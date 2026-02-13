"""
Send Time Optimization Models

Enables intelligent send time optimization for campaigns:
- Per-customer optimal send time profiles
- Campaign-level timing analysis
- Engagement pattern tracking
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class CustomerSendTimeProfile(Base):
    """
    Per-customer optimal send time profile based on historical engagement.

    Tracks engagement patterns to predict optimal send times for each customer,
    improving open rates and click-through rates for campaigns.
    """

    __tablename__ = "cs_customer_send_profiles"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(PG_UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, unique=True, index=True)

    # Optimal windows (stored as hour of day, 0-23)
    best_hour_email = Column(Integer)  # Best hour for email engagement
    best_hour_sms = Column(Integer)  # Best hour for SMS engagement

    # Day of week preferences (0=Monday, 6=Sunday)
    best_days = Column(JSON)  # e.g., [0, 1, 2, 3, 4] for weekdays

    # Engagement patterns by hour
    open_rate_by_hour = Column(JSON)  # {0: 0.12, 1: 0.08, ..., 23: 0.15}
    click_rate_by_hour = Column(JSON)  # {0: 0.05, 1: 0.03, ..., 23: 0.08}

    # Confidence score for prediction (0-100)
    confidence = Column(Float, default=0)
    # Number of messages used for calculation
    sample_size = Column(Integer, default=0)

    # Customer's timezone for send time calculations
    timezone = Column(String(50), default="America/Chicago")

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_calculated_at = Column(DateTime(timezone=True))

    # Relationships
    customer = relationship("Customer", backref="send_time_profile")

    def __repr__(self):
        return f"<CustomerSendTimeProfile id={self.id} customer_id={self.customer_id} best_hour={self.best_hour_email}>"


class CampaignSendTimeAnalysis(Base):
    """
    Campaign-level send time analysis and performance tracking.

    Aggregates timing performance data across all messages sent in a campaign
    to identify optimal send times for future campaigns.
    """

    __tablename__ = "cs_campaign_send_analysis"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("cs_campaigns.id"), nullable=False, index=True)

    # Aggregated optimal times
    recommended_hour = Column(Integer)  # Best hour based on analysis (0-23)
    recommended_days = Column(JSON)  # Best days [0=Mon, 6=Sun]

    # Performance by hour: {hour: {sent, opened, clicked, open_rate, click_rate}}
    hourly_performance = Column(JSON)

    # Performance by day: {day: {sent, opened, clicked, open_rate, click_rate}}
    daily_performance = Column(JSON)

    # Analysis metadata
    analysis_period_start = Column(DateTime(timezone=True))
    analysis_period_end = Column(DateTime(timezone=True))
    total_messages_analyzed = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    campaign = relationship("Campaign", backref="send_time_analysis")

    def __repr__(self):
        return f"<CampaignSendTimeAnalysis id={self.id} campaign_id={self.campaign_id} recommended_hour={self.recommended_hour}>"
