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


class HrBenefitPlan(Base):
    __tablename__ = "hr_benefit_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    kind = Column(String(32), nullable=False)
    carrier = Column(String(128), nullable=True)
    name = Column(String(200), nullable=False)
    monthly_cost = Column(Numeric(10, 2), nullable=True)
    employee_contribution = Column(Numeric(10, 2), nullable=True)
    employer_contribution = Column(Numeric(10, 2), nullable=True)
    is_active = Column(Boolean, nullable=False, server_default=func.true())
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (Index("ix_hr_benefit_plans_kind", "kind"),)


class HrBenefitEnrollment(Base):
    __tablename__ = "hr_benefit_enrollments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("technicians.id"), nullable=True)
    employee_name = Column(String(200), nullable=False)
    employee_title = Column(String(200), nullable=True)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("hr_benefit_plans.id"), nullable=True)
    plan_name = Column(String(200), nullable=True)
    carrier = Column(String(128), nullable=True)
    benefit_type = Column(String(32), nullable=False, default="medical")
    status = Column(String(32), nullable=False, default="active")
    effective_date = Column(Date, nullable=True)
    termination_date = Column(Date, nullable=True)
    monthly_cost = Column(Numeric(10, 2), nullable=True)
    monthly_deduction = Column(Numeric(10, 2), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, nullable=True)


class HrBenefitEvent(Base):
    __tablename__ = "hr_benefit_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("technicians.id"), nullable=True)
    employee_name = Column(String(200), nullable=False)
    employee_title = Column(String(200), nullable=True)
    event_type = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="pending")
    effective_date = Column(Date, nullable=True)
    completion_date = Column(Date, nullable=True)
    is_archived = Column(Boolean, nullable=False, server_default=func.false())
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class HrBenefitEoiRequest(Base):
    __tablename__ = "hr_benefit_eoi_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("technicians.id"), nullable=True)
    employee_name = Column(String(200), nullable=False)
    member_name = Column(String(200), nullable=False)
    member_type = Column(String(32), nullable=False, default="employee")
    benefit_type = Column(String(32), nullable=False, default="life")
    plan_name = Column(String(200), nullable=True)
    status = Column(String(32), nullable=False, default="pending")
    enrollment_created_at = Column(Date, nullable=True)
    enrollment_ends_at = Column(Date, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class HrBenefitHistory(Base):
    __tablename__ = "hr_benefit_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("technicians.id"), nullable=True)
    employee_name = Column(String(200), nullable=False)
    change_type = Column(String(64), nullable=False)
    affected_lines = Column(Integer, nullable=False, default=1)
    completed_date = Column(Date, nullable=True)
    effective_date = Column(Date, nullable=True)
    changed_by = Column(String(128), nullable=True)
    is_terminated = Column(Boolean, nullable=False, server_default=func.false())
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
