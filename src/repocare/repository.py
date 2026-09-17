from sqlmodel import select

from repocare.db import CheckpointRow, TaskRow, get_session


def create_task(task_id: str, title: str, state: str) -> TaskRow:
    with get_session() as session:
        row = TaskRow(task_id=task_id, title=title, state=state)
        session.add(row)
        session.add(
            CheckpointRow(
                task_id=task_id,
                from_state="",
                to_state=state,
                reason="task created",
            )
        )
        session.commit()
        session.refresh(row)
        return row


def get_task(task_id: str) -> TaskRow | None:
    with get_session() as session:
        return session.get(TaskRow, task_id)


def transition_task(
    task_id: str,
    from_state: str,
    to_state: str,
    reason: str,
) -> TaskRow:
    with get_session() as session:
        row = session.get(TaskRow, task_id)
        if row is None:
            raise KeyError(task_id)

        row.state = to_state
        session.add(
            CheckpointRow(
                task_id=task_id,
                from_state=from_state,
                to_state=to_state,
                reason=reason,
            )
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row


def list_checkpoints(task_id: str) -> list[CheckpointRow]:
    with get_session() as session:
        statement = select(CheckpointRow).where(
            CheckpointRow.task_id == task_id
        )
        return list(session.exec(statement))