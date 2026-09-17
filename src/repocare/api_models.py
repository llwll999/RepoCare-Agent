from pydantic import BaseModel, Field


class CreateIssueRequest(BaseModel):
    title: str = Field(min_length=5, max_length=120)
    description: str = Field(min_length=10, max_length=2000)
    priority: str = Field(default="medium", pattern="^(low|medium|high)$")


class TaskResponse(BaseModel):
    task_id: str
    title: str
    state: str