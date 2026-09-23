from datetime import UTC, datetime

from sqlmodel import select

from repocare.db import MemoryRow, get_session


def remember(
    *,
    kind: str,
    project_scope: str,
    module_scope: str,
    content: str,
    source_trace: str,
    confidence: float,
    expires_at: datetime | None = None,
) -> MemoryRow:
    """Store one fact once per project, returning the existing fact on repeats."""
    with get_session() as session:
        statement = select(MemoryRow).where(
            MemoryRow.project_scope == project_scope,
            MemoryRow.content == content,
        )
        existing = session.exec(statement).first()
        if existing is not None:
            return existing

        row = MemoryRow(
            kind=kind,
            project_scope=project_scope,
            module_scope=module_scope,
            content=content,
            source_trace=source_trace,
            confidence=confidence,
            expires_at=expires_at,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row


def retrieve(
    project_scope: str,
    module_scope: str,
    now: datetime | None = None,
) -> list[MemoryRow]:
    """Read non-expired facts only from the requested project and module."""
    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=UTC)

    with get_session() as session:
        statement = (
            select(MemoryRow)
            .where(
                MemoryRow.project_scope == project_scope,
                MemoryRow.module_scope == module_scope,
            )
            .order_by(MemoryRow.created_at.desc())
        )
        rows = list(session.exec(statement))

    valid_rows: list[MemoryRow] = []
    for row in rows:
        if row.expires_at is None:
            valid_rows.append(row)
            continue
        expires_at = row.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at > current_time:
            valid_rows.append(row)
    return valid_rows
