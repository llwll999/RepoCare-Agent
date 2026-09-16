from uuid import uuid4

from fastapi import FastAPI, HTTPException

from repocare.api_models import CreateIssueRequest, TaskResponse
from repocare.state import TaskState

from repocare.state import TaskState, require_transition


app = FastAPI(title="RepoCare Agent")

tasks: dict[str, TaskResponse] = {}


@app.post("/issues", response_model=TaskResponse, status_code=201)
def create_issue(request: CreateIssueRequest) -> TaskResponse:
    task_id = str(uuid4())
    task = TaskResponse(
        task_id=task_id,
        title=request.title,
        state=TaskState.INTAKE,
    )
    tasks[task_id] = task
    return task


@app.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: str) -> TaskResponse:
    task = tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task

@app.post(
    "/tasks/{task_id}/start-investigation",
    response_model=TaskResponse,
)
def start_investigation(task_id: str) -> TaskResponse:
    task = tasks.get(task_id)

    if task is None:
        raise HTTPException(status_code=404, detail="task not found")

    current_state = TaskState(task.state)
    target_state = TaskState.INVESTIGATING

    try:
        require_transition(current_state, target_state)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    updated_task = task.model_copy(
        update={"state": target_state}
    )
    tasks[task_id] = updated_task

    return updated_task