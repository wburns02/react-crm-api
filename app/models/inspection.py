"""Inspection model for tracking system inspections and compliance checks."""
from sqlalchemy import Column, String, DateTime, Text, Integer, Date, Boolean, Float, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database import Base


class Inspection(Base):
    """Track septic system inspections for compliance."""

    __tablename__ = "inspections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Inspection reference
    inspection_number = Column(String(50), unique=True, nullable=False, index=True)
    inspection_type = Column(String(100), nullable=False)  # annual, sale, complaint, permit, routine

    # Customer/Property
    customer_id = Column(Integer, nullable=False, index=True)
    property_address = Column(String(500), nullable=True)

    # System info
    system_type = Column(String(100), nullable=True)  # conventional, aerobic, mound, drip
    system_age_years = Column(Integer, nullable=True)
    tank_size_gallons = Column(Integer, nullable=True)

    # Scheduling
    scheduled_date = Column(Date, nullable=True, index=True)
    completed_date = Column(Date, nullable=True)

    # Assignment
    technician_id = Column(String(36), nullable=True, index=True)
    technician_name = Column(String(255), nullable=True)

    # Work order link
    work_order_id = Column(String(36), nullable=True, index=True)

    # Results
    status = Column(String(20), default="pending")  # pending, scheduled, in_progress, completed, failed
    result = Column(String(20), nullable=True)  # pass, fail, conditional
    overall_condition = Column(String(20), nullable=True)  # good, fair, poor, critical

    # Checklist items (JSON for flexibility)
    checklist = Column(JSON, nullable=True)
    # Example: [
    #   {"item": "Tank condition", "status": "pass", "notes": "No cracks"},
    #   {"item": "Scum/sludge levels", "status": "pass", "notes": "15% capacity"},
    #   {"item": "Outlet baffle", "status": "fail", "notes": "Damaged"},
    # ]

    # Measurements
    sludge_depth_inches = Column(Float, nullable=True)
    scum_depth_inches = Column(Float, nullable=True)
    liquid_depth_inches = Column(Float, nullable=True)

    # Compliance
    requires_followup = Column(Boolean, default=False)
    followup_due_date = Column(Date, nullable=True)
    violations_found = Column(JSON, nullable=True)  # List of violation codes
    corrective_actions = Column(Text, nullable=True)

    # Regulatory
    county = Column(String(100), nullable=True)
    permit_number = Column(String(100), nullable=True)
    filed_with_county = Column(Boolean, default=False)
    county_filing_date = Column(Date, nullable=True)

    # Documentation
    photos = Column(JSON, nullable=True)  # List of photo URLs
    report_url = Column(String(500), nullable=True)
    notes = Column(Text, nullable=True)

    # Fees
    inspection_fee = Column(Float, nullable=True)
    fee_collected = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Inspection {self.inspection_number} - {self.inspection_type}>"

    @property
    def is_passed(self):
        return self.result == "pass"

    @property
    def is_overdue(self):
        from datetime import date
        if not self.scheduled_date or self.status == "completed":
            return False
        return self.scheduled_date < date.today() and self.status != "completed"
