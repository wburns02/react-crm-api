from uuid import uuid4

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class HrRequisition(Base):
    __tablename__ = "hr_requisitions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    slug = Column(String(128), unique=True, nullable=False)
    title = Column(String(200), nullable=False)
    department = Column(String(128), nullable=True)
    location_city = Column(String(128), nullable=True)
    location_state = Column(String(32), nullable=True)
    employment_type = Column(String(32), nullable=False, default="full_time")
    compensation_min = Column(Numeric(10, 2), nullable=True)
    compensation_max = Column(Numeric(10, 2), nullable=True)
    compensation_display = Column(String(64), nullable=True)
    description_md = Column(Text, nullable=True)
    requirements_md = Column(Text, nullable=True)
    benefits_md = Column(Text, nullable=True)
    status = Column(String(16), nullable=False, default="draft")
    opened_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    hiring_manager_id = Column(Integer, ForeignKey("api_users.id"), nullable=True)
    onboarding_template_id = Column(
        UUID(as_uuid=True), ForeignKey("hr_workflow_templates.id"), nullable=True
    )
    created_by = Column(Integer, ForeignKey("api_users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, onupdate=func.now(), nullable=True)

    __table_args__ = (Index("ix_hr_requisitions_status", "status"),)
