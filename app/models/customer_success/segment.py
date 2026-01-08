"""
Segment Models for Enterprise Customer Success Platform

World-class segmentation engine enabling:
- Dynamic and static customer segmentation
- Nested segments (segment of segments)
- Exclusion rules (in A but not in B)
- Historical membership tracking with snapshots
- AI-generated segments with clustering and lookalike
"""

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text,
    ForeignKey, Enum as SQLEnum, JSON, Numeric, Index, UniqueConstraint
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
    - Nested segments (composite from other segments)
    """
    __tablename__ = "cs_segments"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    color = Column(String(7), default='#3B82F6')  # Hex color for UI
    icon = Column(String(50))  # Icon name for UI

    # Segment type
    segment_type = Column(
        SQLEnum('static', 'dynamic', 'ai_generated', 'nested', name='cs_segment_type_enum'),
        default='dynamic'
    )

    # Is this a system-defined segment (protected from deletion)
    is_system = Column(Boolean, default=False)

    # For dynamic segments - JSON rules using advanced rule format
    # Example: {
    #   "logic": "and",
    #   "rules": [
    #     {"field": "health_score", "operator": "less_than", "value": 50},
    #     {"field": "customer_type", "operator": "equals", "value": "enterprise"},
    #     {
    #       "logic": "or",
    #       "rules": [
    #         {"field": "total_spent", "operator": "greater_than", "value": 10000},
    #         {"field": "visit_count", "operator": "greater_than", "value": 5}
    #       ]
    #     }
    #   ],
    #   "include_segments": [2, 5],  # Include customers from these segments
    #   "exclude_segments": [3]       # Exclude customers in these segments
    # }
    rules_json = Column(JSON)

    # Legacy rules field for backward compatibility
    rules = Column(JSON)

    # For nested segments - reference to parent segments
    include_segment_ids = Column(JSON)  # [1, 2, 3] - union of these segments
    exclude_segment_ids = Column(JSON)  # [4, 5] - exclude customers in these

    # Rule evaluation mode (for backward compatibility)
    rule_evaluation_mode = Column(
        SQLEnum('all_match', 'any_match', name='cs_rule_mode_enum'),
        default='all_match'
    )

    # AI-generated segment metadata
    ai_confidence = Column(Float)
    ai_reasoning = Column(Text)
    ai_model_version = Column(String(50))
    ai_cluster_id = Column(Integer)  # For clustering-based segments

    # Smart segment metadata
    category = Column(String(50))  # lifecycle, value, service, engagement, geographic
    ai_insight = Column(Text)  # AI-generated insight message for this segment
    recommended_actions = Column(JSON)  # List of recommended actions for segment members

    # Segment metrics (auto-calculated)
    customer_count = Column(Integer, default=0)
    total_arr = Column(Numeric(15, 2), default=0)
    avg_health_score = Column(Float, default=0)
    at_risk_count = Column(Integer, default=0)
    avg_lifetime_value = Column(Numeric(15, 2), default=0)
    revenue_opportunity = Column(Numeric(15, 2), default=0)  # AI-estimated

    # Settings
    is_active = Column(Boolean, default=True)
    auto_refresh = Column(Boolean, default=True)
    refresh_interval_hours = Column(Integer, default=1)
    last_refreshed_at = Column(DateTime(timezone=True))
    next_refresh_at = Column(DateTime(timezone=True))

    # Priority (for overlapping segments)
    priority = Column(Integer, default=100)

    # Tags for organization
    tags = Column(JSON)  # ["high-value", "enterprise", "at-risk"]

    # Actions on entry/exit
    on_entry_playbook_id = Column(Integer, ForeignKey("cs_playbooks.id", ondelete="SET NULL"))
    on_entry_journey_id = Column(Integer, ForeignKey("cs_journeys.id", ondelete="SET NULL"))
    on_exit_playbook_id = Column(Integer, ForeignKey("cs_playbooks.id", ondelete="SET NULL"))
    on_exit_journey_id = Column(Integer, ForeignKey("cs_journeys.id", ondelete="SET NULL"))

    # Ownership
    created_by_user_id = Column(Integer, ForeignKey("api_users.id"))
    owned_by_user_id = Column(Integer, ForeignKey("api_users.id"))

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    segment_rules = relationship("SegmentRule", back_populates="segment", cascade="all, delete-orphan")
    memberships = relationship("SegmentMembership", back_populates="segment", cascade="all, delete-orphan")
    snapshots = relationship("SegmentSnapshot", back_populates="segment", cascade="all, delete-orphan")
    customer_segments = relationship("CustomerSegment", back_populates="segment", cascade="all, delete-orphan")
    journeys = relationship("Journey", back_populates="trigger_segment", foreign_keys="Journey.trigger_segment_id")
    playbooks = relationship("Playbook", back_populates="trigger_segment", foreign_keys="Playbook.trigger_segment_id")

    def __repr__(self):
        return f"<Segment id={self.id} name='{self.name}' type={self.segment_type} count={self.customer_count}>"


class SegmentRule(Base):
    """
    Individual segment rule for structured rule storage.

    While rules can be stored as JSON in Segment.rules_json for flexibility,
    this table provides normalized storage for better querying and indexing.
    """
    __tablename__ = "cs_segment_rules"

    id = Column(Integer, primary_key=True, index=True)
    segment_id = Column(Integer, ForeignKey("cs_segments.id", ondelete="CASCADE"), nullable=False, index=True)

    # Rule grouping (for nested logic)
    parent_rule_id = Column(Integer, ForeignKey("cs_segment_rules.id", ondelete="CASCADE"))
    group_logic = Column(
        SQLEnum('and', 'or', name='cs_rule_logic_enum'),
        default='and'
    )
    rule_order = Column(Integer, default=0)  # Order within parent group

    # Field specification
    field = Column(String(100), nullable=False)  # e.g., "health_score", "customer.city", "last_service_date"
    field_type = Column(String(50))  # "customer", "health", "behavioral", "financial", "service"

    # Operator
    operator = Column(
        SQLEnum(
            # Equality
            'equals', 'not_equals',
            # Comparison
            'greater_than', 'less_than', 'greater_than_or_equals', 'less_than_or_equals',
            'between',
            # String
            'contains', 'not_contains', 'starts_with', 'ends_with',
            # List
            'in_list', 'not_in_list',
            # Null checks
            'is_empty', 'is_not_empty',
            # Date relative
            'days_ago', 'weeks_ago', 'months_ago',
            'in_last_n_days', 'in_last_n_weeks', 'in_last_n_months',
            'before_date', 'after_date',
            # Relative periods
            'this_week', 'this_month', 'this_quarter', 'this_year',
            'last_week', 'last_month', 'last_quarter', 'last_year',
            name='cs_rule_operator_enum'
        ),
        nullable=False
    )

    # Value (stored as JSON for flexibility with different types)
    value = Column(JSON)  # Single value, array, or range object {"min": x, "max": y}

    # Second value for 'between' operator
    value_end = Column(JSON)

    # Negation flag
    is_negated = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    segment = relationship("Segment", back_populates="segment_rules")
    child_rules = relationship("SegmentRule", backref="parent_rule", remote_side=[id])

    def __repr__(self):
        return f"<SegmentRule id={self.id} segment_id={self.segment_id} {self.field} {self.operator} {self.value}>"


class SegmentMembership(Base):
    """
    Tracks segment membership with entry/exit history.

    Provides comprehensive audit trail for when customers enter and exit segments.
    """
    __tablename__ = "cs_segment_memberships"

    id = Column(Integer, primary_key=True, index=True)
    segment_id = Column(Integer, ForeignKey("cs_segments.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)

    # Current status
    is_active = Column(Boolean, default=True, index=True)

    # Entry tracking
    entered_at = Column(DateTime(timezone=True), server_default=func.now())
    entry_reason = Column(Text)  # "Matched rule: health_score < 50"
    entry_source = Column(String(50))  # 'rule_match', 'manual', 'import', 'ai_suggestion'
    entry_triggered_by = Column(String(100))  # Field that triggered entry

    # Exit tracking
    exited_at = Column(DateTime(timezone=True))
    exit_reason = Column(Text)  # "No longer matches: health_score increased to 65"
    exit_source = Column(String(50))  # 'rule_mismatch', 'manual', 'segment_deleted'
    exit_triggered_by = Column(String(100))  # Field that triggered exit

    # State at entry (for analytics)
    health_score_at_entry = Column(Integer)
    customer_type_at_entry = Column(String(50))
    total_spent_at_entry = Column(Numeric(15, 2))

    # For AI segments - why this customer was included
    ai_match_score = Column(Float)  # 0-1 confidence
    ai_match_reasons = Column(JSON)  # ["Similar to cluster center", "High propensity score"]

    # Duration tracking
    total_membership_seconds = Column(Integer)  # Cumulative time in segment

    # Metadata
    added_by_user_id = Column(Integer, ForeignKey("api_users.id"))

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    segment = relationship("Segment", back_populates="memberships")
    customer = relationship("Customer", backref="segment_memberships_v2")

    # Indexes for performance
    __table_args__ = (
        Index('ix_segment_membership_active', 'segment_id', 'is_active'),
        Index('ix_segment_membership_customer_active', 'customer_id', 'is_active'),
    )

    def __repr__(self):
        return f"<SegmentMembership segment_id={self.segment_id} customer_id={self.customer_id} active={self.is_active}>"


class SegmentSnapshot(Base):
    """
    Point-in-time snapshot of segment membership and metrics.

    Used for:
    - Tracking segment size over time
    - Comparing segment evolution
    - Auditing and compliance
    - Historical reporting
    """
    __tablename__ = "cs_segment_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    segment_id = Column(Integer, ForeignKey("cs_segments.id", ondelete="CASCADE"), nullable=False, index=True)

    # When the snapshot was taken
    snapshot_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # Member count at snapshot time
    member_count = Column(Integer, nullable=False)
    previous_count = Column(Integer)  # Count from previous snapshot
    count_change = Column(Integer)  # Difference from previous

    # Aggregate metrics at snapshot time
    total_arr = Column(Numeric(15, 2))
    avg_health_score = Column(Float)
    median_health_score = Column(Float)
    min_health_score = Column(Integer)
    max_health_score = Column(Integer)
    at_risk_count = Column(Integer)
    healthy_count = Column(Integer)
    critical_count = Column(Integer)

    # Financial metrics
    total_lifetime_value = Column(Numeric(15, 2))
    avg_lifetime_value = Column(Numeric(15, 2))
    total_revenue_opportunity = Column(Numeric(15, 2))

    # Churn/expansion metrics
    avg_churn_probability = Column(Float)
    avg_expansion_probability = Column(Float)

    # Member movement
    members_entered = Column(Integer, default=0)  # New since last snapshot
    members_exited = Column(Integer, default=0)  # Left since last snapshot

    # Extended metadata
    metadata_json = Column(JSON)  # {
    #   "top_entry_reasons": [...],
    #   "top_exit_reasons": [...],
    #   "health_distribution": {"healthy": 40, "at_risk": 30, "critical": 10},
    #   "customer_type_distribution": {...},
    #   "geo_distribution": {...}
    # }

    # Snapshot type
    snapshot_type = Column(
        SQLEnum('scheduled', 'manual', 'on_change', name='cs_snapshot_type_enum'),
        default='scheduled'
    )

    # Who/what triggered the snapshot
    triggered_by = Column(String(100))  # 'scheduler', 'user:123', 'rule_change'

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    segment = relationship("Segment", back_populates="snapshots")

    # Indexes
    __table_args__ = (
        Index('ix_segment_snapshot_time', 'segment_id', 'snapshot_at'),
    )

    def __repr__(self):
        return f"<SegmentSnapshot segment_id={self.segment_id} at={self.snapshot_at} count={self.member_count}>"


class CustomerSegment(Base):
    """
    Junction table linking customers to segments (legacy compatibility).

    This maintains backward compatibility with existing code while
    SegmentMembership provides richer tracking.
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
