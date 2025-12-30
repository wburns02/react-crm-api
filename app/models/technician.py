from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Float, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class Technician(Base):
    """Technician model for field service technicians."""

    __tablename__ = "technicians"

    # Flask uses VARCHAR(36) UUID for technician IDs
    id = Column(String(36), primary_key=True, index=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(255), index=True)
    phone = Column(String(20))
    employee_id = Column(String(50), unique=True, index=True)
    is_active = Column(Boolean, default=True)

    # Home location
    home_region = Column(String(100))
    home_address = Column(String(255))
    home_city = Column(String(100))
    home_state = Column(String(50))
    home_postal_code = Column(String(20))
    home_latitude = Column(Float)
    home_longitude = Column(Float)

    # Skills (stored as JSON array)
    skills = Column(JSON, default=list)

    # Vehicle info
    assigned_vehicle = Column(String(100))
    vehicle_capacity_gallons = Column(Float)

    # Licensing
    license_number = Column(String(100))
    license_expiry = Column(String(20))  # ISO date string

    # Payroll
    hourly_rate = Column(Float)

    # Notes
    notes = Column(Text)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Note: WorkOrder relationship will be added when technician_id FK is added to WorkOrder

    def __repr__(self):
        return f"<Technician {self.first_name} {self.last_name}>"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
