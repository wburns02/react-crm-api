"""
Journey Schemas for Enterprise Customer Success Platform
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Any
from enum import Enum


class JourneyStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class JourneyType(str, Enum):
    ONBOARDING = "onboarding"
    ADOPTION = "adoption"
    RETENTION = "retention"
    EXPANSION = "expansion"
    RENEWAL = "renewal"
    WIN_BACK = "win_back"
    CUSTOM = "custom"
    # Additional types from database model
    RISK_MITIGATION = "risk_mitigation"
    ADVOCACY = "advocacy"


class JourneyStepType(str, Enum):
    EMAIL = "email"
    TASK = "task"
    WAIT = "wait"
    CONDITION = "condition"
    WEBHOOK = "webhook"
    HUMAN_TOUCHPOINT = "human_touchpoint"
    IN_APP_MESSAGE = "in_app_message"
    SMS = "sms"
    NOTIFICATION = "notification"
    UPDATE_FIELD = "update_field"
    ADD_TAG = "add_tag"
    ENROLL_JOURNEY = "enroll_journey"
    TRIGGER_PLAYBOOK = "trigger_playbook"
    # Additional types from database model
    SEGMENT_UPDATE = "segment_update"
    HEALTH_CHECK = "health_check"
    SLACK_NOTIFICATION = "slack_notification"
    CUSTOM = "custom"


class EnrollmentStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    EXITED = "exited"
    FAILED = "failed"


class StepExecutionStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


# Journey Steps


class JourneyStepBase(BaseModel):
    """Base journey step schema."""

    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    step_type: JourneyStepType

    step_order: int = Field(1, ge=1)

    # Wait configuration
    wait_duration_hours: Optional[int] = None
    wait_until_time: Optional[str] = None  # "09:00" in customer timezone
    wait_for_event: Optional[str] = None

    # Condition configuration
    condition_rules: Optional[dict] = None  # Same format as segment rules
    true_next_step_id: Optional[int] = None
    false_next_step_id: Optional[int] = None

    # Action configuration
    action_config: Optional[dict] = None
    # Email: {"template_id": 1, "subject": "...", "from_name": "..."}
    # Task: {"title": "...", "description": "...", "assignee_role": "csm"}
    # Webhook: {"url": "...", "method": "POST", "headers": {...}}

    # Skip conditions
    skip_if_condition: Optional[dict] = None

    # Settings
    is_required: bool = True
    allow_manual_skip: bool = False
    timeout_hours: Optional[int] = None
    retry_on_failure: bool = False
    max_retries: int = Field(3, ge=0, le=10)

    is_active: bool = True


class JourneyStepCreate(JourneyStepBase):
    """Schema for creating a journey step."""

    journey_id: int


class JourneyStepUpdate(BaseModel):
    """Schema for updating a journey step."""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    step_type: Optional[JourneyStepType] = None
    step_order: Optional[int] = Field(None, ge=1)
    wait_duration_hours: Optional[int] = None
    wait_until_time: Optional[str] = None
    wait_for_event: Optional[str] = None
    condition_rules: Optional[dict] = None
    true_next_step_id: Optional[int] = None
    false_next_step_id: Optional[int] = None
    action_config: Optional[dict] = None
    skip_if_condition: Optional[dict] = None
    is_required: Optional[bool] = None
    allow_manual_skip: Optional[bool] = None
    timeout_hours: Optional[int] = None
    retry_on_failure: Optional[bool] = None
    max_retries: Optional[int] = Field(None, ge=0, le=10)
    is_active: Optional[bool] = None


class JourneyStepResponse(JourneyStepBase):
    """Journey step response schema."""

    id: int
    journey_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Journeys


class JourneyBase(BaseModel):
    """Base journey schema."""

    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    journey_type: JourneyType = JourneyType.CUSTOM
    # Note: status column may not exist in DB, use is_active instead
    status: Optional[JourneyStatus] = JourneyStatus.DRAFT
    is_active: bool = True

    # Entry triggers
    trigger_segment_id: Optional[int] = None
    trigger_event: Optional[str] = None
    trigger_on_health_drop: Optional[int] = None
    trigger_on_health_rise: Optional[int] = None

    # Entry criteria (JSON rules)
    entry_criteria: Optional[dict] = None

    # Exit criteria
    exit_on_event: Optional[str] = None
    exit_criteria: Optional[dict] = None

    # Goal tracking
    goal_event: Optional[str] = None
    goal_criteria: Optional[dict] = None

    # Settings
    allow_re_enrollment: bool = False
    re_enrollment_cooldown_days: Optional[int] = None
    max_active_enrollments: int = Field(1, ge=1)
    priority: int = Field(0, description="Higher priority journeys override lower")

    # Timing
    business_hours_only: bool = False
    timezone: str = Field("America/Chicago", max_length=50)

    # Metadata
    tags: Optional[list[str]] = None


class JourneyCreate(JourneyBase):
    """Schema for creating a journey."""

    steps: Optional[list[JourneyStepCreate]] = None


class JourneyUpdate(BaseModel):
    """Schema for updating a journey."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    journey_type: Optional[JourneyType] = None
    status: Optional[JourneyStatus] = None
    trigger_segment_id: Optional[int] = None
    trigger_event: Optional[str] = None
    trigger_on_health_drop: Optional[int] = None
    trigger_on_health_rise: Optional[int] = None
    entry_criteria: Optional[dict] = None
    exit_on_event: Optional[str] = None
    exit_criteria: Optional[dict] = None
    goal_event: Optional[str] = None
    goal_criteria: Optional[dict] = None
    allow_re_enrollment: Optional[bool] = None
    re_enrollment_cooldown_days: Optional[int] = None
    max_active_enrollments: Optional[int] = Field(None, ge=1)
    priority: Optional[int] = None
    business_hours_only: Optional[bool] = None
    timezone: Optional[str] = None
    tags: Optional[list[str]] = None


class JourneyResponse(JourneyBase):
    """Journey response schema."""

    id: int

    # Metrics (some columns may not exist in DB yet)
    total_enrolled: int = 0
    currently_active: int = 0  # DB column name
    total_completed: int = 0  # DB column name
    total_exited_early: int = 0
    avg_completion_days: Optional[float] = None
    success_rate: Optional[float] = None  # DB column name

    # Steps
    steps: list[JourneyStepResponse] = []

    # Ownership
    created_by_user_id: Optional[int] = None
    owned_by_user_id: Optional[int] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class JourneyListResponse(BaseModel):
    """Paginated journey list response."""

    items: list[JourneyResponse]
    total: int
    page: int
    page_size: int


# Journey Enrollments


class JourneyEnrollmentBase(BaseModel):
    """Base journey enrollment schema."""

    customer_id: str
    journey_id: int
    enrolled_by: Optional[str] = None
    enrollment_reason: Optional[str] = None


class JourneyEnrollmentCreate(JourneyEnrollmentBase):
    """Schema for creating a journey enrollment."""

    pass


class JourneyEnrollmentResponse(JourneyEnrollmentBase):
    """Journey enrollment response schema."""

    id: int
    status: EnrollmentStatus

    # Progress (some columns may not exist in DB yet)
    current_step_id: Optional[int] = None
    current_step_started_at: Optional[datetime] = None
    steps_completed: int = 0

    # Goal tracking
    goal_achieved: bool = False
    goal_value_at_start: Optional[float] = None
    goal_value_at_end: Optional[float] = None

    # Timing
    enrolled_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    exited_at: Optional[datetime] = None
    exit_reason: Optional[str] = None
    exit_notes: Optional[str] = None

    # Metrics
    health_score_at_start: Optional[int] = None
    health_score_at_end: Optional[int] = None

    # Enrollment source
    enrolled_by: Optional[str] = None
    enrollment_trigger: Optional[str] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class JourneyEnrollmentListResponse(BaseModel):
    """Paginated journey enrollment list response."""

    items: list[JourneyEnrollmentResponse]
    total: int
    page: int
    page_size: int


# Step Executions


class JourneyStepExecutionResponse(BaseModel):
    """Journey step execution response schema."""

    id: int
    enrollment_id: int
    step_id: int

    status: StepExecutionStatus
    attempts: int = 0

    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    result: Optional[dict] = None
    error_message: Optional[str] = None

    # For conditions
    condition_result: Optional[bool] = None
    next_step_id: Optional[int] = None

    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Enrollment Operations


class JourneyEnrollRequest(BaseModel):
    """Request to enroll a customer in a journey."""

    customer_id: str
    journey_id: int
    reason: Optional[str] = None
    start_immediately: bool = True
    skip_entry_criteria: bool = False


class JourneyBulkEnrollRequest(BaseModel):
    """Request to bulk enroll customers in a journey."""

    journey_id: int
    customer_ids: Optional[list[str]] = None
    segment_id: Optional[int] = None
    reason: Optional[str] = None
    start_immediately: bool = True
