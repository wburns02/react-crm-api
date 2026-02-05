"""
Touchpoint Schemas for Enterprise Customer Success Platform
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from enum import Enum

from app.schemas.types import UUIDStr


class TouchpointType(str, Enum):
    # Communication
    EMAIL_SENT = "email_sent"
    EMAIL_OPENED = "email_opened"
    EMAIL_CLICKED = "email_clicked"
    EMAIL_REPLIED = "email_replied"
    CALL_OUTBOUND = "call_outbound"
    CALL_INBOUND = "call_inbound"
    CALL_MISSED = "call_missed"
    VOICEMAIL = "voicemail"
    MEETING_SCHEDULED = "meeting_scheduled"
    MEETING_HELD = "meeting_held"
    MEETING_CANCELLED = "meeting_cancelled"
    MEETING_NO_SHOW = "meeting_no_show"
    SMS_SENT = "sms_sent"
    SMS_RECEIVED = "sms_received"
    CHAT_SESSION = "chat_session"
    VIDEO_CALL = "video_call"
    # Product
    PRODUCT_LOGIN = "product_login"
    FEATURE_USAGE = "feature_usage"
    FEATURE_ADOPTION = "feature_adoption"
    WEBINAR_REGISTERED = "webinar_registered"
    WEBINAR_ATTENDED = "webinar_attended"
    TRAINING_COMPLETED = "training_completed"
    # Support
    SUPPORT_TICKET_OPENED = "support_ticket_opened"
    SUPPORT_TICKET_RESOLVED = "support_ticket_resolved"
    SUPPORT_ESCALATION = "support_escalation"
    # Feedback
    NPS_RESPONSE = "nps_response"
    CSAT_RESPONSE = "csat_response"
    SURVEY_RESPONSE = "survey_response"
    REVIEW_POSTED = "review_posted"
    # Business
    QBR_HELD = "qbr_held"
    RENEWAL_DISCUSSION = "renewal_discussion"
    EXPANSION_DISCUSSION = "expansion_discussion"
    CONTRACT_SIGNED = "contract_signed"
    INVOICE_PAID = "invoice_paid"
    PAYMENT_ISSUE = "payment_issue"
    # Internal
    INTERNAL_NOTE = "internal_note"
    HEALTH_ALERT = "health_alert"
    RISK_FLAG = "risk_flag"
    # Other
    IN_APP_MESSAGE_SENT = "in_app_message_sent"
    IN_APP_MESSAGE_CLICKED = "in_app_message_clicked"
    DOCUMENT_SHARED = "document_shared"
    DOCUMENT_VIEWED = "document_viewed"
    EVENT_ATTENDED = "event_attended"
    REFERRAL_MADE = "referral_made"
    CUSTOM = "custom"


class TouchpointDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    INTERNAL = "internal"


class TouchpointChannel(str, Enum):
    EMAIL = "email"
    PHONE = "phone"
    VIDEO = "video"
    IN_APP = "in_app"
    IN_PERSON = "in_person"
    CHAT = "chat"
    SMS = "sms"
    SOCIAL = "social"
    WEBINAR = "webinar"
    EVENT = "event"
    OTHER = "other"


class SentimentLabel(str, Enum):
    VERY_NEGATIVE = "very_negative"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    POSITIVE = "positive"
    VERY_POSITIVE = "very_positive"


class TouchpointBase(BaseModel):
    """Base touchpoint schema."""

    touchpoint_type: TouchpointType

    # Details
    subject: Optional[str] = Field(None, max_length=255)
    summary: Optional[str] = None
    description: Optional[str] = None

    # Direction and channel
    direction: Optional[TouchpointDirection] = None
    channel: Optional[TouchpointChannel] = None

    # Our side participant
    user_id: Optional[int] = None
    user_role: Optional[str] = Field(None, max_length=50)

    # Customer side participant
    contact_name: Optional[str] = Field(None, max_length=100)
    contact_email: Optional[str] = Field(None, max_length=255)
    contact_role: Optional[str] = Field(None, max_length=100)
    contact_is_champion: bool = False
    contact_is_executive: bool = False
    attendee_count: Optional[int] = Field(None, ge=1)

    # Meeting/call specifics
    duration_minutes: Optional[int] = Field(None, ge=0)
    scheduled_duration_minutes: Optional[int] = Field(None, ge=0)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    meeting_link: Optional[str] = Field(None, max_length=500)
    recording_url: Optional[str] = Field(None, max_length=500)
    transcript_url: Optional[str] = Field(None, max_length=500)

    # Email specifics
    email_message_id: Optional[str] = Field(None, max_length=255)
    email_thread_id: Optional[str] = Field(None, max_length=255)
    email_opened_count: Optional[int] = Field(None, ge=0)
    email_click_count: Optional[int] = Field(None, ge=0)
    email_reply_received: Optional[bool] = None

    # Product usage specifics
    feature_name: Optional[str] = Field(None, max_length=100)
    usage_count: Optional[int] = Field(None, ge=0)
    usage_duration_minutes: Optional[int] = Field(None, ge=0)

    # NPS/Survey specifics
    nps_score: Optional[int] = Field(None, ge=0, le=10)
    csat_score: Optional[int] = Field(None, ge=1, le=5)
    survey_responses: Optional[dict] = None

    # Attachments
    attachments: Optional[list[dict]] = None
    notes: Optional[str] = None

    # Source tracking
    source: Optional[str] = Field(None, max_length=100)
    external_id: Optional[str] = Field(None, max_length=255)
    source_url: Optional[str] = Field(None, max_length=500)

    # Visibility
    is_internal: bool = False
    is_confidential: bool = False

    # Timestamp
    occurred_at: Optional[datetime] = None


class TouchpointCreate(TouchpointBase):
    """Schema for creating a touchpoint."""

    customer_id: UUIDStr

    # Related entities
    task_id: Optional[int] = None
    journey_enrollment_id: Optional[int] = None
    playbook_execution_id: Optional[int] = None
    support_ticket_id: Optional[str] = Field(None, max_length=100)


class TouchpointUpdate(BaseModel):
    """Schema for updating a touchpoint."""

    touchpoint_type: Optional[TouchpointType] = None
    subject: Optional[str] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    direction: Optional[TouchpointDirection] = None
    channel: Optional[TouchpointChannel] = None
    user_id: Optional[int] = None
    user_role: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_role: Optional[str] = None
    contact_is_champion: Optional[bool] = None
    contact_is_executive: Optional[bool] = None
    attendee_count: Optional[int] = None
    duration_minutes: Optional[int] = None
    scheduled_duration_minutes: Optional[int] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    meeting_link: Optional[str] = None
    recording_url: Optional[str] = None
    transcript_url: Optional[str] = None
    email_opened_count: Optional[int] = None
    email_click_count: Optional[int] = None
    email_reply_received: Optional[bool] = None
    feature_name: Optional[str] = None
    usage_count: Optional[int] = None
    usage_duration_minutes: Optional[int] = None
    nps_score: Optional[int] = None
    csat_score: Optional[int] = None
    survey_responses: Optional[dict] = None
    attachments: Optional[list[dict]] = None
    notes: Optional[str] = None
    is_internal: Optional[bool] = None
    is_confidential: Optional[bool] = None
    occurred_at: Optional[datetime] = None

    # AI sentiment (can be updated by sentiment service)
    sentiment_score: Optional[float] = Field(None, ge=-1, le=1)
    sentiment_label: Optional[SentimentLabel] = None
    sentiment_confidence: Optional[float] = Field(None, ge=0, le=1)
    key_topics: Optional[list[str]] = None
    action_items: Optional[list[str]] = None
    risk_signals: Optional[list[str]] = None
    expansion_signals: Optional[list[str]] = None
    key_quotes: Optional[list[str]] = None
    engagement_score: Optional[int] = Field(None, ge=0, le=100)
    was_positive: Optional[bool] = None


class TouchpointResponse(TouchpointBase):
    """Touchpoint response schema."""

    id: int
    customer_id: UUIDStr

    # Related entities
    task_id: Optional[int] = None
    journey_enrollment_id: Optional[int] = None
    playbook_execution_id: Optional[int] = None
    support_ticket_id: Optional[str] = None

    # AI-powered sentiment analysis
    sentiment_score: Optional[float] = None
    sentiment_label: Optional[SentimentLabel] = None
    sentiment_confidence: Optional[float] = None

    # AI-extracted insights
    key_topics: Optional[list[str]] = None
    action_items: Optional[list[str]] = None
    risk_signals: Optional[list[str]] = None
    expansion_signals: Optional[list[str]] = None
    key_quotes: Optional[list[str]] = None

    # Engagement
    engagement_score: Optional[int] = None
    was_positive: Optional[bool] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TouchpointListResponse(BaseModel):
    """Paginated touchpoint list response."""

    items: list[TouchpointResponse]
    total: int
    page: int
    page_size: int


# Sentiment Analysis


class TouchpointSentimentAnalysis(BaseModel):
    """Sentiment analysis result for a touchpoint."""

    touchpoint_id: int
    sentiment_score: float = Field(..., ge=-1, le=1)
    sentiment_label: SentimentLabel
    sentiment_confidence: float = Field(..., ge=0, le=1)
    key_topics: list[str] = []
    action_items: list[str] = []
    risk_signals: list[str] = []
    expansion_signals: list[str] = []
    key_quotes: list[str] = []
    engagement_score: int = Field(..., ge=0, le=100)
    was_positive: bool


# Timeline View


class TouchpointTimelineResponse(BaseModel):
    """Customer touchpoint timeline response."""

    customer_id: UUIDStr
    touchpoints: list[TouchpointResponse]
    total: int
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None

    # Summary stats
    total_interactions: int = 0
    positive_interactions: int = 0
    negative_interactions: int = 0
    avg_sentiment: Optional[float] = None
    most_common_type: Optional[str] = None
    most_common_channel: Optional[str] = None
    last_interaction: Optional[datetime] = None
    days_since_last_interaction: Optional[int] = None
