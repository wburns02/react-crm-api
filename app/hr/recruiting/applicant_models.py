from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.sql import func

from app.database import Base


_INET = INET().with_variant(String(45), "sqlite")


class HrApplicant(Base):
    __tablename__ = "hr_applicants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    first_name = Column(String(128), nullable=False)
    last_name = Column(String(128), nullable=False)
    email = Column(String(256), nullable=False)
    phone = Column(String(32), nullable=True)
    resume_storage_key = Column(String(512), nullable=True)
    resume_parsed = Column(JSON, nullable=True)
    source = Column(String(32), nullable=False, default="careers_page")
    source_ref = Column(String(256), nullable=True)
    sms_consent_given = Column(Boolean, nullable=False, default=False)
    sms_consent_ip = Column(_INET, nullable=True)
    sms_consent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_hr_applicants_email", "email"),
        Index("ix_hr_applicants_created_at", "created_at"),
    )


class HrApplication(Base):
    __tablename__ = "hr_applications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    applicant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("hr_applicants.id", ondelete="CASCADE"),
        nullable=False,
    )
    requisition_id = Column(
        UUID(as_uuid=True), ForeignKey("hr_requisitions.id"), nullable=False
    )
    stage = Column(String(16), nullable=False, default="applied")
    stage_entered_at = Column(DateTime, server_default=func.now(), nullable=False)
    assigned_recruiter_id = Column(Integer, ForeignKey("api_users.id"), nullable=True)
    rejection_reason = Column(String(256), nullable=True)
    rating = Column(SmallInteger, nullable=True)
    answers = Column(JSON, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, onupdate=func.now(), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "applicant_id", "requisition_id", name="uq_hr_applications_applicant_req"
        ),
        Index("ix_hr_applications_requisition_stage", "requisition_id", "stage"),
        Index("ix_hr_applications_stage", "stage"),
    )


class HrApplicationEvent(Base):
    __tablename__ = "hr_application_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    application_id = Column(
        UUID(as_uuid=True),
        ForeignKey("hr_applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type = Column(String(32), nullable=False)
    user_id = Column(Integer, ForeignKey("api_users.id"), nullable=True)
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        Index(
            "ix_hr_application_events_application_created",
            "application_id",
            "created_at",
        ),
    )


class HrRecruitingMessageTemplate(Base):
    __tablename__ = "hr_recruiting_message_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    stage = Column(String(16), nullable=False, unique=True)
    channel = Column(String(16), nullable=False, default="sms")
    body = Column(Text, nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    updated_at = Column(DateTime, onupdate=func.now(), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
