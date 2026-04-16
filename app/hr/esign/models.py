from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.sql import func

from app.database import Base


_INET = INET().with_variant(String(45), "sqlite")


class HrDocumentTemplate(Base):
    __tablename__ = "hr_document_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    kind = Column(String(64), unique=True, nullable=False)
    version = Column(String(32), nullable=False, default="1")
    pdf_storage_key = Column(String(512), nullable=False)
    fields = Column(JSON, default=list, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class HrSignatureRequest(Base):
    __tablename__ = "hr_signature_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    token = Column(String(64), unique=True, nullable=False)
    signer_email = Column(String(256), nullable=False)
    signer_name = Column(String(256), nullable=False)
    signer_user_id = Column(Integer, ForeignKey("api_users.id"), nullable=True)
    document_template_id = Column(
        UUID(as_uuid=True),
        ForeignKey("hr_document_templates.id"),
        nullable=False,
    )
    field_values = Column(JSON, default=dict, nullable=False)
    status = Column(String(16), default="sent", nullable=False)
    sent_at = Column(DateTime, server_default=func.now(), nullable=False)
    viewed_at = Column(DateTime, nullable=True)
    signed_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=False)
    workflow_task_id = Column(
        UUID(as_uuid=True), ForeignKey("hr_workflow_tasks.id"), nullable=True
    )

    __table_args__ = (Index("ix_hr_sig_requests_status", "status"),)


class HrSignedDocument(Base):
    __tablename__ = "hr_signed_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    signature_request_id = Column(
        UUID(as_uuid=True),
        ForeignKey("hr_signature_requests.id"),
        nullable=False,
    )
    storage_key = Column(String(512), nullable=False)
    signer_ip = Column(_INET, nullable=True)
    signer_user_agent = Column(Text, nullable=True)
    signature_image_key = Column(String(512), nullable=False)
    signed_at = Column(DateTime, server_default=func.now(), nullable=False)
    hash_sha256 = Column(String(64), nullable=False)


class HrSignatureEvent(Base):
    __tablename__ = "hr_signature_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    signature_request_id = Column(
        UUID(as_uuid=True),
        ForeignKey("hr_signature_requests.id"),
        nullable=False,
    )
    event_type = Column(String(32), nullable=False)
    ip = Column(_INET, nullable=True)
    user_agent = Column(Text, nullable=True)
    payload = Column(JSON, default=dict)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
