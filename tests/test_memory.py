from datetime import UTC, datetime, timedelta

from repocare.memory import remember, retrieve


def test_memory_deduplicates_same_project_content(
    isolated_engine,
) -> None:
    first = remember(
        kind="FACT",
        project_scope="assessment-helper",
        module_scope="export_service",
        content="已被替代的审核记录不得参与最终导出。",
        source_trace="task-001:test-export",
        confidence=1.0,
    )
    second = remember(
        kind="FACT",
        project_scope="assessment-helper",
        module_scope="export_service",
        content="已被替代的审核记录不得参与最终导出。",
        source_trace="task-002:review",
        confidence=1.0,
    )

    assert first.memory_id == second.memory_id


def test_retrieve_skips_expired_memory(isolated_engine) -> None:
    now = datetime.now(UTC)
    remember(
        kind="FACT",
        project_scope="assessment-helper",
        module_scope="export_service",
        content="旧规则",
        source_trace="old-task",
        confidence=1.0,
        expires_at=now - timedelta(seconds=1),
    )
    remember(
        kind="FACT",
        project_scope="assessment-helper",
        module_scope="export_service",
        content="新规则",
        source_trace="new-task",
        confidence=1.0,
    )

    memories = retrieve("assessment-helper", "export_service", now)

    assert [row.content for row in memories] == ["新规则"]


def test_memory_is_isolated_by_project(isolated_engine) -> None:
    remember(
        kind="FACT",
        project_scope="assessment-helper",
        module_scope="export_service",
        content="只属于综测项目的规则",
        source_trace="task-003",
        confidence=0.9,
    )

    memories = retrieve("another-project", "export_service")

    assert memories == []
