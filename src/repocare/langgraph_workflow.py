"""LangGraph orchestration for RepoCare's controlled repair workflow.

LangGraph owns the *workflow checkpoint and interrupt boundary*. Existing
RepoCare modules remain responsible for domain logic: RAG retrieval, model
protocol validation, patch construction, Sandbox verification, and delivery
guardrails. This keeps framework code from gaining write authority.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any, Literal, TypedDict
from uuid import uuid4

# Restrict checkpoint deserialization before importing the SQLite saver.
os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from repocare.deepseek import (
    DeepSeekDiagnosis,
    DeepSeekDiagnosisError,
    diagnose_with_deepseek,
)
from repocare.multi_agent_runtime import (
    DemoRun,
    IssueInput,
    approve_and_test,
    build_debugger_context,
    create_demo_run,
    persist_verified_memory,
    retrieve_rag_evidence,
)
from repocare.rag_store import RetrievedEvidence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LANGGRAPH_DB = PROJECT_ROOT / "repocare_langgraph.db"


class RepoCareGraphState(TypedDict, total=False):
    """JSON-serializable state shared by the explicit workflow nodes."""

    run_id: str
    issue: dict[str, Any]
    rag_evidence: list[dict[str, Any]]
    model_diagnosis: dict[str, Any] | None
    model_warning: str | None
    run: dict[str, Any]
    approval: dict[str, Any]


def _as_evidence(items: list[dict[str, Any]]) -> list[RetrievedEvidence]:
    return [RetrievedEvidence.model_validate(item) for item in items]


def debugger_node(state: RepoCareGraphState) -> RepoCareGraphState:
    """Read only code/RAG evidence, then request a validated model diagnosis."""
    issue = IssueInput.model_validate(state["issue"])
    rag_evidence = retrieve_rag_evidence(issue)
    try:
        diagnosis = diagnose_with_deepseek(
            title=issue.title,
            description=issue.description,
            source_files=build_debugger_context(issue.scenario, rag_evidence),
        )
        return {
            "rag_evidence": [item.model_dump(mode="json") for item in rag_evidence],
            "model_diagnosis": diagnosis.model_dump(mode="json"),
            "model_warning": None,
        }
    except DeepSeekDiagnosisError as error:
        # The deterministic repair path remains available when the optional
        # external model is unavailable or returns an invalid protocol shape.
        return {
            "rag_evidence": [item.model_dump(mode="json") for item in rag_evidence],
            "model_diagnosis": None,
            "model_warning": str(error),
        }


def modifier_node(state: RepoCareGraphState) -> RepoCareGraphState:
    """Generate a constrained proposal; this node never writes real code."""
    issue = IssueInput.model_validate(state["issue"])
    diagnosis_data = state.get("model_diagnosis")
    run = create_demo_run(
        issue,
        model_diagnosis=(
            DeepSeekDiagnosis.model_validate(diagnosis_data)
            if isinstance(diagnosis_data, dict)
            else None
        ),
        model_warning=state.get("model_warning"),
        rag_evidence=_as_evidence(state.get("rag_evidence", [])),
    )
    # The LangGraph thread ID and API-visible run ID are deliberately identical.
    run.run_id = state["run_id"]
    run.trace.extend(
        [
            "langgraph node: debugger evidence checkpoint completed",
            "langgraph node: modifier proposal checkpoint completed",
        ]
    )
    return {"run": run.model_dump(mode="json")}


def route_after_modifier(
    state: RepoCareGraphState,
) -> Literal["human_approval", "finish"]:
    run = DemoRun.model_validate(state["run"])
    # A safe stop (for example, the current source already has the guard) is
    # an intentional graph terminal state, not an invitation to fabricate a patch.
    return "human_approval" if run.state == "WAITING_FOR_APPROVAL" else "finish"


def human_approval_node(state: RepoCareGraphState) -> RepoCareGraphState:
    """Pause the graph until a human accepts or rejects the exact proposal."""
    run = DemoRun.model_validate(state["run"])
    decision = interrupt(
        {
            "kind": "patch_approval",
            "run_id": run.run_id,
            "approved_scope": run.approved_scope,
            "patch_diff": run.patch_diff,
            "message": "Sandbox verification requires explicit human approval.",
        }
    )
    if not isinstance(decision, dict) or not decision.get("approved"):
        run.state = "NEEDS_HUMAN"
        run.working_memory = "人工未批准当前补丁；任务停止，等待新的约束或复现信息。"
        run.trace.append("langgraph interrupt: human rejected or withheld approval")
        return {
            "run": run.model_dump(mode="json"),
            "approval": {"approved": False},
        }

    # API feedback may have changed the displayed proposal while the graph was
    # paused. Pass that validated snapshot on resume instead of discarding it.
    candidate_run = decision.get("run")
    if isinstance(candidate_run, dict):
        run = DemoRun.model_validate(candidate_run)
    run.trace.append("langgraph interrupt resumed: human approved Sandbox execution")
    return {
        "run": run.model_dump(mode="json"),
        "approval": {"approved": True},
    }


def route_after_approval(state: RepoCareGraphState) -> Literal["tester", "finish"]:
    approval = state.get("approval", {})
    return "tester" if approval.get("approved") else "finish"


def tester_node(state: RepoCareGraphState) -> RepoCareGraphState:
    """Let the existing independent Sandbox verifier decide the final state."""
    run = DemoRun.model_validate(state["run"])
    verified = persist_verified_memory(approve_and_test(run))
    verified.trace.append("langgraph node: tester verification checkpoint completed")
    return {"run": verified.model_dump(mode="json")}


def build_repocare_graph(checkpointer: Any) -> Any:
    """Build the explicit debugger → modifier → approval → tester graph."""
    workflow = StateGraph(RepoCareGraphState)
    workflow.add_node("debugger", debugger_node)
    workflow.add_node("modifier", modifier_node)
    workflow.add_node("human_approval", human_approval_node)
    workflow.add_node("tester", tester_node)
    workflow.add_edge(START, "debugger")
    workflow.add_edge("debugger", "modifier")
    workflow.add_conditional_edges(
        "modifier",
        route_after_modifier,
        {"human_approval": "human_approval", "finish": END},
    )
    workflow.add_conditional_edges(
        "human_approval",
        route_after_approval,
        {"tester": "tester", "finish": END},
    )
    workflow.add_edge("tester", END)
    return workflow.compile(checkpointer=checkpointer)


# SqliteSaver is suitable for this local single-process demo. A production
# multi-worker deployment should migrate this one checkpoint backend to Postgres.
_connection = sqlite3.connect(LANGGRAPH_DB, check_same_thread=False)
_checkpointer = SqliteSaver(_connection)
_checkpointer.setup()
repocare_graph = build_repocare_graph(_checkpointer)
_graph_lock = RLock()


def _config(run_id: str) -> dict[str, dict[str, str]]:
    return {"configurable": {"thread_id": run_id}}


def _load_graph_run(run_id: str) -> DemoRun:
    snapshot = repocare_graph.get_state(_config(run_id))
    payload = snapshot.values.get("run")
    if not isinstance(payload, dict):
        raise TypeError("LangGraph checkpoint does not contain a RepoCare run")
    return DemoRun.model_validate(payload)


def start_langgraph_run(issue: IssueInput) -> DemoRun:
    """Start a graph and return after proposal generation or a safe stop."""
    run_id = str(uuid4())
    with _graph_lock:
        repocare_graph.invoke(
            {"run_id": run_id, "issue": issue.model_dump(mode="json")},
            _config(run_id),
            durability="sync",
        )
        return _load_graph_run(run_id)


def approve_langgraph_run(run: DemoRun) -> DemoRun:
    """Resume the interrupted approval node and execute the tester node."""
    if run.state != "WAITING_FOR_APPROVAL":
        raise ValueError("a run must be waiting for approval before execution")
    with _graph_lock:
        repocare_graph.invoke(
            Command(
                resume={"approved": True, "run": run.model_dump(mode="json")}
            ),
            _config(run.run_id),
            durability="sync",
        )
        return _load_graph_run(run.run_id)
