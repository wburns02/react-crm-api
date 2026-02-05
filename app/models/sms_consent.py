from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base
import uuid


class SMSConsent(Base):
    """SMS Consent model for TCPA compliance tracking."""

    __tablename__ = "sms_consent"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True)
    phone_number = Column(String(20), nullable=False, index=True)

    # Consent status
    consent_status = Column(String(20), default="pending")  # opted_in, opted_out, pending
    consent_source = Column(String(50))  # web_form, verbal, sms_keyword, import

    # Opt-in details
    opt_in_timestamp = Column(DateTime(timezone=True))
    opt_in_ip_address = Column(String(45))
    double_opt_in_confirmed = Column(Boolean, default=False)
    double_opt_in_timestamp = Column(DateTime(timezone=True))

    # Opt-out details
    opt_out_timestamp = Column(DateTime(timezone=True))
    opt_out_reason = Column(String(100))

    # Compliance
    tcpa_disclosure_version = Column(String(20))
    tcpa_disclosure_accepted = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    customer = relationship("Customer", backref="sms_consents")

    def __repr__(self):
        return f"<SMSConsent {self.phone_number} {self.consent_status}>"


class SMSConsentAudit(Base):
    """Audit log for SMS consent changes."""

    __tablename__ = "sms_consent_audit"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    consent_id = Column(UUID(as_uuid=True), ForeignKey("sms_consent.id"), nullable=False, index=True)

    # Audit details
    action = Column(String(30), nullable=False)  # opt_in, opt_out, update, verify
    previous_status = Column(String(20))
    new_status = Column(String(20))

    # Request details
    ip_address = Column(String(45))
    user_agent = Column(Text)
    performed_by = Column(String(100))  # User ID or 'system' or 'customer'

    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    consent = relationship("SMSConsent", backref="audit_logs")

    def __repr__(self):
        return f"<SMSConsentAudit {self.action} {self.created_at}>"
