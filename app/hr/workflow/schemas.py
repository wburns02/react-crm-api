from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.types import UUIDStr


TaskKind = Literal["form_sign", "document_upload", "training_video", "verify", "assignment", "manual"]
TaskStatus = Literal["blocked", "ready", "in_progress", "completed", "skipped"]
AssigneeRole = Literal["hire", "employee", "manager", "hr", "dispatch", "it"]
WorkflowStatus = Literal["active", "completed", "cancelled"]
TemplateCategory = Literal["onboarding", "offboarding", "recruiting", "operational"]
SubjectType = Literal["employee", "applicant", "truck", "customer"]


class TemplateTaskIn(BaseModel):
    position: int
    stage: str | None = None
    name: str
    description: str | None = None
    kind: TaskKind
    assignee_role: AssigneeRole
    due_offset_days: int = 0
    required: bool = True
    config: dict[str, Any] = Field(default_factory=dict)
    depends_on_positions: list[int] = Field(default_factory=list)


class TemplateIn(BaseModel):
    name: str
    category: TemplateCategory
    tasks: list[TemplateTaskIn]


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    name: str
    category: TemplateCategory
    version: int
    is_active: bool


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    instance_id: UUIDStr
    position: int
    stage: str | None
    name: str
    kind: TaskKind
    status: TaskStatus
    assignee_user_id: int | None
    assignee_subject_id: UUIDStr | None
    assignee_role: AssigneeRole
    due_at: datetime | None
    completed_at: datetime | None
    config: dict[str, Any]
    result: dict[str, Any]


class InstanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    template_id: UUIDStr
    template_version: int
    subject_type: SubjectType
    subject_id: UUIDStr
    status: WorkflowStatus
    started_at: datetime
    completed_at: datetime | None


class SpawnRequest(BaseModel):
    template_id: UUIDStr
    subject_type: SubjectType
    subject_id: UUIDStr
    start_date: datetime | None = None


class AdvanceTaskRequest(BaseModel):
    status: Literal["in_progress", "completed", "skipped"]
    reason: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)
