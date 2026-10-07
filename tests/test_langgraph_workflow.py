from __future__ import annotations

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

import repocare.langgraph_workflow as workflow_module
from repocare.deepseek import DeepSeekDiagnosisError
from repocare.multi_agent_runtime import DemoRun, IssueInput
from repocare.multi_agent_runtime import TestReport as RunTestReport


def make_issue() -> IssueInput:
    return IssueInput(
        title="补交后导出分值重复",
        description="同一材料补交后，导出的已认定分值从 4 重复累计为 8。",
    )


def model_unavailable(**_: object) -> object:
    raise DeepSeekDiagnosisError("test model is intentionally unavailable")


def test_graph_ends_safely_when_current_source_already_has_the_guard(
    monkeypatch,
) -> None:
    monkeypatch.setattr(workflow_module, "retrieve_rag_evidence", lambda _: [])
    monkeypatch.setattr(workflow_module, "diagnose_with_deepseek", model_unavailable)

    with SqliteSaver.from_conn_string(":memory:") as saver:
        saver.setup()
        graph = workflow_module.build_repocare_graph(saver)
        config = {"configurable": {"thread_id": "already-protected"}}

        graph.invoke(
            {"run_id": "already-protected", "issue": make_issue().model_dump()},
            config,
            durability="sync",
        )
        snapshot = graph.get_state(config)

    run = DemoRun.model_validate(snapshot.values["run"])
    assert run.state == "NEEDS_HUMAN"
    assert snapshot.next == ()
    assert run.patch_diff == ""


def test_graph_interrupts_for_approval_then_resumes_to_tester(
    monkeypatch,
) -> None:
    monkeypatch.setattr(workflow_module, "retrieve_rag_evidence", lambda _: [])
    monkeypatch.setattr(workflow_module, "diagnose_with_deepseek", model_unavailable)

    def waiting_proposal(*_: object, **__: object) -> DemoRun:
        return DemoRun(
            run_id="will-be-replaced",
            title="演示补丁",
            description="验证 LangGraph 的批准中断和恢复。",
            state="WAITING_FOR_APPROVAL",
            patch_diff="--- a/demo.py\n+++ b/demo.py\n",
            approved_scope="Only demo.py may be changed.",
        )

    def verified_run(run: DemoRun) -> DemoRun:
        run.state = "RESOLVED"
        run.test_report = RunTestReport(passed=True, output="sandbox passed", duration_ms=1)
        return run

    monkeypatch.setattr(workflow_module, "create_demo_run", waiting_proposal)
    monkeypatch.setattr(workflow_module, "approve_and_test", verified_run)
    monkeypatch.setattr(workflow_module, "persist_verified_memory", lambda run: run)

    with SqliteSaver.from_conn_string(":memory:") as saver:
        saver.setup()
        graph = workflow_module.build_repocare_graph(saver)
        config = {"configurable": {"thread_id": "approval-thread"}}

        paused = graph.invoke(
            {"run_id": "approval-thread", "issue": make_issue().model_dump()},
            config,
            durability="sync",
        )
        assert "__interrupt__" in paused

        before_approval = DemoRun.model_validate(graph.get_state(config).values["run"])
        graph.invoke(
            Command(
                resume={
                    "approved": True,
                    "run": before_approval.model_dump(mode="json"),
                }
            ),
            config,
            durability="sync",
        )
        snapshot = graph.get_state(config)

    after_approval = DemoRun.model_validate(snapshot.values["run"])
    assert after_approval.run_id == "approval-thread"
    assert after_approval.state == "RESOLVED"
    assert snapshot.next == ()
    assert any("tester verification checkpoint" in item for item in after_approval.trace)
