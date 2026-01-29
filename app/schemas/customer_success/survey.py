"""
Survey Schemas for Enterprise Customer Success Platform

2025-2026 Enhancements:
- AI analysis schemas for sentiment, themes, and recommendations
- Detractor queue and trend analysis
- Action tracking for survey follow-ups
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


class UrgencyLevel(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AnalysisStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class SurveyActionType(str, Enum):
    CALLBACK = "callback"
    TASK = "task"
    TICKET = "ticket"
    OFFER = "offer"
    ESCALATION = "escalation"
    EMAIL = "email"
    MEETING = "meeting"


class ActionPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ActionStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


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
    # 2025-2026 Enhancements
    delivery_channel: Optional[str] = None  # 'email', 'sms', 'in_app', 'multi'
    reminder_count: int = 1
    a_b_test_variant: Optional[str] = None
    conditional_logic: Optional[dict] = None  # Question branching rules


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
    # 2025-2026 Enhancements
    delivery_channel: Optional[str] = None
    reminder_count: Optional[int] = None
    a_b_test_variant: Optional[str] = None
    conditional_logic: Optional[dict] = None


class SurveyResponse(SurveyBase):
    """Survey response schema."""

    id: int
    status: SurveyStatus = SurveyStatus.DRAFT

    # Metrics
    responses_count: int = 0
    avg_score: Optional[float] = None
    completion_rate: Optional[float] = None
    response_rate: Optional[float] = None  # 2025-2026 Enhancement
    promoters_count: int = 0
    passives_count: int = 0
    detractors_count: int = 0

    # Questions
    questions: list[SurveyQuestionResponse] = []

    # Target segment name (for display)
    target_segment_name: Optional[str] = None

    # Ownership
    created_by_user_id: Optional[int] = None

    # 2025-2026 Enhancement: Reminder tracking
    last_reminder_sent: Optional[datetime] = None

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
    # 2025-2026 Enhancements
    feedback_text: Optional[str] = None
    topics_detected: Optional[list[str]] = None
    urgency_level: Optional[UrgencyLevel] = None
    action_taken: bool = False
    action_type: Optional[str] = None
    action_taken_at: Optional[datetime] = None
    action_taken_by: Optional[int] = None
    # Timestamps
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


# ============ 2025-2026 Enhancement Schemas ============

# AI Analysis Schemas


class UrgentIssue(BaseModel):
    """Individual urgent issue detected by AI."""

    text: str
    customer_id: int
    customer_name: Optional[str] = None
    severity: str  # 'critical', 'high', 'medium', 'low'
    response_id: Optional[int] = None


class ChurnRiskIndicator(BaseModel):
    """Churn risk indicator from AI analysis."""

    indicator: str  # e.g., 'competitor_mention', 'low_score', 'negative_feedback'
    weight: float  # 0 to 1
    details: Optional[str] = None
    customer_id: Optional[int] = None


class CompetitorMention(BaseModel):
    """Competitor mention detected in feedback."""

    competitor: str
    context: str
    customer_id: int
    customer_name: Optional[str] = None
    response_id: Optional[int] = None


class ActionRecommendation(BaseModel):
    """AI-generated action recommendation."""

    type: str  # 'callback', 'task', 'ticket', 'offer', 'escalation'
    customer_id: int
    customer_name: Optional[str] = None
    reason: str
    priority: str  # 'critical', 'high', 'medium', 'low'
    suggested_deadline_days: Optional[int] = None
    response_id: Optional[int] = None


class SurveyAnalysisCreate(BaseModel):
    """Request to trigger AI analysis."""

    include_individual_responses: bool = True  # Analyze each response separately
    force_reanalyze: bool = False  # Re-run even if analysis exists


class SurveyAnalysisResponse(BaseModel):
    """AI analysis results for a survey."""

    id: int
    survey_id: int
    response_id: Optional[int] = None  # null = survey-level analysis

    # Sentiment breakdown
    sentiment_breakdown: Optional[dict] = None  # {"positive": 45, "neutral": 30, "negative": 25}

    # Themes and topics
    key_themes: Optional[list[str]] = None

    # Issues and risks
    urgent_issues: Optional[list[UrgentIssue]] = None
    churn_risk_indicators: Optional[list[ChurnRiskIndicator]] = None
    competitor_mentions: Optional[list[CompetitorMention]] = None

    # Recommendations
    action_recommendations: Optional[list[ActionRecommendation]] = None

    # Scores
    overall_sentiment_score: Optional[float] = None  # -1 to 1
    churn_risk_score: Optional[float] = None  # 0 to 100
    urgency_score: Optional[float] = None  # 0 to 100

    # Summary
    executive_summary: Optional[str] = None

    # Metadata
    status: AnalysisStatus = AnalysisStatus.PENDING
    analysis_version: Optional[str] = None
    analysis_model: Optional[str] = None
    analyzed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


# Detractor Queue Schemas


class DetractorItem(BaseModel):
    """Individual detractor needing attention."""

    response_id: int
    survey_id: int
    survey_name: str
    customer_id: int
    customer_name: str
    score: float
    sentiment: Optional[Sentiment] = None
    feedback_text: Optional[str] = None
    topics_detected: Optional[list[str]] = None
    urgency_level: Optional[UrgencyLevel] = None
    action_taken: bool = False
    action_type: Optional[str] = None
    responded_at: datetime
    days_since_response: int


class DetractorQueueResponse(BaseModel):
    """Detractor queue with all detractors needing attention."""

    items: list[DetractorItem]
    total: int
    critical_count: int
    high_count: int
    action_needed_count: int  # Those without action taken


# Trend Analysis Schemas


class TrendDataPoint(BaseModel):
    """Single data point in trend analysis."""

    date: str  # ISO date string
    responses_count: int
    avg_score: Optional[float] = None
    nps_score: Optional[float] = None
    promoters: int = 0
    passives: int = 0
    detractors: int = 0
    sentiment_positive: int = 0
    sentiment_neutral: int = 0
    sentiment_negative: int = 0


class SurveyTrendResponse(BaseModel):
    """Cross-survey trend data over time."""

    period: str  # 'daily', 'weekly', 'monthly'
    start_date: str
    end_date: str
    data_points: list[TrendDataPoint]
    # Aggregate stats
    total_responses: int
    avg_nps_score: Optional[float] = None
    avg_score: Optional[float] = None
    trend_direction: str  # 'improving', 'declining', 'stable'
    # Top themes across all surveys
    top_themes: list[str] = []
    # Survey breakdown
    surveys_included: list[dict] = []  # [{"id": 1, "name": "Q1 NPS", "responses": 50}]


# Action Schemas


class SurveyActionCreate(BaseModel):
    """Create an action from survey insight."""

    response_id: Optional[int] = None
    analysis_id: Optional[int] = None
    customer_id: int
    action_type: SurveyActionType
    title: str = Field(..., min_length=1, max_length=300)
    description: Optional[str] = None
    priority: ActionPriority = ActionPriority.MEDIUM
    source: str = "manual"  # 'ai_recommendation', 'manual', 'automation'
    ai_confidence: Optional[float] = None
    assigned_to_user_id: Optional[int] = None
    due_date: Optional[datetime] = None


class SurveyActionUpdate(BaseModel):
    """Update a survey action."""

    title: Optional[str] = Field(None, min_length=1, max_length=300)
    description: Optional[str] = None
    priority: Optional[ActionPriority] = None
    assigned_to_user_id: Optional[int] = None
    status: Optional[ActionStatus] = None
    due_date: Optional[datetime] = None
    outcome: Optional[str] = None


class SurveyActionResponse(BaseModel):
    """Survey action response."""

    id: int
    survey_id: int
    response_id: Optional[int] = None
    analysis_id: Optional[int] = None
    customer_id: int
    customer_name: Optional[str] = None

    action_type: SurveyActionType
    title: str
    description: Optional[str] = None
    priority: ActionPriority
    source: str
    ai_confidence: Optional[float] = None

    assigned_to_user_id: Optional[int] = None
    assigned_to_name: Optional[str] = None
    created_by_user_id: Optional[int] = None
    created_by_name: Optional[str] = None

    status: ActionStatus
    due_date: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    outcome: Optional[str] = None

    linked_entity_type: Optional[str] = None
    linked_entity_id: Optional[int] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SurveyActionListResponse(BaseModel):
    """Paginated list of survey actions."""

    items: list[SurveyActionResponse]
    total: int
    page: int
    page_size: int


# ============ 2025-2026 Advanced Survey Builder Schemas ============

# Conditional Logic Schemas


class LogicOperator(str, Enum):
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    GREATER_OR_EQUAL = "greater_or_equal"
    LESS_OR_EQUAL = "less_or_equal"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    IS_ANSWERED = "is_answered"
    IS_NOT_ANSWERED = "is_not_answered"


class LogicAction(str, Enum):
    SHOW = "show"
    HIDE = "hide"
    SKIP_TO = "skip_to"
    END_SURVEY = "end_survey"


class ConditionalLogicRule(BaseModel):
    """Single conditional logic rule for survey questions."""

    id: str
    source_question_id: str
    operator: LogicOperator
    value: Optional[Any] = None  # Can be string, number, or list
    action: LogicAction
    target_question_id: Optional[str] = None  # Required for SKIP_TO action
    logic_group: Optional[str] = "and"  # 'and' or 'or' for chaining rules


class ConditionalLogicConfig(BaseModel):
    """Full conditional logic configuration for a question."""

    question_id: str
    rules: list[ConditionalLogicRule] = []
    default_visible: bool = True


# A/B Test Schemas


class ABTestMetric(str, Enum):
    RESPONSE_RATE = "response_rate"
    COMPLETION_RATE = "completion_rate"
    NPS_SCORE = "nps_score"
    CSAT_SCORE = "csat_score"


class ABTestVariant(BaseModel):
    """A/B test variant configuration."""

    id: str
    name: str
    subject: Optional[str] = None
    changes: Optional[dict] = None  # Key-value of what differs in this variant
    traffic_percentage: int = 50


class ABTestConfig(BaseModel):
    """Full A/B test configuration for a survey."""

    enabled: bool = False
    variants: list[ABTestVariant] = []
    test_metric: ABTestMetric = ABTestMetric.RESPONSE_RATE
    traffic_split: list[int] = []  # Percentage for each variant
    auto_select_winner: bool = True
    winner_threshold: float = 95.0  # Statistical confidence threshold
    test_duration_days: int = 7


class ABTestResults(BaseModel):
    """Results from an A/B test."""

    survey_id: int
    variant_results: list[dict] = []  # [{"variant_id": "a", "responses": 100, "score": 8.5}]
    winning_variant_id: Optional[str] = None
    confidence_level: Optional[float] = None
    is_conclusive: bool = False
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None


# Delivery Settings Schemas


class DeliveryChannel(str, Enum):
    EMAIL = "email"
    SMS = "sms"
    IN_APP = "in_app"
    WEBHOOK = "webhook"


class DeliveryTimingType(str, Enum):
    IMMEDIATE = "immediate"
    SCHEDULED = "scheduled"
    EVENT_TRIGGERED = "event_triggered"
    RECURRING = "recurring"


class ChannelConfig(BaseModel):
    """Configuration for a single delivery channel."""

    enabled: bool = False
    # Email specific
    subject: Optional[str] = None
    preview_text: Optional[str] = None
    sender_name: Optional[str] = None
    sender_email: Optional[str] = None
    # SMS specific
    phone_number: Optional[str] = None
    # In-app specific
    position: Optional[str] = None  # 'bottom-right', 'bottom-left', 'center', 'slide-in'
    # Webhook specific
    webhook_url: Optional[str] = None


class RecurringSchedule(BaseModel):
    """Recurring schedule configuration."""

    frequency: str  # 'daily', 'weekly', 'monthly', 'quarterly'
    day_of_week: Optional[int] = None  # 0-6 for weekly
    day_of_month: Optional[int] = None  # 1-31 for monthly
    time: str = "10:00"  # HH:MM format


class DeliveryTiming(BaseModel):
    """Survey delivery timing configuration."""

    type: DeliveryTimingType = DeliveryTimingType.SCHEDULED
    scheduled_date: Optional[str] = None
    scheduled_time: Optional[str] = None
    timezone: Optional[str] = None
    event_trigger: Optional[str] = None
    delay_hours: Optional[int] = None
    recurring_schedule: Optional[RecurringSchedule] = None
    optimal_time_enabled: bool = False


class ReminderConfig(BaseModel):
    """Survey reminder configuration."""

    enabled: bool = True
    max_reminders: int = 2
    reminder_intervals: list[int] = [3, 7]  # Days after initial send
    reminder_subject: Optional[str] = None
    stop_on_response: bool = True


class FatigueSettings(BaseModel):
    """Survey fatigue prevention settings."""

    enabled: bool = True
    min_days_between_surveys: int = 30
    max_surveys_per_month: int = 2
    respect_opt_out: bool = True
    exclude_recently_churned: bool = True
    exclude_new_customers_days: int = 14


class DeliverySettings(BaseModel):
    """Complete survey delivery configuration."""

    channels: dict[str, ChannelConfig] = {}  # Channel name -> config
    timing: DeliveryTiming = DeliveryTiming()
    ab_test: Optional[ABTestConfig] = None
    reminders: ReminderConfig = ReminderConfig()
    fatigue: FatigueSettings = FatigueSettings()
    target_segment_id: Optional[int] = None
    exclude_segment_ids: list[int] = []


# Survey Template Schemas


class SurveyTemplateQuestion(BaseModel):
    """Question template for survey templates."""

    id: str
    type: QuestionType
    text: str
    required: bool = False
    options: Optional[list[str]] = None
    scale_min: Optional[int] = None
    scale_max: Optional[int] = None
    scale_labels: Optional[dict] = None  # {"min": "...", "max": "..."}
    placeholder: Optional[str] = None
    max_length: Optional[int] = None
    conditional_logic: Optional[list[ConditionalLogicRule]] = None


class SurveyTemplateCreate(BaseModel):
    """Create a survey template."""

    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    survey_type: SurveyType = SurveyType.CUSTOM
    questions: list[SurveyTemplateQuestion] = []
    delivery_settings: Optional[DeliverySettings] = None
    tags: list[str] = []
    is_public: bool = False  # Available to all users


class SurveyTemplateUpdate(BaseModel):
    """Update a survey template."""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    survey_type: Optional[SurveyType] = None
    questions: Optional[list[SurveyTemplateQuestion]] = None
    delivery_settings: Optional[DeliverySettings] = None
    tags: Optional[list[str]] = None
    is_public: Optional[bool] = None


class SurveyTemplateResponse(BaseModel):
    """Survey template response."""

    id: int
    name: str
    description: Optional[str] = None
    survey_type: SurveyType
    questions: list[SurveyTemplateQuestion] = []
    delivery_settings: Optional[DeliverySettings] = None
    tags: list[str] = []
    is_public: bool = False

    # Usage stats
    times_used: int = 0

    # Ownership
    created_by_user_id: Optional[int] = None
    created_by_name: Optional[str] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SurveyTemplateListResponse(BaseModel):
    """Paginated list of survey templates."""

    items: list[SurveyTemplateResponse]
    total: int
    page: int
    page_size: int


# Survey Eligibility Check Schema


class SurveyEligibilityResponse(BaseModel):
    """Response for survey eligibility check."""

    eligible: bool
    reason: str
    next_eligible_date: Optional[str] = None
    recent_surveys: list[dict] = []  # [{"survey_id": 1, "name": "...", "responded_at": "..."}]
    fatigue_score: Optional[float] = None  # 0-100, higher = more fatigued
    opt_out: bool = False
    customer_status: Optional[str] = None  # 'active', 'churned', 'new'
