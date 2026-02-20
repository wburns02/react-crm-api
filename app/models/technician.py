from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Float, Date, Numeric, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base
import uuid


class Technician(Base):
    """Technician model - id column is native UUID in the database."""

    __tablename__ = "technicians"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(255), index=True)
    phone = Column(String(20))
    employee_id = Column(String(50), unique=True, index=True)
    is_active = Column(Boolean, default=True)

    # Skills stored as JSON array for cross-database compatibility (PostgreSQL + SQLite)
    skills = Column(JSON)

    # Vehicle info
    assigned_vehicle = Column(String(100))
    vehicle_capacity_gallons = Column(Integer)

    # Licensing
    license_number = Column(String(100))
    license_expiry = Column(Date)

    # Pay rates
    hourly_rate = Column(Float)
    overtime_rate = Column(Numeric)
    double_time_rate = Column(Numeric)
    travel_rate = Column(Numeric)
    pay_type = Column(String(50))
    salary_amount = Column(Numeric)

    # Work hours
    default_hours_per_week = Column(Numeric)
    overtime_threshold = Column(Numeric)

    # PTO
    pto_balance_hours = Column(Numeric)
    pto_accrual_rate = Column(Numeric)

    # Employment
    hire_date = Column(Date)
    department = Column(String(100))
    external_payroll_id = Column(String(100))

    # Home location
    home_region = Column(String(100))
    home_address = Column(String(255))
    home_city = Column(String(100))
    home_state = Column(String(50))
    home_postal_code = Column(String(20))
    home_latitude = Column(Float)
    home_longitude = Column(Float)

    # Notes
    notes = Column(Text)

    # Timestamps
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

    # Multi-entity (LLC) support
    entity_id = Column(UUID(as_uuid=True), ForeignKey("company_entities.id"), nullable=True, index=True)

    def __repr__(self):
        return f"<Technician {self.first_name} {self.last_name}>"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
