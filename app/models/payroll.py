"""Payroll models for time tracking and compensation."""
from sqlalchemy import Column, String, DateTime, Text, Integer, Float, Boolean, Date, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database import Base


class PayrollPeriod(Base):
    """Payroll period definition."""

    __tablename__ = "payroll_periods"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Period dates
    start_date = Column(Date, nullable=False, index=True)
    end_date = Column(Date, nullable=False)
    period_type = Column(String(20), default="biweekly")  # weekly, biweekly, monthly

    # Status
    status = Column(String(20), default="open", index=True)  # open, locked, approved, processed

    # Totals
    total_regular_hours = Column(Float, default=0.0)
    total_overtime_hours = Column(Float, default=0.0)
    total_gross_pay = Column(Float, default=0.0)
    total_commissions = Column(Float, default=0.0)
    technician_count = Column(Integer, default=0)

    # Approval
    approved_by = Column(String(100), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)

    # Processing
    processed_at = Column(DateTime(timezone=True), nullable=True)
    export_file_url = Column(String(500), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class TimeEntry(Base):
    """Individual time entry for a technician."""

    __tablename__ = "time_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # References
    technician_id = Column(String(36), nullable=False, index=True)
    work_order_id = Column(String(36), nullable=True, index=True)
    payroll_period_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    # Time
    entry_date = Column(Date, nullable=False, index=True)
    clock_in = Column(DateTime(timezone=True), nullable=False)
    clock_out = Column(DateTime(timezone=True), nullable=True)

    # Duration
    regular_hours = Column(Float, default=0.0)
    overtime_hours = Column(Float, default=0.0)
    break_minutes = Column(Integer, default=0)

    # GPS verification
    clock_in_lat = Column(Float, nullable=True)
    clock_in_lon = Column(Float, nullable=True)
    clock_out_lat = Column(Float, nullable=True)
    clock_out_lon = Column(Float, nullable=True)

    # Type
    entry_type = Column(String(20), default="work")  # work, travel, break, pto

    # Status
    status = Column(String(20), default="pending")  # pending, approved, rejected
    approved_by = Column(String(100), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)

    # Notes
    notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Commission(Base):
    """Commission record for technician."""

    __tablename__ = "commissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # References
    technician_id = Column(String(36), nullable=False, index=True)
    work_order_id = Column(String(36), nullable=True)
    invoice_id = Column(String(36), nullable=True)
    payroll_period_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    # Commission details
    commission_type = Column(String(50), nullable=False)  # job_completion, upsell, referral
    base_amount = Column(Float, nullable=False)  # Amount commission is calculated on
    rate = Column(Float, nullable=False)  # Percentage or fixed amount
    rate_type = Column(String(20), default="percent")  # percent, fixed

    # Calculated amount
    commission_amount = Column(Float, nullable=False)

    # Status
    status = Column(String(20), default="pending")  # pending, approved, paid

    # Notes
    description = Column(Text, nullable=True)

    # Timestamps
    earned_date = Column(Date, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class TechnicianPayRate(Base):
    """Pay rate configuration for technician."""

    __tablename__ = "technician_pay_rates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    technician_id = Column(String(36), nullable=False, index=True)  # Not unique - techs can have multiple rate records

    # Hourly rates
    hourly_rate = Column(Float, nullable=False)
    overtime_multiplier = Column(Float, default=1.5)

    # Commission rates
    job_commission_rate = Column(Float, default=0.0)  # % of job value
    upsell_commission_rate = Column(Float, default=0.0)

    # Overtime threshold
    weekly_overtime_threshold = Column(Float, default=40.0)

    # Effective dates
    effective_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
