import pytest

from repocare.tools import (
    ApplyPatchInput,
    ApprovalRequiredError,
    PatchLedger,
)


def test_patch_requires_approval() -> None:
    ledger = PatchLedger()

    with pytest.raises(ApprovalRequiredError, match="approval_required"):
        ledger.apply_patch(
            ApplyPatchInput(
                task_id="task-001",
                plan_id="plan-001",
                idempotency_key="request-001",
                approved=False,
            )
        )


def test_patch_is_idempotent() -> None:
    ledger = PatchLedger()
    request = ApplyPatchInput(
        task_id="task-001",
        plan_id="plan-001",
        idempotency_key="request-001",
        approved=True,
    )

    first = ledger.apply_patch(request)
    second = ledger.apply_patch(request)

    assert first.code == "patch_recorded"
    assert second.data == first.data
    assert "duplicate request" in second.message