from repocare.multi_agent_runtime import (
    ZONGCE_CLOUD_FILE,
    ZONGCE_PROJECT_ROOT,
    ApplyInput,
    IssueInput,
    apply_verified_zongce_patch,
    create_demo_run,
)


def test_zongce_existing_guard_does_not_receive_a_duplicate_patch() -> None:
    original_source = (ZONGCE_PROJECT_ROOT / ZONGCE_CLOUD_FILE).read_text(
        encoding="utf-8"
    )
    run = create_demo_run(
        IssueInput(
            title="同一网页条目重复提交后，综测认定总分重复累计",
            description="学生误点提交两次同一智育网页条目，审核后可能重复累计。",
            scenario="zongce",
        )
    )

    assert run.rag_evidence
    assert any(
        item.source_path == "knowledge_base/product_rules/zongce-proof-submission.md"
        for item in run.rag_evidence
    )

    assert run.state == "NEEDS_HUMAN"
    assert run.patch_diff == ""
    assert (ZONGCE_PROJECT_ROOT / ZONGCE_CLOUD_FILE).read_text(
        encoding="utf-8"
    ) == original_source


def test_real_code_apply_requires_second_confirmation() -> None:
    run = create_demo_run(
        IssueInput(
            title="同一网页条目重复提交后，综测认定总分重复累计",
            description="学生误点提交两次同一智育网页条目，审核后可能重复累计。",
            scenario="zongce",
        )
    )

    try:
        apply_verified_zongce_patch(run, ApplyInput(confirmed=False))
    except ValueError as error:
        assert "请先勾选" in str(error)
    else:
        raise AssertionError("an unconfirmed request must never modify real code")
