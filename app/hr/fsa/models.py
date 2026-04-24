from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class HrFsaPlan(Base):
    __tablename__ = "hr_fsa_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    kind = Column(String(32), nullable=False)
    name = Column(String(200), nullable=False)
    annual_limit_employee = Column(Numeric(10, 2), nullable=False, default=0)
    annual_limit_family = Column(Numeric(10, 2), nullable=True)
    plan_year_start = Column(Date, nullable=True)
    plan_year_end = Column(Date, nullable=True)
    grace_period_enabled = Column(Boolean, nullable=False, server_default=func.false())
    grace_period_months = Column(Integer, nullable=False, default=0)
    rollover_enabled = Column(Boolean, nullable=False, server_default=func.false())
    rollover_max = Column(Numeric(10, 2), nullable=True)
    runout_days = Column(Integer, nullable=False, default=90)
    is_active = Column(Boolean, nullable=False, server_default=func.true())
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, nullable=True)


class HrFsaEnrollment(Base):
    __tablename__ = "hr_fsa_enrollments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("technicians.id"), nullable=True)
    employee_name = Column(String(200), nullable=False)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("hr_fsa_plans.id"), nullable=True)
    plan_kind = Column(String(32), nullable=False)
    annual_election = Column(Numeric(10, 2), nullable=False, default=0)
    ytd_contributed = Column(Numeric(10, 2), nullable=False, default=0)
    ytd_spent = Column(Numeric(10, 2), nullable=False, default=0)
    status = Column(String(32), nullable=False, default="active")
    enrolled_at = Column(Date, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class HrFsaTransaction(Base):
    __tablename__ = "hr_fsa_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("technicians.id"), nullable=True)
    employee_name = Column(String(200), nullable=False)
    plan_kind = Column(String(32), nullable=False)
    transaction_date = Column(Date, nullable=False)
    merchant = Column(String(200), nullable=True)
    category = Column(String(64), nullable=True)
    amount = Column(Numeric(10, 2), nullable=False)
    kind = Column(String(32), nullable=False, default="card_swipe")
    status = Column(String(32), nullable=False, default="pending")
    notes = Column(String(512), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class HrFsaSettings(Base):
    __tablename__ = "hr_fsa_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    bank_name = Column(String(200), nullable=True)
    bank_account_last4 = Column(String(16), nullable=True)
    bank_routing_last4 = Column(String(16), nullable=True)
    bank_account_type = Column(String(32), nullable=True)
    eligibility_waiting_days = Column(Integer, nullable=False, default=0)
    eligibility_min_hours = Column(Integer, nullable=False, default=30)
    eligibility_rule = Column(String(512), nullable=True)
    debit_card_enabled = Column(Boolean, nullable=False, server_default=func.true())
    auto_substantiation_enabled = Column(Boolean, nullable=False, server_default=func.true())
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, nullable=True)


class HrFsaDocument(Base):
    __tablename__ = "hr_fsa_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    title = Column(String(200), nullable=False)
    kind = Column(String(32), nullable=False)
    url = Column(String(512), nullable=True)
    storage_key = Column(String(512), nullable=True)
    description = Column(String(512), nullable=True)
    uploaded_at = Column(DateTime, server_default=func.now(), nullable=False)


class HrFsaComplianceTest(Base):
    __tablename__ = "hr_fsa_compliance_tests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    test_kind = Column(String(64), nullable=False)
    plan_year = Column(Integer, nullable=False)
    run_date = Column(DateTime, server_default=func.now(), nullable=False)
    status = Column(String(32), nullable=False, default="passed")
    highly_compensated_count = Column(Integer, nullable=False, default=0)
    non_highly_compensated_count = Column(Integer, nullable=False, default=0)
    failure_reason = Column(String(1024), nullable=True)
    report_url = Column(String(512), nullable=True)


class HrFsaExclusion(Base):
    __tablename__ = "hr_fsa_exclusions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("technicians.id"), nullable=True)
    employee_name = Column(String(200), nullable=False)
    reason = Column(String(200), nullable=False)
    excluded_from = Column(String(64), nullable=False, default="all")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
