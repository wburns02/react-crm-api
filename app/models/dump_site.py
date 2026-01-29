"""Dump site models for tracking disposal locations and fees."""
from sqlalchemy import Column, String, DateTime, Text, Float, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database import Base


class DumpSite(Base):
    """Dump site for waste disposal with location-specific fees."""

    __tablename__ = "dump_sites"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Site information
    name = Column(String(255), nullable=False)

    # Address
    address_line1 = Column(String(255), nullable=True)
    address_city = Column(String(100), nullable=True)
    address_state = Column(String(2), nullable=False, index=True)  # TX, SC, TN, etc.
    address_postal_code = Column(String(20), nullable=True)

    # Location
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    # Fee structure
    fee_per_gallon = Column(Float, nullable=False)  # e.g., 0.07 for 7 cents/gallon

    # Status
    is_active = Column(Boolean, default=True)

    # Notes
    notes = Column(Text, nullable=True)

    # Contact info
    contact_name = Column(String(100), nullable=True)
    contact_phone = Column(String(20), nullable=True)

    # Hours of operation (e.g., "Mon-Fri 7AM-5PM", "24/7")
    hours_of_operation = Column(String(255), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
