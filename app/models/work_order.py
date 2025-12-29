from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Enum, ForeignKey, Float
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum
from app.database import Base


class JobType(str, enum.Enum):
    pumping = "pumping"
    inspection = "inspection"
    repair = "repair"
    installation = "installation"
    emergency = "emergency"
    maintenance = "maintenance"
    grease_trap = "grease_trap"
    camera_inspection = "camera_inspection"


class WorkOrderStatus(str, enum.Enum):
    draft = "draft"
    scheduled = "scheduled"
    confirmed = "confirmed"
    enroute = "enroute"
    on_site = "on_site"
    in_progress = "in_progress"
    completed = "completed"
    canceled = "canceled"
    requires_followup = "requires_followup"


class Priority(str, enum.Enum):
    low = "low"
    normal = "normal"
    high = "high"
    urgent = "urgent"
    emergency = "emergency"


class WorkOrder(Base):
    """Work Order model."""

    __tablename__ = "work_orders"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)

    job_type = Column(Enum(JobType), nullable=False)
    status = Column(Enum(WorkOrderStatus), default=WorkOrderStatus.draft)
    priority = Column(Enum(Priority), default=Priority.normal)

    scheduled_date = Column(DateTime(timezone=True))
    time_window_start = Column(String(10))  # "09:00"
    time_window_end = Column(String(10))  # "12:00"
    estimated_duration_hours = Column(Float)

    assigned_technician = Column(String(100))
    service_address = Column(String(255))
    service_city = Column(String(100))
    service_state = Column(String(50))
    service_zip = Column(String(20))

    description = Column(Text)
    notes = Column(Text)
    internal_notes = Column(Text)

    # Completion details
    completed_at = Column(DateTime(timezone=True))
    completion_notes = Column(Text)

    # React-specific fields (new schema)
    estimated_completion = Column(DateTime(timezone=True))
    actual_duration_hours = Column(Float)
    equipment_used = Column(Text)  # JSON array

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    customer = relationship("Customer", back_populates="work_orders")

    def __repr__(self):
        return f"<WorkOrder {self.id} - {self.job_type}>"
