"""
Escalation Models for Enterprise Customer Success Platform

Enables escalation management and tracking:
- Escalation creation and routing
- Severity levels and SLAs
- Resolution tracking
- Stakeholder notifications
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, Enum as SQLEnum, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class Escalation(Base):
    """
    Customer escalation record.
    """

    __tablename__ = "cs_escalations"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)

    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=False)

    # Escalation type
    escalation_type = Column(
        SQLEnum(
            "technical",
            "billing",
            "service",
            "product",
            "relationship",
            "executive",
            "custom",
            name="cs_escalation_type_enum",
        ),
        default="service",
    )

    # Severity/Priority
    severity = Column(SQLEnum("low", "medium", "high", "critical", name="cs_severity_enum"), default="medium")

    priority = Column(Integer, default=50)  # 1-100, higher = more urgent

    # Status
    status = Column(
        SQLEnum(
            "open",
            "in_progress",
            "pending_customer",
            "pending_internal",
            "resolved",
            "closed",
            name="cs_escalation_status_enum",
        ),
        default="open",
    )

    # Source
    source = Column(String(100))  # 'support_ticket', 'csm_flagged', 'customer_request', 'health_alert'
    source_id = Column(Integer)  # Reference to source record (e.g., ticket ID)

    # Assignment
    assigned_to_user_id = Column(Integer, ForeignKey("api_users.id"))
    escalated_by_user_id = Column(Integer, ForeignKey("api_users.id"))
    escalated_to_user_id = Column(Integer, ForeignKey("api_users.id"))  # Manager/exec escalated to

    # SLA tracking
    sla_hours = Column(Integer, default=24)  # Resolution SLA in hours
    sla_deadline = Column(DateTime(timezone=True))
    sla_breached = Column(Boolean, default=False)
    first_response_at = Column(DateTime(timezone=True))
    first_response_sla_hours = Column(Integer, default=4)
    first_response_breached = Column(Boolean, default=False)

    # Impact assessment
    revenue_at_risk = Column(Float)
    churn_probability = Column(Float)
    impact_description = Column(Text)

    # Root cause
    root_cause_category = Column(String(100))
    root_cause_description = Column(Text)

    # Resolution
    resolution_summary = Column(Text)
    resolution_category = Column(String(100))  # 'fixed', 'workaround', 'wont_fix', 'duplicate'
    customer_satisfaction = Column(Integer)  # 1-5 rating from customer

    # Tags and categorization
    tags = Column(JSON)  # ["urgent", "enterprise", "renewal_risk"]

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    resolved_at = Column(DateTime(timezone=True))
    closed_at = Column(DateTime(timezone=True))

    # Relationships
    customer = relationship("Customer", backref="escalations")
    assigned_to = relationship("User", foreign_keys=[assigned_to_user_id], backref="assigned_escalations")
    escalated_by = relationship("User", foreign_keys=[escalated_by_user_id])
    escalated_to = relationship("User", foreign_keys=[escalated_to_user_id])
    notes = relationship(
        "EscalationNote",
        back_populates="escalation",
        cascade="all, delete-orphan",
        order_by="EscalationNote.created_at.desc()",
    )
    activities = relationship(
        "EscalationActivity",
        back_populates="escalation",
        cascade="all, delete-orphan",
        order_by="EscalationActivity.created_at.desc()",
    )

    def __repr__(self):
        return f"<Escalation id={self.id} title='{self.title[:30]}...' severity={self.severity}>"


class EscalationNote(Base):
    """
    Internal notes on an escalation.
    """

    __tablename__ = "cs_escalation_notes"

    id = Column(Integer, primary_key=True, index=True)
    escalation_id = Column(Integer, ForeignKey("cs_escalations.id"), nullable=False, index=True)

    content = Column(Text, nullable=False)

    # Note type
    note_type = Column(
        SQLEnum("update", "internal", "customer_communication", "resolution", name="cs_note_type_enum"),
        default="update",
    )

    # Visibility
    is_internal = Column(Boolean, default=True)  # If false, visible to customer

    # Author
    created_by_user_id = Column(Integer, ForeignKey("api_users.id"))

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    escalation = relationship("Escalation", back_populates="notes")
    created_by = relationship("User", backref="escalation_notes")

    def __repr__(self):
        return f"<EscalationNote id={self.id} escalation_id={self.escalation_id}>"


class EscalationActivity(Base):
    """
    Activity log for escalation tracking.
    """

    __tablename__ = "cs_escalation_activities"

    id = Column(Integer, primary_key=True, index=True)
    escalation_id = Column(Integer, ForeignKey("cs_escalations.id"), nullable=False, index=True)

    # Activity details
    activity_type = Column(String(50), nullable=False)  # 'status_change', 'assignment_change', 'severity_change', etc.
    description = Column(Text)

    # Change tracking
    old_value = Column(String(500))
    new_value = Column(String(500))

    # Who performed the action
    performed_by_user_id = Column(Integer, ForeignKey("api_users.id"))

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    escalation = relationship("Escalation", back_populates="activities")
    performed_by = relationship("User", backref="escalation_activities")

    def __repr__(self):
        return f"<EscalationActivity id={self.id} type={self.activity_type}>"
