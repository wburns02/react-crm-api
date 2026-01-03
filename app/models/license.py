"""License model for tracking business and technician licenses."""
from sqlalchemy import Column, String, DateTime, Text, Integer, Date, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database import Base


class License(Base):
    """Track business and technician licenses."""

    __tablename__ = "licenses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # License identification
    license_number = Column(String(100), nullable=False, index=True)
    license_type = Column(String(100), nullable=False)  # business, septic_installer, plumber, etc.

    # Issuing authority
    issuing_authority = Column(String(255), nullable=True)  # State, county, agency
    issuing_state = Column(String(2), nullable=True)

    # Holder info
    holder_type = Column(String(20), nullable=False, default="business")  # business, technician
    holder_id = Column(String(36), nullable=True, index=True)  # technician_id if applicable
    holder_name = Column(String(255), nullable=True)

    # Dates
    issue_date = Column(Date, nullable=True)
    expiry_date = Column(Date, nullable=False, index=True)

    # Status
    status = Column(String(20), default="active")  # active, expired, suspended, revoked

    # Renewal tracking
    renewal_reminder_sent = Column(Boolean, default=False)
    renewal_reminder_date = Column(Date, nullable=True)

    # Documentation
    document_url = Column(String(500), nullable=True)
    notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<License {self.license_type}: {self.license_number}>"

    @property
    def is_expired(self):
        from datetime import date
        return self.expiry_date < date.today()

    @property
    def days_until_expiry(self):
        from datetime import date
        if not self.expiry_date:
            return None
        return (self.expiry_date - date.today()).days
