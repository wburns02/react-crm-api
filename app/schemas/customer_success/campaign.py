"""
Campaign Schemas for Enterprise Customer Success Platform
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Any
from enum import Enum


class CampaignType(str, Enum):
    NURTURE = "nurture"
    ONBOARDING = "onboarding"
    ADOPTION = "adoption"
    RENEWAL = "renewal"
    EXPANSION = "expansion"
    WINBACK = "winback"
    CUSTOM = "custom"


class CampaignStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class CampaignChannel(str, Enum):
    EMAIL = "email"
    IN_APP = "in_app"
    SMS = "sms"
    MULTI_CHANNEL = "multi_channel"


class StepType(str, Enum):
    EMAIL = "email"
    IN_APP_MESSAGE = "in_app_message"
    SMS = "sms"
    TASK = "task"
    WAIT = "wait"
    CONDITION = "condition"


class EnrollmentStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CONVERTED = "converted"
    UNSUBSCRIBED = "unsubscribed"
    EXITED = "exited"


class ExecutionStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    OPENED = "opened"
    CLICKED = "clicked"
    FAILED = "failed"
    SKIPPED = "skipped"


# Campaign Step Schemas

class CampaignStepBase(BaseModel):
    """Base campaign step schema."""
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    step_type: StepType
    order: int = 0
    delay_days: int = 0
    delay_hours: int = 0
    send_at_time: Optional[str] = None  # 'HH:MM'
    send_on_days: Optional[list[int]] = None  # [1,2,3,4,5]
    subject: Optional[str] = None
    content: Optional[str] = None
    content_html: Optional[str] = None
    cta_text: Optional[str] = None
    cta_url: Optional[str] = None
    condition_rules: Optional[dict] = None
    is_active: bool = True


class CampaignStepCreate(CampaignStepBase):
    """Schema for creating a campaign step."""
    pass


class CampaignStepUpdate(BaseModel):
    """Schema for updating a campaign step."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    step_type: Optional[StepType] = None
    order: Optional[int] = None
    delay_days: Optional[int] = None
    delay_hours: Optional[int] = None
    send_at_time: Optional[str] = None
    send_on_days: Optional[list[int]] = None
    subject: Optional[str] = None
    content: Optional[str] = None
    content_html: Optional[str] = None
    cta_text: Optional[str] = None
    cta_url: Optional[str] = None
    condition_rules: Optional[dict] = None
    is_active: Optional[bool] = None


class CampaignStepResponse(CampaignStepBase):
    """Campaign step response."""
    id: int
    campaign_id: int
    sent_count: int = 0
    delivered_count: int = 0
    opened_count: int = 0
    clicked_count: int = 0
    open_rate: Optional[float] = None
    click_rate: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Campaign Schemas

class CampaignBase(BaseModel):
    """Base campaign schema."""
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    campaign_type: CampaignType = CampaignType.NURTURE
    primary_channel: CampaignChannel = CampaignChannel.EMAIL
    target_segment_id: Optional[int] = None
    target_criteria: Optional[dict] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    timezone: str = "UTC"
    is_recurring: bool = False
    recurrence_pattern: Optional[str] = None
    allow_re_enrollment: bool = False
    max_enrollments_per_customer: int = 1
    goal_type: Optional[str] = None
    goal_metric: Optional[str] = None
    goal_target: Optional[float] = None


class CampaignCreate(CampaignBase):
    """Schema for creating a campaign."""
    steps: Optional[list[CampaignStepCreate]] = None


class CampaignUpdate(BaseModel):
    """Schema for updating a campaign."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    campaign_type: Optional[CampaignType] = None
    status: Optional[CampaignStatus] = None
    primary_channel: Optional[CampaignChannel] = None
    target_segment_id: Optional[int] = None
    target_criteria: Optional[dict] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    timezone: Optional[str] = None
    is_recurring: Optional[bool] = None
    recurrence_pattern: Optional[str] = None
    allow_re_enrollment: Optional[bool] = None
    max_enrollments_per_customer: Optional[int] = None
    goal_type: Optional[str] = None
    goal_metric: Optional[str] = None
    goal_target: Optional[float] = None


class CampaignResponse(CampaignBase):
    """Campaign response schema."""
    id: int
    status: CampaignStatus = CampaignStatus.DRAFT

    # Metrics
    enrolled_count: int = 0
    active_count: int = 0
    completed_count: int = 0
    converted_count: int = 0
    conversion_rate: float = 0
    avg_engagement_score: Optional[float] = None

    # Steps
    steps: list[CampaignStepResponse] = []

    # Segment name
    target_segment_name: Optional[str] = None

    # Ownership
    created_by_user_id: Optional[int] = None
    owned_by_user_id: Optional[int] = None

    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    launched_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CampaignListResponse(BaseModel):
    """Paginated campaign list response."""
    items: list[CampaignResponse]
    total: int
    page: int
    page_size: int


# Enrollment Schemas

class CampaignEnrollmentCreate(BaseModel):
    """Schema for enrolling a customer."""
    customer_id: int


class CampaignEnrollmentUpdate(BaseModel):
    """Schema for updating an enrollment."""
    status: Optional[EnrollmentStatus] = None
    exit_reason: Optional[str] = None


class CampaignEnrollmentResponse(BaseModel):
    """Campaign enrollment response."""
    id: int
    campaign_id: int
    customer_id: int
    customer_name: Optional[str] = None
    status: EnrollmentStatus = EnrollmentStatus.ACTIVE
    current_step_id: Optional[int] = None
    steps_completed: int = 0
    next_step_scheduled_at: Optional[datetime] = None
    messages_sent: int = 0
    messages_opened: int = 0
    messages_clicked: int = 0
    engagement_score: Optional[float] = None
    converted_at: Optional[datetime] = None
    conversion_value: Optional[float] = None
    exit_reason: Optional[str] = None
    exited_at: Optional[datetime] = None
    enrolled_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class EnrollmentListResponse(BaseModel):
    """Paginated enrollment list response."""
    items: list[CampaignEnrollmentResponse]
    total: int
    page: int
    page_size: int


# Step Execution Schemas

class StepExecutionResponse(BaseModel):
    """Step execution response."""
    id: int
    enrollment_id: int
    step_id: int
    status: ExecutionStatus = ExecutionStatus.PENDING
    scheduled_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    clicked_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Campaign Analytics

class CampaignAnalytics(BaseModel):
    """Campaign analytics response."""
    campaign_id: int
    total_enrolled: int = 0
    total_completed: int = 0
    total_converted: int = 0
    conversion_rate: float = 0
    avg_engagement_score: Optional[float] = None
    messages_sent: int = 0
    messages_opened: int = 0
    messages_clicked: int = 0
    open_rate: Optional[float] = None
    click_rate: Optional[float] = None
    step_performance: list[dict] = []  # Per-step metrics
    enrollment_trend: list[dict] = []  # [{date, enrollments, completions}]
