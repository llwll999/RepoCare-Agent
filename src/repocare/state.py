from enum import StrEnum


class TaskState(StrEnum):
    INTAKE = "INTAKE"
    INVESTIGATING = "INVESTIGATING"
    PLANNING = "PLANNING"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    PATCHING = "PATCHING"
    VERIFYING = "VERIFYING"
    RESOLVED = "RESOLVED"
    NEEDS_HUMAN = "NEEDS_HUMAN"


ALLOWED_TRANSITIONS: dict[TaskState, set[TaskState]] = {
    TaskState.INTAKE: {TaskState.INVESTIGATING},
    TaskState.INVESTIGATING: {TaskState.PLANNING, TaskState.NEEDS_HUMAN},
    TaskState.PLANNING: {TaskState.WAITING_FOR_APPROVAL},
    TaskState.WAITING_FOR_APPROVAL: {TaskState.PATCHING, TaskState.NEEDS_HUMAN},
    TaskState.PATCHING: {TaskState.VERIFYING},
    TaskState.VERIFYING: {
        TaskState.RESOLVED,
        TaskState.INVESTIGATING,
        TaskState.NEEDS_HUMAN,
    },
    TaskState.RESOLVED: set(),
    TaskState.NEEDS_HUMAN: set(),
}


def can_transition(current: TaskState, target: TaskState) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


def require_transition(current: TaskState, target: TaskState) -> None:
    if not can_transition(current, target):
        raise ValueError(f"illegal transition: {current} -> {target}")