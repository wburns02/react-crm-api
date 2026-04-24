from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.schemas.types import UUIDStr


class CobraEnrollmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    employee_id: UUIDStr | None
    employee_name: str
    employee_label: str | None
    beneficiary_name: str
    status: str
    qualifying_event: str | None
    eligibility_date: date | None
    exhaustion_date: date | None
    bucket: str
    notice_sent_at: datetime | None
    notes: str | None


class CobraEnrollmentIn(BaseModel):
    employee_name: str
    employee_label: str | None = "Terminated"
    beneficiary_name: str
    status: str = "pending_election"
    qualifying_event: str | None = None
    eligibility_date: date | None = None
    exhaustion_date: date | None = None
    bucket: str = "pending"
    notes: str | None = None


class CobraEnrollmentPatch(BaseModel):
    status: str | None = None
    bucket: str | None = None
    beneficiary_name: str | None = None
    qualifying_event: str | None = None
    eligibility_date: date | None = None
    exhaustion_date: date | None = None
    notes: str | None = None


class CobraPaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    enrollment_id: UUIDStr | None
    employee_name: str
    beneficiary_name: str
    month: str
    employee_charge_date: date | None
    charged_amount: Decimal | None
    company_reimbursement_date: date | None
    reimbursement_amount: Decimal | None
    status: str


class CobraNoticeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    enrollment_id: UUIDStr | None
    employee_name: str
    beneficiary_name: str
    type_of_notice: str
    addressed_to: str | None
    notice_url: str | None
    tracking_status: str
    updated_on: date | None


class CobraSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    payment_method_label: str | None
    bank_last4: str | None
    country_code: str | None
    grace_period_days: int
    election_window_days: int
    send_election_notices_automatically: bool


class CobraSettingsPatch(BaseModel):
    payment_method_label: str | None = None
    bank_last4: str | None = None
    country_code: str | None = None
    grace_period_days: int | None = None
    election_window_days: int | None = None
    send_election_notices_automatically: bool | None = None


class CobraPreRipplingPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    carrier: str
    plan_name: str
    plan_kind: str
    monthly_premium: Decimal | None
    effective_from: date | None
    effective_to: date | None
    is_active: bool


class CobraPreRipplingPlanIn(BaseModel):
    carrier: str
    plan_name: str
    plan_kind: str = "medical"
    monthly_premium: Decimal | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    is_active: bool = True
