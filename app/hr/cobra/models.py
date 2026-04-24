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


class HrCobraEnrollment(Base):
    __tablename__ = "hr_cobra_enrollments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("technicians.id"), nullable=True)
    employee_name = Column(String(200), nullable=False)
    employee_label = Column(String(64), nullable=True)
    beneficiary_name = Column(String(200), nullable=False)
    status = Column(String(64), nullable=False, default="pending_election")
    qualifying_event = Column(String(128), nullable=True)
    eligibility_date = Column(Date, nullable=True)
    exhaustion_date = Column(Date, nullable=True)
    bucket = Column(String(16), nullable=False, default="current")
    notice_sent_at = Column(DateTime, nullable=True)
    notes = Column(String(512), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, nullable=True)


class HrCobraPayment(Base):
    __tablename__ = "hr_cobra_payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    enrollment_id = Column(UUID(as_uuid=True), ForeignKey("hr_cobra_enrollments.id"), nullable=True)
    employee_name = Column(String(200), nullable=False)
    beneficiary_name = Column(String(200), nullable=False)
    month = Column(String(16), nullable=False)
    employee_charge_date = Column(Date, nullable=True)
    charged_amount = Column(Numeric(10, 2), nullable=True)
    company_reimbursement_date = Column(Date, nullable=True)
    reimbursement_amount = Column(Numeric(10, 2), nullable=True)
    status = Column(String(32), nullable=False, default="pending")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class HrCobraNotice(Base):
    __tablename__ = "hr_cobra_notices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    enrollment_id = Column(UUID(as_uuid=True), ForeignKey("hr_cobra_enrollments.id"), nullable=True)
    employee_name = Column(String(200), nullable=False)
    beneficiary_name = Column(String(200), nullable=False)
    type_of_notice = Column(String(200), nullable=False)
    addressed_to = Column(String(400), nullable=True)
    notice_url = Column(String(512), nullable=True)
    tracking_status = Column(String(64), nullable=False, default="In Production")
    updated_on = Column(Date, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class HrCobraSettings(Base):
    __tablename__ = "hr_cobra_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    payment_method_label = Column(String(200), nullable=True)
    bank_last4 = Column(String(16), nullable=True)
    country_code = Column(String(8), nullable=True, default="US")
    grace_period_days = Column(Integer, nullable=False, default=30)
    election_window_days = Column(Integer, nullable=False, default=60)
    send_election_notices_automatically = Column(Boolean, nullable=False, server_default=func.true())
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, nullable=True)


class HrCobraPreRipplingPlan(Base):
    __tablename__ = "hr_cobra_pre_rippling_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    carrier = Column(String(200), nullable=False)
    plan_name = Column(String(200), nullable=False)
    plan_kind = Column(String(32), nullable=False, default="medical")
    monthly_premium = Column(Numeric(10, 2), nullable=True)
    effective_from = Column(Date, nullable=True)
    effective_to = Column(Date, nullable=True)
    is_active = Column(Boolean, nullable=False, server_default=func.true())
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
