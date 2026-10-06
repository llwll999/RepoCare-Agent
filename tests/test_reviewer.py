from repocare.reviewer import (
    VerificationInput,
    verify_resolution,
)


def make_valid_input(**changes) -> VerificationInput:
    data = {
        "task_id": "task-001",
        "approval_granted": True,
        "patch_within_approved_scope": True,
        "regression_test_passed": True,
        "full_test_suite_passed": True,
        "unauthorized_write_count": 0,
    }
    data.update(changes)
    return VerificationInput(**data)


def test_reviewer_accepts_complete_evidence() -> None:
    report = verify_resolution(make_valid_input())

    assert report.verified is True
    assert report.reasons == []


def test_reviewer_rejects_false_completion() -> None:
    report = verify_resolution(
        make_valid_input(regression_test_passed=False)
    )

    assert report.verified is False
    assert "regression test still failing" in report.reasons


def test_reviewer_rejects_unauthorized_write() -> None:
    report = verify_resolution(
        make_valid_input(unauthorized_write_count=1)
    )

    assert report.verified is False
    assert "unauthorized write detected" in report.reasons