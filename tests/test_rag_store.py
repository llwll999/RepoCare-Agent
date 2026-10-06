from pathlib import Path

from repocare.multi_agent_runtime import (
    IssueInput,
    build_debugger_context,
    retrieve_rag_evidence,
)
from repocare.rag_store import (
    KnowledgeSearchInput,
    LocalKnowledgeStore,
    search_local_knowledge,
)


def _write_markdown(root: Path, relative_path: str, content: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_local_knowledge_search_returns_source_labelled_chinese_evidence(
    tmp_path: Path,
) -> None:
    root = tmp_path / "knowledge_base"
    _write_markdown(
        root,
        "product_rules/proof-submission.md",
        "# 提交规则\n\n## 重复提交\n同一网页条目重复提交时，系统必须拒绝第二次材料。",
    )
    _write_markdown(
        root,
        "runbooks/timeout.md",
        "# 超时排查\n\n云函数超时要先检查日志和外部依赖。",
    )
    _write_markdown(
        root,
        "node_modules/ignored.md",
        "# 不应入库\nAPI Key secret token",
    )

    store = LocalKnowledgeStore(root, tmp_path / "knowledge.db")
    stats = store.sync()
    results = store.search(KnowledgeSearchInput(query="同一网页条目重复提交", top_k=2))

    assert stats.document_count == 2
    assert stats.chunk_count == 2
    assert results[0].source_path == "knowledge_base/product_rules/proof-submission.md"
    assert results[0].heading == "重复提交"
    assert results[0].score > 0
    assert "必须拒绝" in results[0].content


def test_sync_removes_deleted_document_chunks(tmp_path: Path) -> None:
    root = tmp_path / "knowledge_base"
    source = root / "rules.md"
    _write_markdown(root, "rules.md", "# 规则\n\n重复累计需要先检查材料创建入口。")
    store = LocalKnowledgeStore(root, tmp_path / "knowledge.db")
    store.sync()

    source.unlink()
    stats = store.sync()
    results = store.search(KnowledgeSearchInput(query="重复累计"))

    assert stats.chunk_count == 0
    assert results == []


def test_function_syncs_before_searching(tmp_path: Path) -> None:
    root = tmp_path / "knowledge_base"
    _write_markdown(root, "architecture.md", "# RAG 边界\n\n检索结果不能绕过人工审批和 Sandbox 测试。")

    results = search_local_knowledge(
        KnowledgeSearchInput(query="检索结果不能绕过 Sandbox"),
        knowledge_root=root,
        database_path=tmp_path / "knowledge.db",
    )

    assert len(results) == 1
    assert results[0].source_path == "knowledge_base/architecture.md"


def test_runtime_only_injects_retrieved_rag_evidence_into_model_context() -> None:
    issue = IssueInput(
        title="同一网页条目重复提交后，综测认定总分重复累计",
        description="学生误点提交两次同一智育网页条目，审核后可能重复累计。",
        scenario="zongce",
    )
    evidence = retrieve_rag_evidence(issue)
    context = build_debugger_context("zongce", evidence)

    assert evidence
    assert all(item.source_path in context for item in evidence)
    assert "知识库" not in context["cloudfunctions/apiV102/index.js"]
