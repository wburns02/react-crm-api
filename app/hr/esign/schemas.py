from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.types import UUIDStr


class SignatureRequestCreateIn(BaseModel):
    document_template_kind: str
    signer_email: str
    signer_name: str
    signer_user_id: int | None = None
    field_values: dict = {}
    workflow_task_id: UUIDStr | None = None
    ttl_days: int = 7


class SignatureRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    token: str
    signer_email: str
    signer_name: str
    status: str
    expires_at: datetime


class SubmitSignatureIn(BaseModel):
    signature_image_base64: str  # PNG data URL or raw base64
    consent_confirmed: bool
