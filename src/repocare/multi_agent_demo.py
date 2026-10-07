"""FastAPI entry point for the visible RepoCare three-agent demo."""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from repocare.langgraph_workflow import approve_langgraph_run, start_langgraph_run
from repocare.memory_store import load_run_checkpoint, save_run_checkpoint
from repocare.multi_agent_runtime import (
    ApplyInput,
    DemoRun,
    FeedbackInput,
    IssueInput,
    add_feedback,
    apply_verified_zongce_patch,
)
from repocare.rag_store import (
    KnowledgeSearchInput,
    RetrievedEvidence,
    search_local_knowledge,
)

app = FastAPI(title="RepoCare Multi-Agent Demo")
runs: dict[str, DemoRun] = {}
STATIC_PAGE = Path(__file__).with_name("static") / "multi_agent.html"


@app.get("/", response_class=FileResponse)
def demo_page() -> FileResponse:
    return FileResponse(STATIC_PAGE)


@app.post("/api/runs", response_model=DemoRun, status_code=201)
def start_run(issue: IssueInput) -> DemoRun:
    run = start_langgraph_run(issue)
    runs[run.run_id] = run
    save_run_checkpoint(run.run_id, run.model_dump(mode="json"))
    return run


@app.post("/api/knowledge/search", response_model=list[RetrievedEvidence])
def search_knowledge(request: KnowledgeSearchInput) -> list[RetrievedEvidence]:
    """Expose a read-only, inspectable local RAG search for the demo UI."""
    return search_local_knowledge(request)


@app.get("/api/runs/{run_id}", response_model=DemoRun)
def get_run(run_id: str) -> DemoRun:
    run = runs.get(run_id)
    if run is None:
        checkpoint = load_run_checkpoint(run_id)
        if checkpoint:
            run = DemoRun.model_validate(checkpoint)
            runs[run.run_id] = run
    if run is None:
        raise HTTPException(status_code=404, detail="demo run not found")
    return run


@app.post("/api/runs/{run_id}/feedback", response_model=DemoRun)
def submit_feedback(run_id: str, feedback: FeedbackInput) -> DemoRun:
    run = get_run(run_id)
    try:
        updated = add_feedback(run, feedback)
        save_run_checkpoint(updated.run_id, updated.model_dump(mode="json"))
        return updated
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/api/runs/{run_id}/approve", response_model=DemoRun)
def approve_run(run_id: str) -> DemoRun:
    run = get_run(run_id)
    try:
        verified = approve_langgraph_run(run)
        save_run_checkpoint(verified.run_id, verified.model_dump(mode="json"))
        return verified
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/api/runs/{run_id}/apply", response_model=DemoRun)
def apply_run(run_id: str, request: ApplyInput) -> DemoRun:
    run = get_run(run_id)
    try:
        delivered = apply_verified_zongce_patch(run, request)
        save_run_checkpoint(delivered.run_id, delivered.model_dump(mode="json"))
        return delivered
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
