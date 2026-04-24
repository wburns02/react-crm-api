from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class HrAcaFiling(Base):
    __tablename__ = "hr_aca_filings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    plan_year = Column(Integer, nullable=False)
    form_1094c_status = Column(String(32), nullable=False, default="not_started")
    form_1095c_count = Column(Integer, nullable=False, default=0)
    irs_deadline = Column(Date, nullable=True)
    employee_deadline = Column(Date, nullable=True)
    filed_at = Column(DateTime, nullable=True)
    is_current = Column(Boolean, nullable=False, server_default=func.false())
    notes = Column(String(512), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class HrAcaLookbackPolicy(Base):
    __tablename__ = "hr_aca_lookback_policy"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    standard_measurement_months = Column(Integer, nullable=False, default=12)
    stability_months = Column(Integer, nullable=False, default=12)
    administrative_days = Column(Integer, nullable=False, default=90)
    initial_measurement_months = Column(Integer, nullable=False, default=12)
    hours_threshold = Column(Integer, nullable=False, default=130)
    is_active = Column(Boolean, nullable=False, server_default=func.false())
    effective_from = Column(Date, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, nullable=True)


class HrAcaEmployeeHours(Base):
    __tablename__ = "hr_aca_employee_hours"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    employee_name = Column(String(200), nullable=False)
    measurement_period = Column(String(64), nullable=False)
    total_hours = Column(Numeric(10, 2), nullable=False, default=0)
    average_hours_per_week = Column(Numeric(6, 2), nullable=False, default=0)
    is_full_time_eligible = Column(Boolean, nullable=False, server_default=func.false())
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class HrBenefitSignatory(Base):
    __tablename__ = "hr_benefit_signatories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    document_type = Column(String(128), nullable=False)
    signatory_name = Column(String(200), nullable=True)
    signatory_department = Column(String(128), nullable=True)
    status = Column(String(32), nullable=False, default="signature_missing")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, nullable=True)


class HrBenefitCompanySettings(Base):
    __tablename__ = "hr_benefit_company_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    class_codes = Column(String(512), nullable=True)
    tax_std_not_taxed = Column(Boolean, nullable=False, server_default=func.true())
    tax_ltd_not_taxed = Column(Boolean, nullable=False, server_default=func.true())
    enrollment_hide_until_start = Column(Boolean, nullable=False, server_default=func.false())
    newly_eligible_window_days = Column(Integer, nullable=False, default=30)
    part_time_offer_health = Column(Boolean, nullable=False, server_default=func.false())
    cost_show_monthly_in_app = Column(Boolean, nullable=False, server_default=func.false())
    cost_hide_company_contribution = Column(Boolean, nullable=False, server_default=func.false())
    ask_tobacco_question = Column(Boolean, nullable=False, server_default=func.true())
    qle_require_admin_approval = Column(Boolean, nullable=False, server_default=func.false())
    new_hire_preview_enabled = Column(Boolean, nullable=False, server_default=func.false())
    form_forwarding_enabled = Column(Boolean, nullable=False, server_default=func.false())
    carrier_connect_tier = Column(String(32), nullable=False, default="standard")
    benefit_admin_notification_user = Column(String(200), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, nullable=True)
