"""Notification model for in-app notifications."""

from sqlalchemy import Column, String, DateTime, Text, Integer, Boolean, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database import Base


class Notification(Base):
    """In-app notification for users."""

    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Target user
    user_id = Column(Integer, ForeignKey("api_users.id"), nullable=False, index=True)

    # Notification content
    type = Column(
        String(50), nullable=False, index=True
    )  # work_order, payment, customer, system, schedule, message, alert
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)

    # Status
    read = Column(Boolean, default=False, index=True)
    read_at = Column(DateTime(timezone=True), nullable=True)

    # Action link (URL to navigate to)
    link = Column(String(500), nullable=True)

    # Additional context
    metadata = Column(JSON, nullable=True)  # entity_id, entity_type, etc.

    # Source
    source = Column(String(50), nullable=True)  # system, user, webhook, scheduler

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    def __repr__(self):
        return f"<Notification {self.type}: {self.title[:30]}>"
