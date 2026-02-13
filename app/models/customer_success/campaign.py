"""
Campaign Models for Enterprise Customer Success Platform

Enables nurture campaigns, engagement sequences, and automated outreach:
- Multi-channel campaigns (email, in-app, SMS)
- Drip sequences with timing controls
- Campaign analytics and performance tracking
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, Enum as SQLEnum, JSON
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class Campaign(Base):
    """
    Customer engagement campaign definition.
    """

    __tablename__ = "cs_campaigns"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)

    # Campaign type
    campaign_type = Column(
        SQLEnum(
            "nurture",
            "onboarding",
            "adoption",
            "renewal",
            "expansion",
            "winback",
            "custom",
            name="cs_campaign_type_enum",
        ),
        default="nurture",
    )

    # Status
    status = Column(
        SQLEnum("draft", "active", "paused", "completed", "archived", name="cs_campaign_status_enum"), default="draft"
    )

    # Target audience
    target_segment_id = Column(Integer, ForeignKey("cs_segments.id"))
    target_criteria = Column(JSON)  # Additional filter criteria

    # Channel configuration
    primary_channel = Column(
        SQLEnum("email", "in_app", "sms", "multi_channel", name="cs_campaign_channel_enum"), default="email"
    )

    # Schedule
    start_date = Column(DateTime(timezone=True))
    end_date = Column(DateTime(timezone=True))
    timezone = Column(String(50), default="UTC")

    # Campaign settings
    is_recurring = Column(Boolean, default=False)
    recurrence_pattern = Column(String(50))  # 'daily', 'weekly', 'monthly'
    allow_re_enrollment = Column(Boolean, default=False)
    max_enrollments_per_customer = Column(Integer, default=1)

    # Goals
    goal_type = Column(String(50))  # 'engagement', 'conversion', 'retention'
    goal_metric = Column(String(100))  # e.g., 'feature_adoption_rate'
    goal_target = Column(Float)  # Target value

    # Metrics (auto-calculated)
    enrolled_count = Column(Integer, default=0)
    active_count = Column(Integer, default=0)
    completed_count = Column(Integer, default=0)
    converted_count = Column(Integer, default=0)
    conversion_rate = Column(Float, default=0)
    avg_engagement_score = Column(Float)

    # Ownership
    created_by_user_id = Column(Integer, ForeignKey("api_users.id"))
    owned_by_user_id = Column(Integer, ForeignKey("api_users.id"))

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    launched_at = Column(DateTime(timezone=True))

    # Relationships
    steps = relationship(
        "CampaignStep", back_populates="campaign", cascade="all, delete-orphan", order_by="CampaignStep.order"
    )
    enrollments = relationship("CampaignEnrollment", back_populates="campaign", cascade="all, delete-orphan")
    target_segment = relationship("Segment", foreign_keys=[target_segment_id])

    def __repr__(self):
        return f"<Campaign id={self.id} name='{self.name}' type={self.campaign_type}>"


class CampaignStep(Base):
    """
    Individual step/message in a campaign sequence.
    """

    __tablename__ = "cs_campaign_steps"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("cs_campaigns.id"), nullable=False, index=True)

    name = Column(String(200), nullable=False)
    description = Column(Text)

    # Step type
    step_type = Column(
        SQLEnum("email", "in_app_message", "sms", "task", "wait", "condition", name="cs_step_type_enum"), nullable=False
    )

    # Order in sequence
    order = Column(Integer, default=0)

    # Timing
    delay_days = Column(Integer, default=0)
    delay_hours = Column(Integer, default=0)
    send_at_time = Column(String(5))  # 'HH:MM' format
    send_on_days = Column(JSON)  # [1,2,3,4,5] for Mon-Fri

    # Content (for message steps)
    subject = Column(String(500))
    content = Column(Text)
    content_html = Column(Text)
    cta_text = Column(String(100))
    cta_url = Column(String(500))

    # For condition steps
    condition_rules = Column(JSON)  # Branching logic

    # Metrics
    sent_count = Column(Integer, default=0)
    delivered_count = Column(Integer, default=0)
    opened_count = Column(Integer, default=0)
    clicked_count = Column(Integer, default=0)
    open_rate = Column(Float)
    click_rate = Column(Float)

    # Settings
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    campaign = relationship("Campaign", back_populates="steps")
    executions = relationship("CampaignStepExecution", back_populates="step", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<CampaignStep id={self.id} name='{self.name}' type={self.step_type}>"


class CampaignEnrollment(Base):
    """
    Customer enrollment in a campaign.
    """

    __tablename__ = "cs_campaign_enrollments"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("cs_campaigns.id"), nullable=False, index=True)
    customer_id = Column(PG_UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True)

    # Status
    status = Column(
        SQLEnum(
            "active", "paused", "completed", "converted", "unsubscribed", "exited", name="cs_enrollment_status_enum"
        ),
        default="active",
    )

    # Progress tracking
    current_step_id = Column(Integer, ForeignKey("cs_campaign_steps.id"))
    steps_completed = Column(Integer, default=0)
    next_step_scheduled_at = Column(DateTime(timezone=True))

    # Engagement metrics for this enrollment
    messages_sent = Column(Integer, default=0)
    messages_opened = Column(Integer, default=0)
    messages_clicked = Column(Integer, default=0)
    engagement_score = Column(Float)

    # Conversion tracking
    converted_at = Column(DateTime(timezone=True))
    conversion_value = Column(Float)

    # Exit tracking
    exit_reason = Column(String(200))
    exited_at = Column(DateTime(timezone=True))

    # Timestamps
    enrolled_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True))

    # Relationships
    campaign = relationship("Campaign", back_populates="enrollments")
    customer = relationship("Customer", backref="campaign_enrollments")
    current_step = relationship("CampaignStep", foreign_keys=[current_step_id])
    step_executions = relationship("CampaignStepExecution", back_populates="enrollment", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<CampaignEnrollment id={self.id} campaign_id={self.campaign_id} customer_id={self.customer_id}>"


class CampaignStepExecution(Base):
    """
    Record of a campaign step being executed for a customer.
    """

    __tablename__ = "cs_campaign_step_executions"

    id = Column(Integer, primary_key=True, index=True)
    enrollment_id = Column(Integer, ForeignKey("cs_campaign_enrollments.id"), nullable=False, index=True)
    step_id = Column(Integer, ForeignKey("cs_campaign_steps.id"), nullable=False, index=True)

    # Execution status
    status = Column(
        SQLEnum("pending", "sent", "delivered", "opened", "clicked", "failed", "skipped", name="cs_exec_status_enum"),
        default="pending",
    )

    # Delivery tracking
    scheduled_at = Column(DateTime(timezone=True))
    sent_at = Column(DateTime(timezone=True))
    delivered_at = Column(DateTime(timezone=True))
    opened_at = Column(DateTime(timezone=True))
    clicked_at = Column(DateTime(timezone=True))

    # Error handling
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)

    # External IDs (from email provider, etc.)
    external_id = Column(String(200))

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    enrollment = relationship("CampaignEnrollment", back_populates="step_executions")
    step = relationship("CampaignStep", back_populates="executions")

    def __repr__(self):
        return f"<CampaignStepExecution id={self.id} step_id={self.step_id} status={self.status}>"
