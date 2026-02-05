"""Service Interval models for recurring service scheduling and reminders."""

from sqlalchemy import Column, String, DateTime, Text, Integer, Boolean, Date, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid

from app.database import Base


class ServiceInterval(Base):
    """Service interval template defining recurring service schedules."""

    __tablename__ = "service_intervals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Basic info
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    service_type = Column(String(50), nullable=False)  # pumping, grease_trap, inspection, maintenance

    # Interval configuration
    interval_months = Column(Integer, nullable=False)  # e.g., 36 for 3-year pumping
    reminder_days_before = Column(JSON, default=[30, 14, 7])  # Days before due to send reminders

    # Status
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    schedules = relationship("CustomerServiceSchedule", back_populates="service_interval", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ServiceInterval {self.name}: {self.interval_months} months>"


class CustomerServiceSchedule(Base):
    """Customer-specific service schedule assignment."""

    __tablename__ = "customer_service_schedules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Foreign keys
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True)
    service_interval_id = Column(UUID(as_uuid=True), ForeignKey("service_intervals.id"), nullable=False, index=True)

    # Schedule dates
    last_service_date = Column(Date, nullable=True)
    next_due_date = Column(Date, nullable=False, index=True)

    # Status tracking
    status = Column(String(30), default="upcoming", index=True)  # upcoming, due, overdue, scheduled, completed

    # Work order link (when scheduled)
    scheduled_work_order_id = Column(String(36), nullable=True, index=True)

    # Reminder tracking
    reminder_sent = Column(Boolean, default=False)
    last_reminder_sent_at = Column(DateTime(timezone=True), nullable=True)

    # Notes
    notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    service_interval = relationship("ServiceInterval", back_populates="schedules")
    reminders = relationship("ServiceReminder", back_populates="schedule", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<CustomerServiceSchedule customer={self.customer_id} due={self.next_due_date}>"


class ServiceReminder(Base):
    """Audit log for service reminders sent."""

    __tablename__ = "service_reminders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Foreign keys
    schedule_id = Column(UUID(as_uuid=True), ForeignKey("customer_service_schedules.id"), nullable=False, index=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True)

    # Reminder details
    reminder_type = Column(String(20), nullable=False)  # sms, email, push
    days_before_due = Column(Integer, nullable=True)  # How many days before due date this was sent

    # Status
    status = Column(String(20), default="sent")  # pending, sent, delivered, failed
    error_message = Column(Text, nullable=True)

    # Link to message record
    message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id"), nullable=True)

    # Timestamps
    sent_at = Column(DateTime(timezone=True), server_default=func.now())
    delivered_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    schedule = relationship("CustomerServiceSchedule", back_populates="reminders")

    def __repr__(self):
        return f"<ServiceReminder {self.reminder_type} schedule={self.schedule_id}>"
