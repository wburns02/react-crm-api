from uuid import uuid4

from sqlalchemy import Column, Date, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class HrPayRun(Base):
    __tablename__ = "hr_pay_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    label = Column(String(128), nullable=False)
    pay_schedule_name = Column(String(200), nullable=True)
    entity = Column(String(200), nullable=True)
    pay_run_type = Column(String(32), nullable=False, default="regular")
    pay_date = Column(Date, nullable=True)
    approve_by = Column(DateTime, nullable=True)
    funding_method = Column(String(32), nullable=True)
    status = Column(String(32), nullable=False, default="upcoming")
    action_text = Column(String(128), nullable=True)
    failure_reason = Column(String(512), nullable=True)
    archived_by = Column(String(200), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, nullable=True)


class HrPayrollPeopleStatus(Base):
    __tablename__ = "hr_payroll_people_status"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    employee_name = Column(String(200), nullable=False)
    employee_title = Column(String(200), nullable=True)
    pay_schedule = Column(String(200), nullable=True)
    status = Column(String(64), nullable=False, default="payroll_ready")
    bucket = Column(String(32), nullable=False, default="payroll_ready")
    critical_missing_count = Column(Integer, nullable=False, default=0)
    missing_fields = Column(String(1024), nullable=True)
    signatory_status = Column(String(64), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, nullable=True)
