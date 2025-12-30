"""E-Signature model for digital document signing."""
from sqlalchemy import Column, String, DateTime, Text, Integer, Boolean, LargeBinary
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database import Base


class SignatureRequest(Base):
    """Document signature request."""

    __tablename__ = "signature_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Document reference
    document_type = Column(String(50), nullable=False)  # quote, contract, work_order
    document_id = Column(String(36), nullable=False, index=True)

    # Customer info
    customer_id = Column(Integer, nullable=False, index=True)
    signer_name = Column(String(255), nullable=False)
    signer_email = Column(String(255), nullable=False)
    signer_phone = Column(String(20), nullable=True)

    # Request details
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=True)  # Custom message to signer

    # Security
    access_token = Column(String(100), unique=True, nullable=False, index=True)
    ip_address = Column(String(45), nullable=True)  # For audit
    user_agent = Column(String(500), nullable=True)

    # Status tracking
    status = Column(String(30), default="pending", index=True)  # pending, viewed, signed, expired, cancelled
    sent_at = Column(DateTime(timezone=True), nullable=True)
    viewed_at = Column(DateTime(timezone=True), nullable=True)
    signed_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Reminders
    reminder_count = Column(Integer, default=0)
    last_reminder_at = Column(DateTime(timezone=True), nullable=True)

    # Created by
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<SignatureRequest {self.document_type}:{self.document_id} - {self.status}>"


class Signature(Base):
    """Captured signature data."""

    __tablename__ = "signatures"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Link to request
    request_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Signature data
    signature_data = Column(Text, nullable=False)  # Base64 encoded image or SVG path
    signature_type = Column(String(20), default="drawn")  # drawn, typed, uploaded

    # Signer info at time of signing (for audit)
    signer_name = Column(String(255), nullable=False)
    signer_email = Column(String(255), nullable=False)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    geolocation = Column(String(100), nullable=True)  # Optional GPS coords

    # Legal consent
    consent_text = Column(Text, nullable=True)  # Text they agreed to
    consent_accepted = Column(Boolean, default=True)

    # Timestamps
    signed_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<Signature {self.id} by {self.signer_name}>"


class SignedDocument(Base):
    """Completed signed document with embedded signature."""

    __tablename__ = "signed_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # References
    request_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    signature_id = Column(UUID(as_uuid=True), nullable=False)
    document_type = Column(String(50), nullable=False)
    document_id = Column(String(36), nullable=False, index=True)
    customer_id = Column(Integer, nullable=False, index=True)

    # Document storage
    pdf_url = Column(String(500), nullable=True)  # S3/storage URL
    pdf_hash = Column(String(64), nullable=True)  # SHA256 for integrity

    # Audit trail
    audit_log = Column(Text, nullable=True)  # JSON audit trail

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<SignedDocument {self.document_type}:{self.document_id}>"
