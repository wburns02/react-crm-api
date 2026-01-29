"""
Touchpoint Model for Enterprise Customer Success Platform

Records all customer interactions for 360-degree visibility
and sentiment analysis.
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, Enum as SQLEnum, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class Touchpoint(Base):
    """
    Customer touchpoint/interaction record.

    Captures all meaningful interactions with customers:
    - Communications (email, call, meeting)
    - Product usage events
    - Support interactions
    - Feedback/surveys
    """

    __tablename__ = "cs_touchpoints"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)

    # Touchpoint type
    touchpoint_type = Column(
        SQLEnum(
            # Communication
            "email_sent",
            "email_opened",
            "email_clicked",
            "email_replied",
            "call_outbound",
            "call_inbound",
            "call_missed",
            "voicemail",
            "meeting_scheduled",
            "meeting_held",
            "meeting_cancelled",
            "meeting_no_show",
            "sms_sent",
            "sms_received",
            "chat_session",
            "video_call",
            # Product
            "product_login",
            "feature_usage",
            "feature_adoption",
            "webinar_registered",
            "webinar_attended",
            "training_completed",
            # Support
            "support_ticket_opened",
            "support_ticket_resolved",
            "support_escalation",
            # Feedback
            "nps_response",
            "csat_response",
            "survey_response",
            "review_posted",
            # Business
            "qbr_held",
            "renewal_discussion",
            "expansion_discussion",
            "contract_signed",
            "invoice_paid",
            "payment_issue",
            # Internal
            "internal_note",
            "health_alert",
            "risk_flag",
            # Other
            "in_app_message_sent",
            "in_app_message_clicked",
            "document_shared",
            "document_viewed",
            "event_attended",
            "referral_made",
            "custom",
            name="cs_touchpoint_type_enum",
        ),
        nullable=False,
    )

    # Details
    subject = Column(String(255))
    summary = Column(Text)
    description = Column(Text)

    # Direction and channel
    direction = Column(SQLEnum("inbound", "outbound", "internal", name="cs_touchpoint_direction_enum"))
    channel = Column(
        SQLEnum(
            "email",
            "phone",
            "video",
            "in_app",
            "in_person",
            "chat",
            "sms",
            "social",
            "webinar",
            "event",
            "other",
            name="cs_touchpoint_channel_enum",
        )
    )

    # Participants - our side
    user_id = Column(Integer, ForeignKey("api_users.id"), index=True)
    user_role = Column(String(50))  # 'csm', 'manager', 'executive', 'support'

    # Participants - customer side
    contact_name = Column(String(100))
    contact_email = Column(String(255))
    contact_role = Column(String(100))
    contact_is_champion = Column(Boolean, default=False)
    contact_is_executive = Column(Boolean, default=False)
    attendee_count = Column(Integer)

    # Sentiment analysis (AI-powered)
    sentiment_score = Column(Float)  # -1.0 to 1.0
    sentiment_label = Column(
        SQLEnum("very_negative", "negative", "neutral", "positive", "very_positive", name="cs_sentiment_enum")
    )
    sentiment_confidence = Column(Float)

    # AI-extracted insights
    key_topics = Column(JSON)  # ["pricing", "feature_request", "competitor"]
    action_items = Column(JSON)  # ["Follow up on pricing", "Schedule demo"]
    risk_signals = Column(JSON)  # ["mentioned competitor", "budget concerns"]
    expansion_signals = Column(JSON)  # ["interested in new module", "adding users"]
    key_quotes = Column(JSON)  # Important verbatim quotes

    # Engagement metrics
    engagement_score = Column(Integer)  # 0-100 for this interaction
    was_positive = Column(Boolean)

    # Related entities
    task_id = Column(Integer, ForeignKey("cs_tasks.id"))
    journey_enrollment_id = Column(Integer, ForeignKey("cs_journey_enrollments.id"))
    playbook_execution_id = Column(Integer, ForeignKey("cs_playbook_executions.id"))
    support_ticket_id = Column(String(100))

    # Meeting/call specifics
    duration_minutes = Column(Integer)
    scheduled_duration_minutes = Column(Integer)
    start_time = Column(DateTime(timezone=True))
    end_time = Column(DateTime(timezone=True))
    meeting_link = Column(String(500))
    recording_url = Column(String(500))
    transcript_url = Column(String(500))

    # Email specifics
    email_message_id = Column(String(255))
    email_thread_id = Column(String(255))
    email_opened_count = Column(Integer)
    email_click_count = Column(Integer)
    email_reply_received = Column(Boolean)

    # Product usage specifics
    feature_name = Column(String(100))
    usage_count = Column(Integer)
    usage_duration_minutes = Column(Integer)

    # NPS/Survey specifics
    nps_score = Column(Integer)  # 0-10
    csat_score = Column(Integer)  # 1-5
    survey_responses = Column(JSON)

    # Attachments/artifacts
    attachments = Column(JSON)  # [{"name": "...", "url": "...", "type": "..."}]
    notes = Column(Text)

    # Source tracking
    source = Column(String(100))  # 'manual', 'email_sync', 'calendar_sync', 'integration:salesforce'
    external_id = Column(String(255))  # ID in source system
    source_url = Column(String(500))  # Link to source

    # Visibility
    is_internal = Column(Boolean, default=False)
    is_confidential = Column(Boolean, default=False)

    # Timestamps
    occurred_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    customer = relationship("Customer", backref="touchpoints")
    user = relationship("User", backref="touchpoints")
    task = relationship("CSTask", back_populates="touchpoints")

    def __repr__(self):
        return f"<Touchpoint id={self.id} customer_id={self.customer_id} type={self.touchpoint_type}>"
