"""Job Cost model for tracking costs associated with work orders."""
from sqlalchemy import Column, String, DateTime, Text, Integer, Float, Boolean, Date
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database import Base


class JobCost(Base):
    """Track costs associated with a work order/job."""

    __tablename__ = "job_costs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Work order reference
    work_order_id = Column(String(36), nullable=False, index=True)

    # Cost identification
    cost_type = Column(String(50), nullable=False)  # labor, materials, equipment, disposal, travel, subcontractor, other
    category = Column(String(100), nullable=True)  # sub-category for detailed tracking

    # Description
    description = Column(String(500), nullable=False)
    notes = Column(Text, nullable=True)

    # Quantity and pricing
    quantity = Column(Float, default=1.0)
    unit = Column(String(20), default="each")  # each, hour, gallon, mile, etc.
    unit_cost = Column(Float, nullable=False)
    total_cost = Column(Float, nullable=False)

    # Markup for billing
    markup_percent = Column(Float, default=0.0)
    billable_amount = Column(Float, nullable=True)

    # Technician assignment (for labor costs)
    technician_id = Column(String(36), nullable=True, index=True)
    technician_name = Column(String(255), nullable=True)

    # Date tracking
    cost_date = Column(Date, nullable=False, index=True)

    # Status
    is_billable = Column(Boolean, default=True)
    is_billed = Column(Boolean, default=False)
    invoice_id = Column(String(36), nullable=True)

    # Vendor/supplier (for materials, subcontractor)
    vendor_name = Column(String(255), nullable=True)
    vendor_invoice = Column(String(100), nullable=True)

    # Receipt/documentation
    receipt_url = Column(String(500), nullable=True)

    # Timestamps
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<JobCost {self.cost_type}: ${self.total_cost}>"

    @property
    def calculated_billable(self):
        """Calculate billable amount with markup."""
        if self.billable_amount:
            return self.billable_amount
        return self.total_cost * (1 + self.markup_percent / 100)
