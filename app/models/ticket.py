"""Ticket model for internal project/feature ticket tracking."""

from sqlalchemy import Column, String, DateTime, Text, Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database import Base


class Ticket(Base):
    """Ticket model for internal project management and feature tracking."""

    __tablename__ = "tickets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Optional link to customer/work order
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True, index=True)
    work_order_id = Column(UUID(as_uuid=True), ForeignKey("work_orders.id"), nullable=True, index=True)

    # Ticket details
    title = Column(String(255), nullable=True)  # Frontend uses title
    subject = Column(String(255), nullable=True)  # Legacy field
    description = Column(Text, nullable=False)
    type = Column(String(50), nullable=True)  # bug, feature, support, task
    category = Column(String(50), nullable=True)  # Legacy: complaint, request, inquiry, feedback

    # Status tracking
    status = Column(String(30), default="open", index=True)
    priority = Column(String(20), default="medium")

    # RICE scoring
    reach = Column(Float, nullable=True)
    impact = Column(Float, nullable=True)
    confidence = Column(Float, nullable=True)
    effort = Column(Float, nullable=True)
    rice_score = Column(Float, nullable=True)

    # Assignment
    assigned_to = Column(String(100), nullable=True)

    # Resolution
    resolution = Column(Text, nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        display = self.title or self.subject or "Untitled"
        return f"<Ticket {self.id} - {display[:30]}>"
