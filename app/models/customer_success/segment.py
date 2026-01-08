"""
Segment Models for Enterprise Customer Success Platform

Enables dynamic and static customer segmentation for targeted
engagement, journey enrollment, and playbook triggering.
"""

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text,
    ForeignKey, Enum as SQLEnum, JSON, Numeric
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class Segment(Base):
    """
    Customer segment definition.

    Supports:
    - Static segments (manually assigned)
    - Dynamic segments (rule-based, auto-updated)
    - AI-generated segments (clustering, lookalike)
    """
    __tablename__ = "cs_segments"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    color = Column(String(7), default='#3B82F6')  # Hex color for UI

    # Segment type
    segment_type = Column(
        SQLEnum('static', 'dynamic', 'ai_generated', name='cs_segment_type_enum'),
        default='dynamic'
    )

    # For dynamic segments - JSON rules
    # Example: {"and": [{"field": "health_score", "op": "lt", "value": 50}, {"field": "arr", "op": "gte", "value": 100000}]}
    rules = Column(JSON)

    # Rule evaluation
    rule_evaluation_mode = Column(
        SQLEnum('all_match', 'any_match', name='cs_rule_mode_enum'),
        default='all_match'
    )

    # AI-generated segment metadata
    ai_confidence = Column(Float)
    ai_reasoning = Column(Text)
    ai_model_version = Column(String(50))

    # Segment metrics (auto-calculated)
    customer_count = Column(Integer, default=0)
    total_arr = Column(Numeric(15, 2), default=0)
    avg_health_score = Column(Float, default=0)
    at_risk_count = Column(Integer, default=0)

    # Settings
    is_active = Column(Boolean, default=True)
    is_system = Column(Boolean, default=False)  # System segments cannot be deleted
    auto_refresh = Column(Boolean, default=True)
    refresh_interval_hours = Column(Integer, default=1)
    last_refreshed_at = Column(DateTime(timezone=True))

    # Smart segment metadata
    category = Column(String(50))  # lifecycle, value, service, engagement, geographic
    ai_insight = Column(Text)  # AI-generated insight message for this segment
    recommended_actions = Column(JSON)  # List of recommended actions for segment members

    # Priority (for overlapping segments)
    priority = Column(Integer, default=100)

    # Ownership
    created_by_user_id = Column(Integer, ForeignKey("api_users.id"))

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    customer_segments = relationship("CustomerSegment", back_populates="segment", cascade="all, delete-orphan")
    journeys = relationship("Journey", back_populates="trigger_segment")
    playbooks = relationship("Playbook", back_populates="trigger_segment")

    def __repr__(self):
        return f"<Segment id={self.id} name='{self.name}' type={self.segment_type} count={self.customer_count}>"


class CustomerSegment(Base):
    """
    Junction table linking customers to segments.

    Tracks when customers entered/exited segments for analytics.
    """
    __tablename__ = "cs_customer_segments"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    segment_id = Column(Integer, ForeignKey("cs_segments.id"), nullable=False, index=True)

    # Membership status
    is_active = Column(Boolean, default=True)

    # Entry/exit tracking
    entered_at = Column(DateTime(timezone=True), server_default=func.now())
    exited_at = Column(DateTime(timezone=True))
    entry_reason = Column(String(200))  # e.g., "health_score dropped below 50"
    exit_reason = Column(String(200))

    # For AI segments - why this customer was included
    ai_match_score = Column(Float)
    ai_match_reasons = Column(JSON)

    # Metadata
    added_by = Column(String(100))  # 'system', 'user:123', 'import'

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    segment = relationship("Segment", back_populates="customer_segments")
    customer = relationship("Customer", backref="segment_memberships")

    def __repr__(self):
        return f"<CustomerSegment customer_id={self.customer_id} segment_id={self.segment_id} active={self.is_active}>"
