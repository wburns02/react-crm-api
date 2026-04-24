from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.schemas.types import UUIDStr


class EnrollmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    employee_id: UUIDStr | None
    employee_name: str
    employee_title: str | None
    plan_id: UUIDStr | None
    plan_name: str | None
    carrier: str | None
    benefit_type: str
    status: str
    effective_date: date | None
    termination_date: date | None
    monthly_cost: Decimal | None
    monthly_deduction: Decimal | None


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    employee_id: UUIDStr | None
    employee_name: str
    employee_title: str | None
    event_type: str
    status: str
    effective_date: date | None
    completion_date: date | None
    is_archived: bool


class EoiRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    employee_id: UUIDStr | None
    employee_name: str
    member_name: str
    member_type: str
    benefit_type: str
    plan_name: str | None
    status: str
    enrollment_created_at: date | None
    enrollment_ends_at: date | None


class HistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    employee_id: UUIDStr | None
    employee_name: str
    change_type: str
    affected_lines: int
    completed_date: date | None
    effective_date: date | None
    changed_by: str | None
    is_terminated: bool


class BenefitsOverviewOut(BaseModel):
    total_enrollments: int
    active_enrollments: int
    waived: int
    terminated: int
    pending_events: int
    pending_eoi: int
    by_benefit_type: dict[str, int]
    total_monthly_cost: Decimal
    total_monthly_deduction: Decimal
    generated_at: datetime
