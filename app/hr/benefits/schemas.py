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


class CarrierIntegrationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    carrier: str
    state: str | None
    enrollment_types: str | None
    integration_status: str
    form_forwarding_enabled: bool
    plan_year: int | None
    is_upcoming: bool


class AccountStructureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    carrier: str
    class_type: str | None
    employee_group: str | None
    plan_name: str | None
    enrollment_tier: str | None
    class_value: str | None
    count_of_employees: int
    group_rules: str | None


class AccountStructureIn(BaseModel):
    carrier: str
    class_type: str | None = None
    employee_group: str | None = None
    plan_name: str | None = None
    enrollment_tier: str | None = None
    class_value: str | None = None
    count_of_employees: int = 0
    group_rules: str | None = None


class ScheduledDeductionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    employee_id: UUIDStr | None
    employee_name: str
    benefit_type: str
    plan_name: str | None
    effective_date: date | None
    auto_manage: bool
    ee_rippling: Decimal | None
    ee_in_payroll: Decimal | None
    er_rippling: Decimal | None
    er_in_payroll: Decimal | None
    taxable_rippling: Decimal | None
    taxable_in_payroll: Decimal | None


class ScheduledDeductionPatch(BaseModel):
    auto_manage: bool | None = None
    ee_in_payroll: Decimal | None = None
    er_in_payroll: Decimal | None = None
    taxable_in_payroll: Decimal | None = None


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
