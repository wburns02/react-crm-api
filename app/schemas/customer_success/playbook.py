"""
Playbook Schemas for Enterprise Customer Success Platform
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from enum import Enum


class PlaybookCategory(str, Enum):
    ONBOARDING = "onboarding"
    ADOPTION = "adoption"
    RENEWAL = "renewal"
    CHURN_RISK = "churn_risk"
    EXPANSION = "expansion"
    ESCALATION = "escalation"
    QBR = "qbr"
    EXECUTIVE_SPONSOR = "executive_sponsor"
    CHAMPION_CHANGE = "champion_change"
    IMPLEMENTATION = "implementation"
    TRAINING = "training"
    CUSTOM = "custom"


class PlaybookTriggerType(str, Enum):
    MANUAL = "manual"
    HEALTH_THRESHOLD = "health_threshold"
    SEGMENT_ENTRY = "segment_entry"
    EVENT = "event"
    DAYS_TO_RENEWAL = "days_to_renewal"
    SCHEDULED = "scheduled"


class PlaybookPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PlaybookStepType(str, Enum):
    CALL = "call"
    EMAIL = "email"
    MEETING = "meeting"
    INTERNAL_TASK = "internal_task"
    PRODUCT_DEMO = "product_demo"
    TRAINING = "training"
    REVIEW = "review"
    ESCALATION = "escalation"
    DOCUMENTATION = "documentation"
    APPROVAL = "approval"
    NOTIFICATION = "notification"
    CUSTOM = "custom"


class PlaybookCompletionType(str, Enum):
    MANUAL = "manual"
    AUTO_EMAIL_SENT = "auto_email_sent"
    AUTO_MEETING_SCHEDULED = "auto_meeting_scheduled"
    APPROVAL_RECEIVED = "approval_received"


class PlaybookExecStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class PlaybookOutcome(str, Enum):
    SUCCESSFUL = "successful"
    UNSUCCESSFUL = "unsuccessful"
    PARTIAL = "partial"
    CANCELLED = "cancelled"


# Playbook Steps

class PlaybookStepBase(BaseModel):
    """Base playbook step schema."""
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    step_type: PlaybookStepType

    step_order: int = Field(1, ge=1)

    # Assignment
    default_assignee_role: Optional[str] = Field(None, max_length=50)
    assignee_override_allowed: bool = True

    # Timing
    days_from_start: int = Field(0, ge=0)
    due_days: Optional[int] = Field(None, ge=1)
    is_required: bool = True

    # Dependencies
    depends_on_step_ids: Optional[list[int]] = None
    blocks_step_ids: Optional[list[int]] = None

    # Templates
    email_template_id: Optional[int] = None
    email_subject: Optional[str] = Field(None, max_length=255)
    email_body_template: Optional[str] = None

    meeting_agenda_template: Optional[str] = None
    talk_track: Optional[str] = None
    instructions: Optional[str] = None

    # Required artifacts
    required_artifacts: Optional[list[str]] = None
    required_outcomes: Optional[list[str]] = None

    # Completion
    completion_type: PlaybookCompletionType = PlaybookCompletionType.MANUAL

    # Skip conditions
    skip_if_condition: Optional[dict] = None

    is_active: bool = True


class PlaybookStepCreate(PlaybookStepBase):
    """Schema for creating a playbook step."""
    playbook_id: int


class PlaybookStepUpdate(BaseModel):
    """Schema for updating a playbook step."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    step_type: Optional[PlaybookStepType] = None
    step_order: Optional[int] = Field(None, ge=1)
    default_assignee_role: Optional[str] = None
    assignee_override_allowed: Optional[bool] = None
    days_from_start: Optional[int] = Field(None, ge=0)
    due_days: Optional[int] = None
    is_required: Optional[bool] = None
    depends_on_step_ids: Optional[list[int]] = None
    blocks_step_ids: Optional[list[int]] = None
    email_template_id: Optional[int] = None
    email_subject: Optional[str] = None
    email_body_template: Optional[str] = None
    meeting_agenda_template: Optional[str] = None
    talk_track: Optional[str] = None
    instructions: Optional[str] = None
    required_artifacts: Optional[list[str]] = None
    required_outcomes: Optional[list[str]] = None
    completion_type: Optional[PlaybookCompletionType] = None
    skip_if_condition: Optional[dict] = None
    is_active: Optional[bool] = None


class PlaybookStepResponse(PlaybookStepBase):
    """Playbook step response schema."""
    id: int
    playbook_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Playbooks

class PlaybookBase(BaseModel):
    """Base playbook schema."""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    category: PlaybookCategory = PlaybookCategory.CUSTOM

    # Trigger configuration
    trigger_type: PlaybookTriggerType = PlaybookTriggerType.MANUAL
    trigger_health_threshold: Optional[int] = Field(None, ge=0, le=100)
    trigger_health_direction: Optional[str] = Field(None, pattern="^(below|above)$")
    trigger_days_to_renewal: Optional[int] = Field(None, ge=0)
    trigger_event: Optional[str] = Field(None, max_length=100)
    trigger_segment_id: Optional[int] = None
    trigger_config: Optional[dict] = None

    # Settings
    priority: PlaybookPriority = PlaybookPriority.MEDIUM
    is_active: bool = True

    # Assignment
    auto_assign: bool = True
    default_assignee_role: Optional[str] = Field(None, max_length=50)
    escalation_assignee_role: Optional[str] = Field(None, max_length=50)

    # Timing
    estimated_hours: Optional[float] = Field(None, ge=0)
    target_completion_days: Optional[int] = Field(None, ge=1)

    # Success criteria
    success_criteria: Optional[dict] = None

    # Execution settings
    allow_parallel_execution: bool = False
    max_active_per_customer: int = Field(1, ge=1)
    cooldown_days: Optional[int] = Field(None, ge=0)


class PlaybookCreate(PlaybookBase):
    """Schema for creating a playbook."""
    steps: Optional[list[PlaybookStepCreate]] = None


class PlaybookUpdate(BaseModel):
    """Schema for updating a playbook."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    category: Optional[PlaybookCategory] = None
    trigger_type: Optional[PlaybookTriggerType] = None
    trigger_health_threshold: Optional[int] = None
    trigger_health_direction: Optional[str] = None
    trigger_days_to_renewal: Optional[int] = None
    trigger_event: Optional[str] = None
    trigger_segment_id: Optional[int] = None
    trigger_config: Optional[dict] = None
    priority: Optional[PlaybookPriority] = None
    is_active: Optional[bool] = None
    auto_assign: Optional[bool] = None
    default_assignee_role: Optional[str] = None
    escalation_assignee_role: Optional[str] = None
    estimated_hours: Optional[float] = None
    target_completion_days: Optional[int] = None
    success_criteria: Optional[dict] = None
    allow_parallel_execution: Optional[bool] = None
    max_active_per_customer: Optional[int] = None
    cooldown_days: Optional[int] = None


class PlaybookResponse(PlaybookBase):
    """Playbook response schema."""
    id: int

    # Metrics
    times_triggered: int = 0
    times_completed: int = 0
    times_successful: int = 0
    avg_completion_days: Optional[float] = None
    success_rate: Optional[float] = None

    # Steps
    steps: list[PlaybookStepResponse] = []

    # Ownership
    created_by_user_id: Optional[int] = None
    owned_by_user_id: Optional[int] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PlaybookListResponse(BaseModel):
    """Paginated playbook list response."""
    items: list[PlaybookResponse]
    total: int
    page: int
    page_size: int


# Playbook Executions

class PlaybookExecutionBase(BaseModel):
    """Base playbook execution schema."""
    customer_id: int
    playbook_id: int
    triggered_by: Optional[str] = None
    trigger_reason: Optional[str] = None


class PlaybookExecutionCreate(PlaybookExecutionBase):
    """Schema for creating a playbook execution."""
    assigned_to_user_id: Optional[int] = None


class PlaybookExecutionResponse(PlaybookExecutionBase):
    """Playbook execution response schema."""
    id: int
    status: PlaybookExecStatus

    # Progress
    current_step_order: int = 1
    steps_completed: int = 0
    steps_total: Optional[int] = None

    # Assignment
    assigned_to_user_id: Optional[int] = None
    escalated_to_user_id: Optional[int] = None

    # Timing
    started_at: Optional[datetime] = None
    target_completion_date: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None

    # Outcome
    outcome: Optional[PlaybookOutcome] = None
    outcome_notes: Optional[str] = None
    success_criteria_met: Optional[dict] = None

    # Health tracking
    health_score_at_start: Optional[int] = None
    health_score_at_end: Optional[int] = None

    # Time tracking
    total_time_spent_minutes: int = 0

    # Metadata
    metadata: Optional[dict] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PlaybookExecutionListResponse(BaseModel):
    """Paginated playbook execution list response."""
    items: list[PlaybookExecutionResponse]
    total: int
    page: int
    page_size: int


# Trigger Operations

class PlaybookTriggerRequest(BaseModel):
    """Request to trigger a playbook for a customer."""
    customer_id: int
    playbook_id: int
    reason: Optional[str] = None
    assigned_to_user_id: Optional[int] = None
    skip_cooldown: bool = False


class PlaybookBulkTriggerRequest(BaseModel):
    """Request to bulk trigger a playbook."""
    playbook_id: int
    customer_ids: Optional[list[int]] = None
    segment_id: Optional[int] = None
    reason: Optional[str] = None
    skip_cooldown: bool = False
