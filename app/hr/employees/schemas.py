from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.types import UUIDStr


CertKind = Literal[
    "tceq_os0", "tceq_mp", "cdl_class_b", "cdl_class_a", "dot_medical",
    "first_aid", "other",
]
CertStatus = Literal["active", "expired", "pending"]
DocKind = Literal[
    "i9", "w4", "handbook_ack", "direct_deposit", "drug_test",
    "dot_med_card", "cdl", "license", "other",
]
AccessSystem = Literal[
    "crm", "ringcentral", "google_workspace", "samsara", "adp", "other",
]


class CertificationIn(BaseModel):
    kind: CertKind
    number: str | None = None
    issued_at: date | None = None
    expires_at: date | None = None
    issuing_authority: str | None = None
    document_storage_key: str | None = None
    status: CertStatus = "active"
    notes: str | None = None


class CertificationPatch(BaseModel):
    kind: CertKind | None = None
    number: str | None = None
    issued_at: date | None = None
    expires_at: date | None = None
    issuing_authority: str | None = None
    document_storage_key: str | None = None
    status: CertStatus | None = None
    notes: str | None = None


class CertificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    employee_id: UUIDStr
    kind: CertKind
    number: str | None
    issued_at: date | None
    expires_at: date | None
    issuing_authority: str | None
    document_storage_key: str | None
    status: CertStatus
    notes: str | None
    created_at: datetime


class DocumentIn(BaseModel):
    kind: DocKind
    storage_key: str
    signed_document_id: UUIDStr | None = None
    expires_at: date | None = None


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    employee_id: UUIDStr
    kind: DocKind
    storage_key: str
    signed_document_id: UUIDStr | None
    uploaded_at: datetime
    expires_at: date | None


class TruckAssignmentIn(BaseModel):
    truck_id: UUIDStr


class TruckAssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    employee_id: UUIDStr
    truck_id: UUIDStr
    assigned_at: datetime
    unassigned_at: datetime | None
    assigned_by: int | None
    unassigned_by: int | None


class FuelCardAssignmentIn(BaseModel):
    card_id: UUIDStr


class FuelCardAssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    employee_id: UUIDStr
    card_id: UUIDStr
    assigned_at: datetime
    unassigned_at: datetime | None


class AccessGrantIn(BaseModel):
    system: AccessSystem
    identifier: str | None = None


class AccessGrantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    employee_id: UUIDStr
    system: AccessSystem
    identifier: str | None
    granted_at: datetime
    revoked_at: datetime | None
