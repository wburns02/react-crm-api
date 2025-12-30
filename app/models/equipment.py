"""Equipment model for tracking customer equipment (septic tanks, pumps, etc.)."""
from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Integer, Float, Date
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database import Base


class Equipment(Base):
    """Equipment model for customer equipment tracking."""

    __tablename__ = "equipment"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)

    # Equipment details
    equipment_type = Column(String(100), nullable=False, index=True)  # septic_tank, pump, drain_field, grease_trap
    manufacturer = Column(String(100), nullable=True)
    model = Column(String(100), nullable=True)
    serial_number = Column(String(100), nullable=True)

    # Capacity/Size
    capacity_gallons = Column(Integer, nullable=True)
    size_description = Column(String(255), nullable=True)

    # Installation
    install_date = Column(Date, nullable=True)
    installed_by = Column(String(100), nullable=True)

    # Warranty
    warranty_expiry = Column(Date, nullable=True)
    warranty_notes = Column(Text, nullable=True)

    # Service tracking
    last_service_date = Column(Date, nullable=True)
    next_service_date = Column(Date, nullable=True)
    service_interval_months = Column(Integer, nullable=True)

    # Location on property
    location_description = Column(String(255), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    # Condition and notes
    condition = Column(String(50), nullable=True)  # excellent, good, fair, poor, needs_replacement
    notes = Column(Text, nullable=True)

    # Status
    is_active = Column(String(10), default="active")  # active, inactive, decommissioned

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Equipment {self.id} - {self.equipment_type}>"
