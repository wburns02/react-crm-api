"""Pydantic schemas for /api/v2/realtors."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.types import UUIDStr


# ---------- Realtor Agent ----------


class RealtorAgentBase(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    brokerage: Optional[str] = Field(None, max_length=255)
    license_number: Optional[str] = Field(None, max_length=50)

    phone: str = Field(..., min_length=7, max_length=20)
    email: Optional[str] = Field(None, max_length=255)
    cell: Optional[str] = Field(None, max_length=20)
    preferred_contact: str = "call"

    coverage_area: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None

    stage: str = "cold"
    current_inspector: Optional[str] = None
    relationship_notes: Optional[str] = None

    one_pager_sent: bool = False
    one_pager_sent_date: Optional[datetime] = None

    assigned_rep: Optional[int] = None
    priority: int = 50
    notes: Optional[str] = None


class RealtorAgentCreate(RealtorAgentBase):
    id: Optional[UUIDStr] = None  # client-supplied id permitted (for migration)


class RealtorAgentUpdate(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    brokerage: Optional[str] = None
    license_number: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    cell: Optional[str] = None
    preferred_contact: Optional[str] = None
    coverage_area: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    stage: Optional[str] = None
    current_inspector: Optional[str] = None
    relationship_notes: Optional[str] = None
    next_follow_up: Optional[datetime] = None
    one_pager_sent: Optional[bool] = None
    one_pager_sent_date: Optional[datetime] = None
    assigned_rep: Optional[int] = None
    priority: Optional[int] = None
    notes: Optional[str] = None


class RealtorAgentResponse(RealtorAgentBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUIDStr
    call_attempts: int
    last_call_date: Optional[datetime]
    last_call_duration: Optional[int]
    last_disposition: Optional[str]
    next_follow_up: Optional[datetime]
    total_referrals: int
    total_revenue: Decimal
    last_referral_date: Optional[datetime]
    created_at: datetime
    updated_at: datetime


# ---------- Call Recording ----------


class CallRecord(BaseModel):
    disposition: str
    duration: int = 0


# ---------- Referral ----------


class ReferralBase(BaseModel):
    property_address: str = Field(..., min_length=1, max_length=500)
    homeowner_name: Optional[str] = None
    service_type: str = "inspection"
    invoice_amount: Optional[Decimal] = None
    status: str = "pending"
    referred_date: Optional[datetime] = None
    completed_date: Optional[datetime] = None
    notes: Optional[str] = None


class ReferralCreate(ReferralBase):
    id: Optional[UUIDStr] = None
    realtor_id: UUIDStr


class ReferralUpdate(BaseModel):
    property_address: Optional[str] = None
    homeowner_name: Optional[str] = None
    service_type: Optional[str] = None
    invoice_amount: Optional[Decimal] = None
    status: Optional[str] = None
    referred_date: Optional[datetime] = None
    completed_date: Optional[datetime] = None
    notes: Optional[str] = None


class ReferralResponse(ReferralBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUIDStr
    realtor_id: UUIDStr
    created_at: datetime
    updated_at: datetime


# ---------- Migrate Local ----------


class MigrateLocalRealtors(BaseModel):
    """Bulk migrate IndexedDB-cached realtor data to the cloud."""

    agents: List[RealtorAgentCreate] = []
    referrals: List[ReferralCreate] = []


class MigrateLocalRealtorsResponse(BaseModel):
    agents_imported: int
    agents_skipped: int
    referrals_imported: int
    referrals_skipped: int
