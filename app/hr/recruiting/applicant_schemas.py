from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.types import UUIDStr


Stage = Literal["applied", "screen", "ride_along", "offer", "hired", "rejected", "withdrawn"]
ApplicantSource = Literal[
    "careers_page", "indeed", "ziprecruiter", "facebook", "referral", "manual", "email"
]


class ApplicantIn(BaseModel):
    first_name: str = Field(min_length=1, max_length=128)
    last_name: str = Field(min_length=1, max_length=128)
    email: EmailStr
    phone: str | None = None
    source: ApplicantSource = "manual"
    source_ref: str | None = None


class ApplicantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    first_name: str
    last_name: str
    email: str
    phone: str | None
    resume_storage_key: str | None
    source: ApplicantSource
    source_ref: str | None
    sms_consent_given: bool
    created_at: datetime


class ApplicationIn(BaseModel):
    applicant_id: UUIDStr
    requisition_id: UUIDStr
    stage: Stage = "applied"
    assigned_recruiter_id: int | None = None
    notes: str | None = None
    answers: dict[str, Any] | None = None


class ApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    applicant_id: UUIDStr
    requisition_id: UUIDStr
    stage: Stage
    stage_entered_at: datetime
    assigned_recruiter_id: int | None
    rejection_reason: str | None
    rating: int | None
    notes: str | None
    created_at: datetime


class ApplicationWithApplicantOut(ApplicationOut):
    applicant: ApplicantOut


class StageTransitionIn(BaseModel):
    stage: Stage
    rejection_reason: str | None = None
    note: str | None = None


class ApplicationEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    application_id: UUIDStr
    event_type: str
    user_id: int | None
    payload: dict[str, Any] | None
    created_at: datetime


class PublicApplyIn(BaseModel):
    first_name: str = Field(min_length=1, max_length=128)
    last_name: str = Field(min_length=1, max_length=128)
    email: EmailStr
    phone: str | None = None
    answers: dict[str, Any] | None = None
    sms_consent: bool = False
    source: ApplicantSource = "careers_page"
    source_ref: str | None = None
