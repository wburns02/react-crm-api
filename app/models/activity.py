"""Activity model for tracking customer interactions."""

from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Enum, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
import enum

from app.database import Base


class ActivityType(str, enum.Enum):
    """Types of customer activities."""

    CALL = "call"
    EMAIL = "email"
    SMS = "sms"
    NOTE = "note"
    MEETING = "meeting"
    TASK = "task"


class Activity(Base):
    """Activity model for customer interaction tracking."""

    __tablename__ = "activities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    activity_type = Column(String(20), nullable=False, index=True)  # call, email, sms, note, meeting, task
    description = Column(Text, nullable=False)
    activity_date = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(String(100), nullable=True)  # User who created the activity
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Activity {self.activity_type} for customer {self.customer_id}>"
