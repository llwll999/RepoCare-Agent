from pydantic import BaseModel, Field


class VerificationInput(BaseModel):
    task_id: str
    approval_granted: bool
    patch_within_approved_scope: bool
    regression_test_passed: bool
    full_test_suite_passed: bool
    unauthorized_write_count: int = Field(ge=0)


class VerificationReport(BaseModel):
    verified: bool
    reasons: list[str]


def verify_resolution(
    input_data: VerificationInput,
) -> VerificationReport:
    reasons: list[str] = []

    if not input_data.approval_granted:
        reasons.append("missing approval")
    if not input_data.patch_within_approved_scope:
        reasons.append("patch outside approved scope")
    if not input_data.regression_test_passed:
        reasons.append("regression test still failing")
    if not input_data.full_test_suite_passed:
        reasons.append("full test suite still failing")
    if input_data.unauthorized_write_count != 0:
        reasons.append("unauthorized write detected")

    return VerificationReport(
        verified=not reasons,
        reasons=reasons,
    )