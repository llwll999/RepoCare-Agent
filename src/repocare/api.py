from uuid import uuid4

from fastapi import FastAPI, HTTPException

from repocare.api_models import CreateIssueRequest, TaskResponse
from repocare.db import create_db_and_tables
from repocare.repository import create_task
from repocare.repository import get_task as get_task_from_db
from repocare.state import TaskState

app = FastAPI(title="RepoCare Agent")


@app.on_event("startup")
def on_startup() -> None:
    create_db_and_tables()


@app.post("/issues", response_model=TaskResponse, status_code=201)
def create_issue(request: CreateIssueRequest) -> TaskResponse:
    row = create_task(
        task_id=str(uuid4()),
        title=request.title,
        state=TaskState.INTAKE.value,
    )
    return TaskResponse(
        task_id=row.task_id,
        title=row.title,
        state=row.state,
    )


@app.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: str) -> TaskResponse:
    row = get_task_from_db(task_id)
    if row is None:
        raise HTTPException(status_code=404, detail="task not found")

    return TaskResponse(
        task_id=row.task_id,
        title=row.title,
        state=row.state,
    )