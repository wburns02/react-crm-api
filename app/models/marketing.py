"""Marketing automation models."""
from sqlalchemy import Column, String, DateTime, Text, Integer, Boolean, JSON, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database import Base


class MarketingCampaign(Base):
    """Marketing campaign definition."""

    __tablename__ = "marketing_campaigns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    campaign_type = Column(String(50), nullable=False)  # nurture, winback, promotion, reminder

    # Targeting
    target_segment = Column(JSON, nullable=True)  # Filter criteria
    estimated_audience = Column(Integer, nullable=True)

    # Schedule
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)

    # Status
    status = Column(String(20), default="draft")  # draft, active, paused, completed

    # Metrics
    total_sent = Column(Integer, default=0)
    total_opened = Column(Integer, default=0)
    total_clicked = Column(Integer, default=0)
    total_converted = Column(Integer, default=0)

    # Timestamps
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class MarketingWorkflow(Base):
    """Automated workflow/sequence."""

    __tablename__ = "marketing_workflows"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    campaign_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Trigger
    trigger_type = Column(String(50), nullable=False)  # event, date, manual
    trigger_config = Column(JSON, nullable=True)

    # Workflow steps (JSON for flexibility)
    steps = Column(JSON, nullable=False)
    # Example: [
    #   {"type": "wait", "days": 1},
    #   {"type": "send_email", "template_id": "...", "subject": "..."},
    #   {"type": "condition", "if": {"opened": true}, "then": 3, "else": 5},
    #   {"type": "send_sms", "template": "..."},
    # ]

    # Status
    is_active = Column(Boolean, default=False)

    # Metrics
    total_enrolled = Column(Integer, default=0)
    total_completed = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class WorkflowEnrollment(Base):
    """Customer enrollment in a workflow."""

    __tablename__ = "workflow_enrollments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    workflow_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    customer_id = Column(Integer, nullable=False, index=True)

    # Progress
    current_step = Column(Integer, default=0)
    status = Column(String(20), default="active")  # active, paused, completed, exited

    # Scheduling
    next_action_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    enrolled_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)


class EmailTemplate(Base):
    """Email template for campaigns."""

    __tablename__ = "email_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    name = Column(String(255), nullable=False)
    subject = Column(String(255), nullable=False)
    body_html = Column(Text, nullable=False)
    body_text = Column(Text, nullable=True)

    # Personalization variables (JSON for SQLite test compatibility)
    variables = Column(JSON, nullable=True)  # ["first_name", "company", ...]

    # Category
    category = Column(String(50), nullable=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SMSTemplate(Base):
    """SMS template for campaigns."""

    __tablename__ = "sms_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    name = Column(String(255), nullable=False)
    body = Column(String(160), nullable=False)  # SMS length limit

    variables = Column(JSON, nullable=True)
    category = Column(String(50), nullable=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
