from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class SMSConsentBase(BaseModel):
    """Base SMS consent schema."""
    customer_id: int
    phone_number: str = Field(..., max_length=20)
    consent_status: Optional[str] = Field("pending", max_length=20)
    consent_source: Optional[str] = Field(None, max_length=50)


class SMSConsentCreate(SMSConsentBase):
    """Schema for creating SMS consent."""
    pass


class SMSConsentUpdate(BaseModel):
    """Schema for updating SMS consent."""
    consent_status: Optional[str] = None
    consent_source: Optional[str] = None
    double_opt_in_confirmed: Optional[bool] = None
    tcpa_disclosure_accepted: Optional[bool] = None


class SMSConsentResponse(SMSConsentBase):
    """Schema for SMS consent response."""
    id: int
    opt_in_timestamp: Optional[datetime] = None
    opt_in_ip_address: Optional[str] = None
    double_opt_in_confirmed: Optional[bool] = None
    double_opt_in_timestamp: Optional[datetime] = None
    opt_out_timestamp: Optional[datetime] = None
    opt_out_reason: Optional[str] = None
    tcpa_disclosure_version: Optional[str] = None
    tcpa_disclosure_accepted: Optional[bool] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SMSConsentListResponse(BaseModel):
    """Paginated SMS consent list response."""
    items: list[SMSConsentResponse]
    total: int
    page: int
    page_size: int


class SMSConsentStats(BaseModel):
    """SMS consent statistics."""
    total: int
    opted_in: int
    opted_out: int
    pending: int
    double_opt_in_rate: float
