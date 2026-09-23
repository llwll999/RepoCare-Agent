import pytest
from sqlmodel import SQLModel, create_engine

from repocare import db


@pytest.fixture
def isolated_engine(tmp_path, monkeypatch):
    """Give each memory test an empty SQLite file, never the real repocare.db."""
    database_url = f"sqlite:///{tmp_path / 'memory-test.db'}"
    test_engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
    )
    monkeypatch.setattr(db, "engine", test_engine)
    SQLModel.metadata.create_all(test_engine)
    yield test_engine
    test_engine.dispose()
