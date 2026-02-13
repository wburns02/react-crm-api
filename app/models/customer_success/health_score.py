"""
Health Score Models for Enterprise Customer Success Platform

Tracks customer health metrics, component scores, and health events
for predictive churn analysis and proactive engagement.
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, Enum as SQLEnum, JSON
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class HealthScore(Base):
    """
    Customer health score record.

    Calculates overall health from weighted components:
    - Product Adoption (30%)
    - Engagement (25%)
    - Relationship (15%)
    - Financial (20%)
    - Support (10%)
    """

    __tablename__ = "cs_health_scores"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(PG_UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True)

    # Overall score (0-100)
    overall_score = Column(Integer, nullable=False, default=50)
    health_status = Column(
        SQLEnum("healthy", "at_risk", "critical", "churned", name="cs_health_status_enum"), default="at_risk"
    )

    # Component scores (0-100 each)
    product_adoption_score = Column(Integer, default=50)
    engagement_score = Column(Integer, default=50)
    relationship_score = Column(Integer, default=50)
    financial_score = Column(Integer, default=50)
    support_score = Column(Integer, default=50)

    # Predictive metrics
    churn_probability = Column(Float, default=0.0)  # 0.0-1.0
    expansion_probability = Column(Float, default=0.0)  # 0.0-1.0
    nps_predicted = Column(Integer)  # -100 to 100

    # Time-based metrics
    days_since_last_login = Column(Integer, default=0)
    days_to_renewal = Column(Integer)
    last_login_at = Column(DateTime(timezone=True))

    # Usage metrics
    active_users_count = Column(Integer, default=0)
    licensed_users_count = Column(Integer, default=0)
    feature_adoption_pct = Column(Float, default=0.0)

    # Trend analysis
    score_trend = Column(SQLEnum("improving", "stable", "declining", name="cs_score_trend_enum"), default="stable")
    score_change_7d = Column(Integer, default=0)
    score_change_30d = Column(Integer, default=0)

    # Risk flags
    has_open_escalation = Column(Boolean, default=False)
    champion_at_risk = Column(Boolean, default=False)
    payment_issues = Column(Boolean, default=False)

    # Calculation metadata
    calculated_at = Column(DateTime(timezone=True), server_default=func.now())
    calculation_version = Column(String(20), default="1.0")

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    customer = relationship("Customer", backref="health_scores")
    events = relationship("HealthScoreEvent", back_populates="health_score")

    def __repr__(self):
        return f"<HealthScore customer_id={self.customer_id} score={self.overall_score} status={self.health_status}>"


class HealthScoreEvent(Base):
    """
    Track health score changes and the events that caused them.

    Used for audit trail and understanding health trends.
    """

    __tablename__ = "cs_health_score_events"

    id = Column(Integer, primary_key=True, index=True)
    health_score_id = Column(Integer, ForeignKey("cs_health_scores.id"), nullable=False, index=True)
    customer_id = Column(PG_UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True)

    # Score change
    previous_score = Column(Integer)
    new_score = Column(Integer)
    score_delta = Column(Integer)

    previous_status = Column(String(20))
    new_status = Column(String(20))

    # Event details
    event_type = Column(
        SQLEnum(
            "score_calculated",
            "manual_override",
            "component_change",
            "escalation_opened",
            "escalation_closed",
            "champion_change",
            "renewal_update",
            "support_issue",
            "engagement_change",
            name="cs_health_event_type_enum",
        ),
        nullable=False,
    )
    event_source = Column(String(100))  # e.g., 'system', 'user:123', 'integration:salesforce'

    # Affected components
    affected_components = Column(JSON)  # ["product_adoption", "support"]

    # Context
    description = Column(Text)
    event_metadata = Column(JSON)

    # Timestamps
    occurred_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    health_score = relationship("HealthScore", back_populates="events")

    def __repr__(self):
        return f"<HealthScoreEvent customer_id={self.customer_id} type={self.event_type} delta={self.score_delta}>"
