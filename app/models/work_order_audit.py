"""
Work Order Audit Log — tracks every change to a work order.

Each row captures: who changed what, when, from where, and the before/after values.
"""
from sqlalchemy import Column, String, DateTime, Text, ForeignKey, JSON
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
import uuid


class WorkOrderAuditLog(Base):
    __tablename__ = "work_order_audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    work_order_id = Column(UUID(as_uuid=True), ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False, index=True)

    # What happened
    action = Column(String(30), nullable=False, index=True)  # created, updated, status_changed, assigned, completed, deleted
    description = Column(Text, nullable=True)  # Human-readable summary

    # Who did it
    user_email = Column(String(100), nullable=True)
    user_name = Column(String(200), nullable=True)

    # Where it came from
    source = Column(String(50), nullable=True)  # crm, booking, customer_portal, api, employee_portal, system
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)

    # What changed (JSON: {"field": {"old": x, "new": y}, ...})
    changes = Column(JSON, nullable=True)

    # When
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self):
        return f"<WorkOrderAuditLog {self.action} on {self.work_order_id}>"
