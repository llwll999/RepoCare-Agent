import pytest

from repocare.state import TaskState, can_transition, require_transition


def test_intake_can_start_investigating() -> None:
    assert can_transition(TaskState.INTAKE, TaskState.INVESTIGATING)


def test_intake_cannot_jump_to_resolved() -> None:
    assert not can_transition(TaskState.INTAKE, TaskState.RESOLVED)

    with pytest.raises(ValueError, match="illegal transition"):
        require_transition(TaskState.INTAKE, TaskState.RESOLVED)