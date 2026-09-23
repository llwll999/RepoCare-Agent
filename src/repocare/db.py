from datetime import UTC, datetime

from sqlmodel import Field, Session, SQLModel, create_engine

DATABASE_URL = "sqlite:///repocare.db"
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)


class TaskRow(SQLModel, table=True):
    task_id: str = Field(primary_key=True)
    title: str
    state: str = Field(index=True)


class CheckpointRow(SQLModel, table=True):
    checkpoint_id: int | None = Field(default=None, primary_key=True)
    task_id: str = Field(index=True)
    from_state: str
    to_state: str
    reason: str


class MemoryRow(SQLModel, table=True):
    """A traceable long-term fact, scoped to one project and module."""

    memory_id: int | None = Field(default=None, primary_key=True)
    kind: str = Field(index=True)
    project_scope: str = Field(index=True)
    module_scope: str = Field(index=True)
    content: str
    source_trace: str
    confidence: float
    expires_at: datetime | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)
