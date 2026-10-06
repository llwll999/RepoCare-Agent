"""Local, source-traceable retrieval for RepoCare's debugger agent.

This module deliberately starts with an offline sparse-vector baseline instead
of downloading an embedding model.  It reads only curated Markdown files from
``knowledge_base/``, persists chunks in SQLite, and returns source paths with
every result.  A later semantic embedding adapter can replace the scoring
function without changing the Runtime's approval or test safeguards.
"""

from __future__ import annotations

import hashlib
import math
import re
import sqlite3
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_KNOWLEDGE_ROOT = PROJECT_ROOT / "knowledge_base"
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "repocare_knowledge.db"

MAX_DOCUMENT_CHARS = 80_000
MAX_CHUNK_CHARS = 720
CHUNK_OVERLAP_CHARS = 100
IGNORED_PATH_PARTS = {".git", ".venv", "node_modules", "__pycache__"}


class KnowledgeChunk(BaseModel):
    """One immutable, source-labelled text unit stored in the local knowledge base."""

    chunk_id: str
    source_path: str
    heading: str
    content: str = Field(min_length=1, max_length=MAX_CHUNK_CHARS)
    content_hash: str


class RetrievedEvidence(KnowledgeChunk):
    """A retrieved chunk plus its local sparse-vector similarity score."""

    score: float = Field(ge=0.0, le=1.0)


class KnowledgeSearchInput(BaseModel):
    query: str = Field(min_length=2, max_length=2_000)
    top_k: int = Field(default=3, ge=1, le=5)


class KnowledgeBaseStats(BaseModel):
    document_count: int
    chunk_count: int


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_allowed_markdown(path: Path, root: Path) -> bool:
    """Keep indexing strictly inside the curated directory and skip hidden secrets."""
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return (
        path.suffix.lower() == ".md"
        and path.name != ".env"
        and not any(part in IGNORED_PATH_PARTS for part in relative.parts)
    )


def _markdown_sections(path: Path, text: str) -> list[tuple[str, str]]:
    """Split Markdown by headings before splitting long sections into chunks."""
    heading = path.stem.replace("_", " ")
    sections: list[tuple[str, str]] = []
    lines: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
        if match:
            body = "\n".join(lines).strip()
            if body:
                sections.append((heading, body))
            heading = match.group(1)
            lines = []
        else:
            lines.append(line)
    body = "\n".join(lines).strip()
    if body:
        sections.append((heading, body))
    return sections


def _split_section(text: str) -> list[str]:
    """Keep paragraphs together where possible, with a small overlap for context."""
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= MAX_CHUNK_CHARS:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = f"{current[-CHUNK_OVERLAP_CHARS:]}\n\n{paragraph}".strip()
        while len(current) > MAX_CHUNK_CHARS:
            chunks.append(current[:MAX_CHUNK_CHARS])
            current = current[MAX_CHUNK_CHARS - CHUNK_OVERLAP_CHARS :]
    if current:
        chunks.append(current)
    return chunks


def load_knowledge_chunks(root: Path = DEFAULT_KNOWLEDGE_ROOT) -> list[KnowledgeChunk]:
    """Read only curated Markdown into source-traceable, bounded chunks."""
    if not root.exists():
        return []

    chunks: list[KnowledgeChunk] = []
    for path in sorted(root.rglob("*.md")):
        if not _is_allowed_markdown(path, root):
            continue
        text = path.read_text(encoding="utf-8")
        if len(text) > MAX_DOCUMENT_CHARS:
            raise ValueError(f"knowledge document is too large: {path.name}")
        source_path = path.resolve().relative_to(root.resolve().parent).as_posix()
        for section_index, (heading, section) in enumerate(_markdown_sections(path, text)):
            for chunk_index, content in enumerate(_split_section(section)):
                identity = f"{source_path}\0{section_index}\0{chunk_index}\0{content}"
                chunks.append(
                    KnowledgeChunk(
                        chunk_id=_sha256(identity)[:24],
                        source_path=source_path,
                        heading=heading,
                        content=content,
                        content_hash=_sha256(content),
                    )
                )
    return chunks


def _token_counts(text: str) -> Counter[str]:
    """Build a tiny Chinese/English sparse vector without a remote model dependency."""
    normalized = text.lower()
    tokens: Counter[str] = Counter(re.findall(r"[a-z0-9_]+", normalized))
    for sequence in re.findall(r"[\u4e00-\u9fff]+", normalized):
        tokens.update(sequence)
        tokens.update(sequence[index : index + 2] for index in range(len(sequence) - 1))
    return tokens


def _cosine_similarity(query: Counter[str], document: Counter[str]) -> float:
    dot_product = sum(query[token] * document[token] for token in query.keys() & document.keys())
    if not dot_product:
        return 0.0
    query_norm = math.sqrt(sum(value * value for value in query.values()))
    document_norm = math.sqrt(sum(value * value for value in document.values()))
    return dot_product / (query_norm * document_norm)


class LocalKnowledgeStore:
    """A small SQLite-backed local knowledge base with deterministic retrieval."""

    def __init__(
        self,
        knowledge_root: Path = DEFAULT_KNOWLEDGE_ROOT,
        database_path: Path = DEFAULT_DATABASE_PATH,
    ) -> None:
        self.knowledge_root = knowledge_root
        self.database_path = database_path

    def _connection(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge_chunks (
                chunk_id TEXT PRIMARY KEY,
                source_path TEXT NOT NULL,
                heading TEXT NOT NULL,
                content TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                indexed_at TEXT NOT NULL
            )
            """
        )
        return connection

    def sync(self) -> KnowledgeBaseStats:
        """Upsert current Markdown chunks and remove chunks from deleted documents."""
        chunks = load_knowledge_chunks(self.knowledge_root)
        current_ids = {chunk.chunk_id for chunk in chunks}
        with self._connection() as connection:
            for chunk in chunks:
                connection.execute(
                    """
                    INSERT INTO knowledge_chunks(
                        chunk_id, source_path, heading, content, content_hash, indexed_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(chunk_id) DO UPDATE SET
                        source_path=excluded.source_path,
                        heading=excluded.heading,
                        content=excluded.content,
                        content_hash=excluded.content_hash,
                        indexed_at=excluded.indexed_at
                    """,
                    (
                        chunk.chunk_id,
                        chunk.source_path,
                        chunk.heading,
                        chunk.content,
                        chunk.content_hash,
                        _timestamp(),
                    ),
                )
            stored_ids = {
                row["chunk_id"]
                for row in connection.execute("SELECT chunk_id FROM knowledge_chunks")
            }
            stale_ids = stored_ids - current_ids
            connection.executemany(
                "DELETE FROM knowledge_chunks WHERE chunk_id = ?",
                [(chunk_id,) for chunk_id in stale_ids],
            )
        return KnowledgeBaseStats(
            document_count=len({chunk.source_path for chunk in chunks}),
            chunk_count=len(chunks),
        )

    def search(self, input_data: KnowledgeSearchInput) -> list[RetrievedEvidence]:
        """Return only the best source-labelled chunks; never manufacture evidence."""
        query_tokens = _token_counts(input_data.query)
        if not query_tokens:
            return []
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT chunk_id, source_path, heading, content, content_hash FROM knowledge_chunks"
            ).fetchall()
        results = [
            RetrievedEvidence(
                chunk_id=row["chunk_id"],
                source_path=row["source_path"],
                heading=row["heading"],
                content=row["content"],
                content_hash=row["content_hash"],
                score=_cosine_similarity(
                    query_tokens,
                    _token_counts(f"{row['heading']}\n{row['content']}"),
                ),
            )
            for row in rows
        ]
        return [result for result in sorted(
            results, key=lambda item: (-item.score, item.source_path, item.chunk_id)
        ) if result.score > 0][: input_data.top_k]


def search_local_knowledge(
    input_data: KnowledgeSearchInput,
    *,
    knowledge_root: Path = DEFAULT_KNOWLEDGE_ROOT,
    database_path: Path = DEFAULT_DATABASE_PATH,
) -> list[RetrievedEvidence]:
    """Synchronize the curated local knowledge base, then retrieve Top-K evidence."""
    store = LocalKnowledgeStore(knowledge_root, database_path)
    store.sync()
    return store.search(input_data)
