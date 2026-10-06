"""Small durable memory store for RepoCare's local demonstration.

Task checkpoints retain short-lived working state and make a server restart
recoverable. Long-term memories retain only verified engineering decisions,
never source files, API keys, or raw user uploads.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_PATH = PROJECT_ROOT / "repocare_memory.db"


def _connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS run_checkpoints (
            run_id TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS long_term_memories (
            memory_key TEXT PRIMARY KEY,
            scenario TEXT NOT NULL,
            summary TEXT NOT NULL,
            tags TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    return connection


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def save_run_checkpoint(run_id: str, payload: dict[str, Any]) -> None:
    """Store bounded working memory and state, so a stopped service can recover."""
    with _connection() as connection:
        connection.execute(
            """
            INSERT INTO run_checkpoints(run_id, payload, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                payload=excluded.payload,
                updated_at=excluded.updated_at
            """,
            (run_id, json.dumps(payload, ensure_ascii=False), _timestamp()),
        )


def load_run_checkpoint(run_id: str) -> dict[str, Any] | None:
    with _connection() as connection:
        row = connection.execute(
            "SELECT payload FROM run_checkpoints WHERE run_id = ?", (run_id,)
        ).fetchone()
    return json.loads(row["payload"]) if row else None


def remember_verified_pattern(
    *, scenario: str, memory_key: str, summary: str, tags: list[str]
) -> None:
    """Persist a concise, tested lesson that can help later tasks in this scenario."""
    with _connection() as connection:
        connection.execute(
            """
            INSERT INTO long_term_memories(memory_key, scenario, summary, tags, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(memory_key) DO UPDATE SET
                summary=excluded.summary,
                tags=excluded.tags,
                created_at=excluded.created_at
            """,
            (memory_key, scenario, summary, json.dumps(tags, ensure_ascii=False), _timestamp()),
        )


def recall_verified_patterns(scenario: str, limit: int = 3) -> list[dict[str, Any]]:
    """Return a small bounded set; long-term memory must not flood model context."""
    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT memory_key, summary, tags, created_at
            FROM long_term_memories
            WHERE scenario = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (scenario, limit),
        ).fetchall()
    return [
        {
            "memory_key": row["memory_key"],
            "summary": row["summary"],
            "tags": json.loads(row["tags"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]
