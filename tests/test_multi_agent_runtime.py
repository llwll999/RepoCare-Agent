from repocare.multi_agent_runtime import (
    EXPORT_FILE,
    PROJECT_ROOT,
    DemoRun,
    FeedbackInput,
    IssueInput,
    add_feedback,
    create_demo_run,
)


def make_issue() -> IssueInput:
    return IssueInput(
        title="补交后导出分值重复",
        description="同一材料补交后，导出的已认定分值从 4 重复累计为 8。",
    )


def test_debugger_stops_when_current_source_already_has_the_safety_guard() -> None:
    run = create_demo_run(make_issue())

    assert run.state == "NEEDS_HUMAN"
    assert [evidence.path for evidence in run.evidence] == [
        "demo_app/export_service.py",
        "demo_app/models.py",
        "tests/test_export_service.py",
    ]
    assert run.patch_diff == ""
    assert run.rag_evidence
    assert "No patch is proposed" in run.approved_scope


def test_feedback_invalidates_approval_and_keeps_run_waiting() -> None:
    run = DemoRun(
        run_id="run-001",
        title="演示任务",
        description="需要在批准前限制修改范围。",
        state="WAITING_FOR_APPROVAL",
    )

    updated = add_feedback(
        run,
        FeedbackInput(constraint="只允许改导出逻辑，不能改测试。"),
    )

    assert updated.state == "WAITING_FOR_APPROVAL"
    assert updated.feedback == "只允许改导出逻辑，不能改测试。"
    assert "old approval invalidated" in updated.trace[-2]


def test_currently_protected_source_is_not_changed_while_diagnosing() -> None:
    original_source = (PROJECT_ROOT / EXPORT_FILE).read_text(encoding="utf-8")
    run = create_demo_run(make_issue())

    assert run.state == "NEEDS_HUMAN"
    assert (PROJECT_ROOT / EXPORT_FILE).read_text(encoding="utf-8") == original_source
