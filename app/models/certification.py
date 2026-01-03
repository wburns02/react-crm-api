"""Certification model for tracking technician certifications."""
from sqlalchemy import Column, String, DateTime, Text, Integer, Date, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database import Base


class Certification(Base):
    """Track technician certifications and training."""

    __tablename__ = "certifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Certification info
    name = Column(String(255), nullable=False)
    certification_type = Column(String(100), nullable=False)  # safety, equipment, specialty
    certification_number = Column(String(100), nullable=True)

    # Issuing authority
    issuing_organization = Column(String(255), nullable=True)

    # Holder (technician)
    technician_id = Column(String(36), nullable=False, index=True)
    technician_name = Column(String(255), nullable=True)

    # Dates
    issue_date = Column(Date, nullable=True)
    expiry_date = Column(Date, nullable=True, index=True)

    # Status
    status = Column(String(20), default="active")  # active, expired, suspended

    # Renewal tracking
    renewal_reminder_sent = Column(Boolean, default=False)
    requires_renewal = Column(Boolean, default=True)
    renewal_interval_months = Column(Integer, nullable=True)  # e.g., 12 for annual

    # Training details
    training_hours = Column(Integer, nullable=True)
    training_date = Column(Date, nullable=True)
    training_provider = Column(String(255), nullable=True)

    # Documentation
    document_url = Column(String(500), nullable=True)
    notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Certification {self.name} - {self.technician_name}>"

    @property
    def is_expired(self):
        from datetime import date
        if not self.expiry_date:
            return False
        return self.expiry_date < date.today()

    @property
    def days_until_expiry(self):
        from datetime import date
        if not self.expiry_date:
            return None
        return (self.expiry_date - date.today()).days
