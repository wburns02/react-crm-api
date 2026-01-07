"""
Survey Schemas for Enterprise Customer Success Platform
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Any
from enum import Enum


class SurveyType(str, Enum):
    NPS = "nps"
    CSAT = "csat"
    CES = "ces"
    CUSTOM = "custom"


class SurveyStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


class SurveyTrigger(str, Enum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    EVENT = "event"
    MILESTONE = "milestone"


class QuestionType(str, Enum):
    RATING = "rating"
    SCALE = "scale"
    TEXT = "text"
    MULTIPLE_CHOICE = "multiple_choice"
    SINGLE_CHOICE = "single_choice"


class Sentiment(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


# Survey Question Schemas

class SurveyQuestionBase(BaseModel):
    """Base survey question schema."""
    text: str = Field(..., min_length=1)
    description: Optional[str] = None
    question_type: QuestionType
    order: int = 0
    is_required: bool = True
    scale_min: Optional[int] = 0
    scale_max: Optional[int] = 10
    scale_min_label: Optional[str] = None
    scale_max_label: Optional[str] = None
    options: Optional[list[str]] = None


class SurveyQuestionCreate(SurveyQuestionBase):
    """Schema for creating a question."""
    pass


class SurveyQuestionUpdate(BaseModel):
    """Schema for updating a question."""
    text: Optional[str] = None
    description: Optional[str] = None
    question_type: Optional[QuestionType] = None
    order: Optional[int] = None
    is_required: Optional[bool] = None
    scale_min: Optional[int] = None
    scale_max: Optional[int] = None
    scale_min_label: Optional[str] = None
    scale_max_label: Optional[str] = None
    options: Optional[list[str]] = None


class SurveyQuestionResponse(SurveyQuestionBase):
    """Survey question response."""
    id: int
    survey_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Survey Schemas

class SurveyBase(BaseModel):
    """Base survey schema."""
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    survey_type: SurveyType = SurveyType.NPS
    trigger_type: SurveyTrigger = SurveyTrigger.MANUAL
    scheduled_at: Optional[datetime] = None
    schedule_recurrence: Optional[str] = None
    trigger_event: Optional[str] = None
    target_segment_id: Optional[int] = None
    is_anonymous: bool = False
    allow_multiple_responses: bool = False
    send_reminder: bool = True
    reminder_days: int = 3


class SurveyCreate(SurveyBase):
    """Schema for creating a survey."""
    questions: Optional[list[SurveyQuestionCreate]] = None


class SurveyUpdate(BaseModel):
    """Schema for updating a survey."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    survey_type: Optional[SurveyType] = None
    status: Optional[SurveyStatus] = None
    trigger_type: Optional[SurveyTrigger] = None
    scheduled_at: Optional[datetime] = None
    schedule_recurrence: Optional[str] = None
    trigger_event: Optional[str] = None
    target_segment_id: Optional[int] = None
    is_anonymous: Optional[bool] = None
    allow_multiple_responses: Optional[bool] = None
    send_reminder: Optional[bool] = None
    reminder_days: Optional[int] = None


class SurveyResponse(SurveyBase):
    """Survey response schema."""
    id: int
    status: SurveyStatus = SurveyStatus.DRAFT

    # Metrics
    responses_count: int = 0
    avg_score: Optional[float] = None
    completion_rate: Optional[float] = None
    promoters_count: int = 0
    passives_count: int = 0
    detractors_count: int = 0

    # Questions
    questions: list[SurveyQuestionResponse] = []

    # Target segment name (for display)
    target_segment_name: Optional[str] = None

    # Ownership
    created_by_user_id: Optional[int] = None

    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SurveyListResponse(BaseModel):
    """Paginated survey list response."""
    items: list[SurveyResponse]
    total: int
    page: int
    page_size: int


# Survey Response (from customer) Schemas

class SurveyAnswerCreate(BaseModel):
    """Schema for creating a survey answer."""
    question_id: int
    rating_value: Optional[int] = None
    text_value: Optional[str] = None
    choice_values: Optional[list[str]] = None


class SurveySubmissionCreate(BaseModel):
    """Schema for submitting a survey response."""
    customer_id: int
    answers: list[SurveyAnswerCreate]
    source: Optional[str] = None
    device: Optional[str] = None


class SurveyAnswerResponse(BaseModel):
    """Survey answer response."""
    id: int
    question_id: int
    rating_value: Optional[int] = None
    text_value: Optional[str] = None
    choice_values: Optional[list[str]] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SurveySubmissionResponse(BaseModel):
    """Survey submission response."""
    id: int
    survey_id: int
    customer_id: int
    customer_name: Optional[str] = None
    overall_score: Optional[float] = None
    sentiment: Optional[Sentiment] = None
    sentiment_score: Optional[float] = None
    is_complete: bool = False
    answers: list[SurveyAnswerResponse] = []
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SurveyResponseListResponse(BaseModel):
    """Paginated survey response list."""
    items: list[SurveySubmissionResponse]
    total: int
    page: int
    page_size: int


# Survey Analytics

class NPSBreakdown(BaseModel):
    """NPS breakdown stats."""
    promoters: int = 0
    passives: int = 0
    detractors: int = 0
    nps_score: float = 0
    total_responses: int = 0


class SurveyAnalytics(BaseModel):
    """Survey analytics response."""
    survey_id: int
    total_responses: int = 0
    avg_score: Optional[float] = None
    completion_rate: Optional[float] = None
    nps_breakdown: Optional[NPSBreakdown] = None
    response_trend: list[dict] = []  # [{"date": "2026-01-01", "count": 10, "avg_score": 8.5}]
    question_stats: list[dict] = []  # Per-question statistics
