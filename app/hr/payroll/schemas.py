from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.types import UUIDStr


class PayRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    label: str
    pay_schedule_name: str | None
    entity: str | None
    pay_run_type: str
    pay_date: date | None
    approve_by: datetime | None
    funding_method: str | None
    status: str
    action_text: str | None
    failure_reason: str | None
    archived_by: str | None


class PayRunPatch(BaseModel):
    status: str | None = None
    action_text: str | None = None
    failure_reason: str | None = None
    archived_by: str | None = None
    funding_method: str | None = None


class PayrollPeopleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    employee_name: str
    employee_title: str | None
    pay_schedule: str | None
    status: str
    bucket: str
    critical_missing_count: int
    missing_fields: str | None
    signatory_status: str | None


class PayrollPeoplePatch(BaseModel):
    status: str | None = None
    critical_missing_count: int | None = None
    missing_fields: str | None = None
    signatory_status: str | None = None
