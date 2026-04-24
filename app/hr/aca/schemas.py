from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.schemas.types import UUIDStr


class AcaFilingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    plan_year: int
    form_1094c_status: str
    form_1095c_count: int
    irs_deadline: date | None
    employee_deadline: date | None
    filed_at: datetime | None
    is_current: bool
    notes: str | None


class LookbackPolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    standard_measurement_months: int
    stability_months: int
    administrative_days: int
    initial_measurement_months: int
    hours_threshold: int
    is_active: bool
    effective_from: date | None


class LookbackPolicyPatch(BaseModel):
    standard_measurement_months: int | None = None
    stability_months: int | None = None
    administrative_days: int | None = None
    initial_measurement_months: int | None = None
    hours_threshold: int | None = None
    is_active: bool | None = None
    effective_from: date | None = None


class EmployeeHoursOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    employee_name: str
    measurement_period: str
    total_hours: Decimal
    average_hours_per_week: Decimal
    is_full_time_eligible: bool


class BenefitSignatoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    document_type: str
    signatory_name: str | None
    signatory_department: str | None
    status: str


class BenefitSignatoryPatch(BaseModel):
    signatory_name: str | None = None
    signatory_department: str | None = None
    status: str | None = None


class CompanySettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    class_codes: str | None
    tax_std_not_taxed: bool
    tax_ltd_not_taxed: bool
    enrollment_hide_until_start: bool
    newly_eligible_window_days: int
    part_time_offer_health: bool
    cost_show_monthly_in_app: bool
    cost_hide_company_contribution: bool
    ask_tobacco_question: bool
    qle_require_admin_approval: bool
    new_hire_preview_enabled: bool
    form_forwarding_enabled: bool
    carrier_connect_tier: str
    benefit_admin_notification_user: str | None


class CompanySettingsPatch(BaseModel):
    class_codes: str | None = None
    tax_std_not_taxed: bool | None = None
    tax_ltd_not_taxed: bool | None = None
    enrollment_hide_until_start: bool | None = None
    newly_eligible_window_days: int | None = None
    part_time_offer_health: bool | None = None
    cost_show_monthly_in_app: bool | None = None
    cost_hide_company_contribution: bool | None = None
    ask_tobacco_question: bool | None = None
    qle_require_admin_approval: bool | None = None
    new_hire_preview_enabled: bool | None = None
    form_forwarding_enabled: bool | None = None
    carrier_connect_tier: str | None = None
    benefit_admin_notification_user: str | None = None
