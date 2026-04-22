"""Pydantic schemas for /api/v2/outbound-campaigns."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------- Campaign ----------


class CampaignBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    status: str = "draft"
    source_file: Optional[str] = None
    source_sheet: Optional[str] = None


class CampaignCreate(CampaignBase):
    id: Optional[str] = None  # client-supplied stable id permitted


class CampaignUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[str] = None


class CampaignCounters(BaseModel):
    total: int
    pending: int
    called: int
    connected: int
    interested: int
    voicemail: int
    no_answer: int
    callback_scheduled: int
    completed: int
    do_not_call: int


class CampaignResponse(CampaignBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    counters: CampaignCounters


# ---------- Contact ----------


class ContactBase(BaseModel):
    account_number: Optional[str] = None
    account_name: str = Field(..., min_length=1, max_length=255)
    company: Optional[str] = None
    phone: str = Field(..., min_length=1, max_length=32)
    email: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    service_zone: Optional[str] = None
    system_type: Optional[str] = None
    contract_type: Optional[str] = None
    contract_status: Optional[str] = None
    contract_start: Optional[date] = None
    contract_end: Optional[date] = None
    contract_value: Optional[Decimal] = None
    customer_type: Optional[str] = None
    call_priority_label: Optional[str] = None
    priority: int = 0
    opens: Optional[int] = None
    notes: Optional[str] = None


class ContactCreate(ContactBase):
    id: Optional[str] = None


class ContactUpdate(BaseModel):
    account_name: Optional[str] = Field(None, min_length=1, max_length=255)
    company: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    service_zone: Optional[str] = None
    system_type: Optional[str] = None
    call_priority_label: Optional[str] = None
    priority: Optional[int] = None
    notes: Optional[str] = None
    callback_date: Optional[datetime] = None
    assigned_rep: Optional[int] = None


class ContactResponse(ContactBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    campaign_id: str
    call_status: str
    call_attempts: int
    last_call_date: Optional[datetime] = None
    last_call_duration: Optional[int] = None
    last_disposition: Optional[str] = None
    callback_date: Optional[datetime] = None
    assigned_rep: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class BulkContactsCreate(BaseModel):
    contacts: List[ContactCreate]


class BulkContactsResponse(BaseModel):
    contacts: List[ContactResponse]


# ---------- Disposition ----------


class DispositionCreate(BaseModel):
    call_status: str
    notes: Optional[str] = None
    duration_sec: Optional[int] = None


class AttemptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    contact_id: str
    campaign_id: str
    rep_user_id: Optional[int] = None
    dispositioned_at: datetime
    call_status: str
    notes: Optional[str] = None
    duration_sec: Optional[int] = None


class DispositionResponse(BaseModel):
    contact: ContactResponse
    attempt: AttemptResponse


# ---------- Callback ----------


class CallbackCreate(BaseModel):
    contact_id: str
    campaign_id: str
    scheduled_for: datetime
    notes: Optional[str] = None


class CallbackUpdate(BaseModel):
    scheduled_for: Optional[datetime] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    completed_at: Optional[datetime] = None


class CallbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    contact_id: str
    campaign_id: str
    rep_user_id: Optional[int] = None
    scheduled_for: datetime
    notes: Optional[str] = None
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None


# ---------- Local migration ----------


class LegacyContactPayload(BaseModel):
    """Shape of a contact coming from the browser's IndexedDB dump.

    Tolerates unknown fields so minor client-side schema drift does not break
    the migration.
    """

    model_config = ConfigDict(extra="ignore")

    id: str
    campaign_id: str
    account_number: Optional[str] = None
    account_name: str
    company: Optional[str] = None
    phone: str
    email: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    service_zone: Optional[str] = None
    system_type: Optional[str] = None
    contract_type: Optional[str] = None
    contract_status: Optional[str] = None
    contract_value: Optional[Decimal] = None
    customer_type: Optional[str] = None
    call_priority_label: Optional[str] = None
    call_status: str
    call_attempts: int = 0
    last_call_date: Optional[datetime] = None
    last_call_duration: Optional[int] = None
    last_disposition: Optional[str] = None
    notes: Optional[str] = None
    callback_date: Optional[datetime] = None
    priority: int = 0
    opens: Optional[int] = None


class LegacyCampaignPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    description: Optional[str] = None
    status: Optional[str] = "active"
    source_file: Optional[str] = None
    source_sheet: Optional[str] = None


class LegacyCallbackPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: Optional[str] = None
    contact_id: str
    campaign_id: Optional[str] = None
    scheduled_for: datetime
    notes: Optional[str] = None
    status: Optional[str] = "scheduled"


class MigrateLocalRequest(BaseModel):
    campaigns: List[LegacyCampaignPayload] = Field(default_factory=list)
    contacts: List[LegacyContactPayload] = Field(default_factory=list)
    callbacks: List[LegacyCallbackPayload] = Field(default_factory=list)


class MigrateLocalImported(BaseModel):
    campaigns: int
    contacts: int
    attempts: int
    callbacks: int


class MigrateLocalResponse(BaseModel):
    imported: MigrateLocalImported
