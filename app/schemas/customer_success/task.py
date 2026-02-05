"""
Task Schemas for Enterprise Customer Success Platform
"""

from pydantic import BaseModel, Field
from datetime import datetime, date
from typing import Optional
from enum import Enum


class TaskType(str, Enum):
    CALL = "call"
    EMAIL = "email"
    MEETING = "meeting"
    INTERNAL = "internal"
    REVIEW = "review"
    ESCALATION = "escalation"
    FOLLOW_UP = "follow_up"
    DOCUMENTATION = "documentation"
    TRAINING = "training"
    PRODUCT_DEMO = "product_demo"
    QBR = "qbr"
    RENEWAL = "renewal"
    CUSTOM = "custom"


class TaskCategory(str, Enum):
    ONBOARDING = "onboarding"
    ADOPTION = "adoption"
    RETENTION = "retention"
    EXPANSION = "expansion"
    SUPPORT = "support"
    RELATIONSHIP = "relationship"
    ADMINISTRATIVE = "administrative"


class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"
    SNOOZED = "snoozed"


class TaskOutcome(str, Enum):
    SUCCESSFUL = "successful"
    UNSUCCESSFUL = "unsuccessful"
    RESCHEDULED = "rescheduled"
    NO_RESPONSE = "no_response"
    VOICEMAIL = "voicemail"
    ESCALATED = "escalated"
    CANCELLED = "cancelled"
    NOT_APPLICABLE = "not_applicable"


class CSTaskBase(BaseModel):
    """Base CS task schema."""

    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None

    task_type: TaskType = TaskType.CUSTOM
    category: Optional[TaskCategory] = None

    # Customer contact
    contact_name: Optional[str] = Field(None, max_length=100)
    contact_email: Optional[str] = Field(None, max_length=255)
    contact_phone: Optional[str] = Field(None, max_length=50)
    contact_role: Optional[str] = Field(None, max_length=100)

    # Priority and timing
    priority: TaskPriority = TaskPriority.MEDIUM
    due_date: Optional[date] = None
    due_datetime: Optional[datetime] = None
    reminder_at: Optional[datetime] = None

    # Meeting/call details
    scheduled_datetime: Optional[datetime] = None
    meeting_link: Optional[str] = Field(None, max_length=500)
    meeting_duration_minutes: Optional[int] = Field(None, ge=5)
    meeting_type: Optional[str] = Field(None, max_length=50)

    # Templates
    instructions: Optional[str] = None
    talk_track: Optional[str] = None
    agenda: Optional[str] = None

    # Requirements
    required_artifacts: Optional[list[str]] = None
    estimated_minutes: Optional[int] = Field(None, ge=1)

    # Dependencies
    depends_on_task_ids: Optional[list[int]] = None
    blocks_task_ids: Optional[list[int]] = None

    # Recurrence
    is_recurring: bool = False
    recurrence_pattern: Optional[str] = Field(None, pattern="^(daily|weekly|biweekly|monthly)$")
    recurrence_end_date: Optional[date] = None

    # Links
    related_url: Optional[str] = Field(None, max_length=500)
    document_url: Optional[str] = Field(None, max_length=500)

    # Metadata
    tags: Optional[list[str]] = None
    task_data: Optional[dict] = None  # Renamed from metadata to avoid SQLAlchemy conflict


class CSTaskCreate(CSTaskBase):
    """Schema for creating a CS task."""

    customer_id: str
    assigned_to_user_id: Optional[int] = None


class CSTaskUpdate(BaseModel):
    """Schema for updating a CS task."""

    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    task_type: Optional[TaskType] = None
    category: Optional[TaskCategory] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_role: Optional[str] = None
    priority: Optional[TaskPriority] = None
    status: Optional[TaskStatus] = None
    due_date: Optional[date] = None
    due_datetime: Optional[datetime] = None
    reminder_at: Optional[datetime] = None
    snoozed_until: Optional[datetime] = None
    scheduled_datetime: Optional[datetime] = None
    meeting_link: Optional[str] = None
    meeting_duration_minutes: Optional[int] = None
    meeting_type: Optional[str] = None
    instructions: Optional[str] = None
    talk_track: Optional[str] = None
    agenda: Optional[str] = None
    required_artifacts: Optional[list[str]] = None
    estimated_minutes: Optional[int] = None
    depends_on_task_ids: Optional[list[int]] = None
    blocks_task_ids: Optional[list[int]] = None
    is_recurring: Optional[bool] = None
    recurrence_pattern: Optional[str] = None
    recurrence_end_date: Optional[date] = None
    related_url: Optional[str] = None
    document_url: Optional[str] = None
    recording_url: Optional[str] = None
    tags: Optional[list[str]] = None
    task_data: Optional[dict] = None  # Renamed from metadata to avoid SQLAlchemy conflict
    assigned_to_user_id: Optional[int] = None


class CSTaskResponse(CSTaskBase):
    """CS task response schema."""

    id: int
    customer_id: str
    status: TaskStatus

    # Assignment
    assigned_to_user_id: Optional[int] = None
    assigned_to_role: Optional[str] = None
    assigned_by_user_id: Optional[int] = None
    assigned_at: Optional[datetime] = None

    # Origin
    playbook_execution_id: Optional[int] = None
    playbook_step_id: Optional[int] = None
    journey_enrollment_id: Optional[int] = None
    journey_step_id: Optional[int] = None
    source: Optional[str] = None

    # Timing
    snoozed_until: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None

    # Outcome
    outcome: Optional[TaskOutcome] = None
    outcome_notes: Optional[str] = None

    # Completed artifacts
    completed_artifacts: Optional[dict] = None

    # Time tracking
    time_spent_minutes: int = 0

    # Email tracking
    email_template_id: Optional[int] = None
    email_sent_at: Optional[datetime] = None
    email_opened_at: Optional[datetime] = None
    email_clicked_at: Optional[datetime] = None

    # Recurrence
    parent_task_id: Optional[int] = None

    # Links
    recording_url: Optional[str] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CSTaskListResponse(BaseModel):
    """Paginated CS task list response."""

    items: list[CSTaskResponse]
    total: int
    page: int
    page_size: int


# Task Operations


class CSTaskCompleteRequest(BaseModel):
    """Request to complete a task."""

    outcome: TaskOutcome
    outcome_notes: Optional[str] = None
    completed_artifacts: Optional[dict] = None
    time_spent_minutes: Optional[int] = Field(None, ge=0)


class CSTaskAssignRequest(BaseModel):
    """Request to assign/reassign a task."""

    assigned_to_user_id: int
    reason: Optional[str] = None


class CSTaskBulkUpdateRequest(BaseModel):
    """Request to bulk update tasks."""

    task_ids: list[int]
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    assigned_to_user_id: Optional[int] = None
    due_date: Optional[date] = None
