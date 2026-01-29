"""Ticket model for support/service ticket tracking."""

from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database import Base


class Ticket(Base):
    """Ticket model for customer support/service requests."""

    __tablename__ = "tickets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    work_order_id = Column(String(36), ForeignKey("work_orders.id"), nullable=True, index=True)

    # Ticket details
    subject = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String(50), nullable=True)  # complaint, request, inquiry, feedback

    # Status tracking
    status = Column(String(30), default="open", index=True)  # open, in_progress, pending, resolved, closed
    priority = Column(String(20), default="normal")  # low, normal, high, urgent

    # Assignment
    assigned_to = Column(String(100), nullable=True)  # User email or name

    # Resolution
    resolution = Column(Text, nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Ticket {self.id} - {self.subject[:30]}>"
