from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    Text,
    Float,
    ForeignKey,
    Date,
    Time,
    JSON,
    Numeric,
    Enum as SQLEnum,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import ENUM, UUID
from app.database import Base
import uuid

# PostgreSQL ENUM types - must match database schema exactly
WorkOrderStatusEnum = ENUM(
    "draft",
    "scheduled",
    "confirmed",
    "enroute",
    "on_site",
    "in_progress",
    "completed",
    "canceled",
    "requires_followup",
    name="work_order_status_enum",
    create_type=False,  # Don't create, already exists in DB
)

WorkOrderJobTypeEnum = ENUM(
    "pumping",
    "inspection",
    "repair",
    "installation",
    "emergency",
    "maintenance",
    "grease_trap",
    "camera_inspection",
    name="work_order_job_type_enum",
    create_type=False,
)

WorkOrderPriorityEnum = ENUM(
    "low", "normal", "high", "urgent", "emergency", name="work_order_priority_enum", create_type=False
)


class WorkOrder(Base):
    """Work Order model - matches Flask database schema."""

    __tablename__ = "work_orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    # Human-readable work order number (WO-000001 format)
    work_order_number = Column(String(20), unique=True, index=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True)
    technician_id = Column(UUID(as_uuid=True), ForeignKey("technicians.id"), nullable=True, index=True)

    # Job details - use String to avoid asyncpg ENUM type mismatch errors
    job_type = Column(String(50), nullable=False)
    priority = Column(String(50))
    status = Column(String(50))

    # Scheduling
    scheduled_date = Column(Date)
    time_window_start = Column(Time)
    time_window_end = Column(Time)
    estimated_duration_hours = Column(Float)

    # Service location
    service_address_line1 = Column(String(255))
    service_address_line2 = Column(String(255))
    service_city = Column(String(100))
    service_state = Column(String(50))
    service_postal_code = Column(String(20))
    service_latitude = Column(Float)
    service_longitude = Column(Float)

    # Job specifics
    estimated_gallons = Column(Integer)
    notes = Column(Text)
    internal_notes = Column(Text)

    # Recurrence
    is_recurring = Column(Boolean, default=False)
    recurrence_frequency = Column(String(50))
    next_recurrence_date = Column(Date)

    # Checklist (stored as JSON)
    checklist = Column(JSON)

    # Assignment
    assigned_vehicle = Column(String(100))
    assigned_technician = Column(String(100))

    # Timestamps
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

    # Financial
    total_amount = Column(Numeric)

    # Time tracking
    actual_start_time = Column(DateTime(timezone=True))
    actual_end_time = Column(DateTime(timezone=True))
    travel_start_time = Column(DateTime(timezone=True))
    travel_end_time = Column(DateTime(timezone=True))
    break_minutes = Column(Integer)
    total_labor_minutes = Column(Integer)
    total_travel_minutes = Column(Integer)

    # Clock in/out
    is_clocked_in = Column(Boolean, default=False)
    clock_in_gps_lat = Column(Numeric)
    clock_in_gps_lon = Column(Numeric)
    clock_out_gps_lat = Column(Numeric)
    clock_out_gps_lon = Column(Numeric)

    # Relationships
    customer = relationship("Customer", back_populates="work_orders")

    def __repr__(self):
        return f"<WorkOrder {self.id} - {self.job_type}>"
