from pathlib import Path
from time import perf_counter

from pydantic import BaseModel, Field

PROJECT_ROOT = Path.cwd()


class ToolResult(BaseModel):
    ok: bool
    code: str
    message: str
    data: dict = Field(default_factory=dict)
    duration_ms: int


class SearchCodeInput(BaseModel):
    query: str = Field(min_length=2, max_length=80)
    relative_root: str = "demo_app"


class ApprovalRequiredError(Exception):
    pass


def search_code(input_data: SearchCodeInput) -> ToolResult:
    started = perf_counter()
    root = (PROJECT_ROOT / input_data.relative_root).resolve()

    if PROJECT_ROOT.resolve() not in root.parents and root != PROJECT_ROOT.resolve():
        return ToolResult(
            ok=False,
            code="path_not_allowed",
            message="requested path is outside the project root",
            duration_ms=0,
        )

    matches: list[str] = []
    for file_path in root.rglob("*.py"):
        text = file_path.read_text(encoding="utf-8")
        if input_data.query.lower() in text.lower():
            matches.append(file_path.relative_to(PROJECT_ROOT).as_posix())

    return ToolResult(
        ok=True,
        code="ok",
        message=f"found {len(matches)} matching files",
        data={"matches": matches},
        duration_ms=int((perf_counter() - started) * 1000),
    )

class ApplyPatchInput(BaseModel):
    task_id: str
    plan_id: str
    idempotency_key: str = Field(min_length=8, max_length=100)
    approved: bool


class PatchLedger:
    def __init__(self) -> None:
        self._results: dict[str, ToolResult] = {}

    def apply_patch(self, input_data: ApplyPatchInput) -> ToolResult:
        if not input_data.approved:
            raise ApprovalRequiredError("approval_required")

        existing = self._results.get(input_data.idempotency_key)
        if existing is not None:
            return existing.model_copy(
                update={
                    "message": "duplicate request; returned previous result",
                }
            )

        result = ToolResult(
            ok=True,
            code="patch_recorded",
            message="sandbox patch recorded; no real file was changed",
            data={
                "task_id": input_data.task_id,
                "plan_id": input_data.plan_id,
                "idempotency_key": input_data.idempotency_key,
            },
            duration_ms=0,
        )
        self._results[input_data.idempotency_key] = result
        return result
