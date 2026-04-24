from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.schemas.types import UUIDStr


class FsaPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    kind: str
    name: str
    annual_limit_employee: Decimal
    annual_limit_family: Decimal | None
    plan_year_start: date | None
    plan_year_end: date | None
    grace_period_enabled: bool
    grace_period_months: int
    rollover_enabled: bool
    rollover_max: Decimal | None
    runout_days: int
    is_active: bool


class FsaPlanIn(BaseModel):
    kind: str
    name: str
    annual_limit_employee: Decimal = Decimal("0")
    annual_limit_family: Decimal | None = None
    plan_year_start: date | None = None
    plan_year_end: date | None = None
    grace_period_enabled: bool = False
    grace_period_months: int = 0
    rollover_enabled: bool = False
    rollover_max: Decimal | None = None
    runout_days: int = 90
    is_active: bool = True


class FsaPlanPatch(BaseModel):
    name: str | None = None
    annual_limit_employee: Decimal | None = None
    annual_limit_family: Decimal | None = None
    plan_year_start: date | None = None
    plan_year_end: date | None = None
    grace_period_enabled: bool | None = None
    grace_period_months: int | None = None
    rollover_enabled: bool | None = None
    rollover_max: Decimal | None = None
    runout_days: int | None = None
    is_active: bool | None = None


class FsaEnrollmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    employee_id: UUIDStr | None
    employee_name: str
    plan_id: UUIDStr | None
    plan_kind: str
    annual_election: Decimal
    ytd_contributed: Decimal
    ytd_spent: Decimal
    status: str
    enrolled_at: date | None


class FsaTransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    employee_id: UUIDStr | None
    employee_name: str
    plan_kind: str
    transaction_date: date
    merchant: str | None
    category: str | None
    amount: Decimal
    kind: str
    status: str
    notes: str | None


class FsaTransactionPatch(BaseModel):
    status: str | None = None
    notes: str | None = None


class FsaSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    bank_name: str | None
    bank_account_last4: str | None
    bank_routing_last4: str | None
    bank_account_type: str | None
    eligibility_waiting_days: int
    eligibility_min_hours: int
    eligibility_rule: str | None
    debit_card_enabled: bool
    auto_substantiation_enabled: bool


class FsaSettingsPatch(BaseModel):
    bank_name: str | None = None
    bank_account_last4: str | None = None
    bank_routing_last4: str | None = None
    bank_account_type: str | None = None
    eligibility_waiting_days: int | None = None
    eligibility_min_hours: int | None = None
    eligibility_rule: str | None = None
    debit_card_enabled: bool | None = None
    auto_substantiation_enabled: bool | None = None


class FsaDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    title: str
    kind: str
    url: str | None
    description: str | None
    uploaded_at: datetime


class FsaComplianceTestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    test_kind: str
    plan_year: int
    run_date: datetime
    status: str
    highly_compensated_count: int
    non_highly_compensated_count: int
    failure_reason: str | None
    report_url: str | None


class FsaExclusionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    employee_id: UUIDStr | None
    employee_name: str
    reason: str
    excluded_from: str


class FsaExclusionIn(BaseModel):
    employee_name: str
    reason: str
    excluded_from: str = "all"
    employee_id: UUIDStr | None = None


class FsaOverviewOut(BaseModel):
    total_enrollments: int
    active_enrollments: int
    pending_enrollments: int
    declined_enrollments: int
    total_ytd_contributed: Decimal
    total_ytd_spent: Decimal
    remaining_balance: Decimal
    by_plan_kind: dict[str, int]
    transactions_last_30d: int
    last_compliance_status: str | None
    bank_configured: bool
