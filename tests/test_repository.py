from sqlmodel import SQLModel, create_engine

from repocare import db
from repocare.repository import create_task, get_task


def test_task_persists_after_restart(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "repocare-test.db"
    database_url = f"sqlite:///{database_path}"

    first_engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
    )
    monkeypatch.setattr(db, "engine", first_engine)
    SQLModel.metadata.create_all(first_engine)

    created = create_task(
        "task-001",
        "导出分值重复",
        "INTAKE",
    )

    first_engine.dispose()

    restarted_engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
    )
    monkeypatch.setattr(db, "engine", restarted_engine)

    loaded = get_task("task-001")

    assert loaded is not None
    assert loaded.task_id == created.task_id
    assert loaded.title == "导出分值重复"
    assert loaded.state == "INTAKE"

    restarted_engine.dispose()