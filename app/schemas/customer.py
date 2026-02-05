from pydantic import BaseModel, EmailStr, Field
from datetime import datetime, date
from typing import Optional
from decimal import Decimal

from app.schemas.types import UUIDStr


class CustomerBase(BaseModel):
    """Base customer schema."""

    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)

    # Address
    address_line1: Optional[str] = Field(None, max_length=255)
    address_line2: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=50)
    postal_code: Optional[str] = Field(None, max_length=20)

    # Status
    is_active: Optional[bool] = True

    # Lead/Sales tracking
    lead_source: Optional[str] = None
    lead_notes: Optional[str] = None
    prospect_stage: Optional[str] = None
    assigned_sales_rep: Optional[str] = None
    estimated_value: Optional[float] = None
    customer_type: Optional[str] = None

    # Septic system info
    tank_size_gallons: Optional[int] = None
    number_of_tanks: Optional[int] = None
    system_type: Optional[str] = None
    manufacturer: Optional[str] = None
    installer_name: Optional[str] = None
    subdivision: Optional[str] = None
    system_issued_date: Optional[date] = None

    # Tags
    tags: Optional[str] = None

    # Marketing
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_term: Optional[str] = None
    utm_content: Optional[str] = None
    gclid: Optional[str] = None
    landing_page: Optional[str] = None

    # Geo
    latitude: Optional[Decimal] = None
    longitude: Optional[Decimal] = None

    # Integrations
    default_payment_terms: Optional[str] = None
    quickbooks_customer_id: Optional[str] = None
    hubspot_contact_id: Optional[str] = None
    servicenow_ticket_ref: Optional[str] = None

    # Follow-up
    next_follow_up_date: Optional[date] = None


class CustomerCreate(CustomerBase):
    """Schema for creating a customer."""

    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)


class CustomerUpdate(CustomerBase):
    """Schema for updating a customer (all fields optional)."""

    pass


class CustomerResponse(CustomerBase):
    """Schema for customer response."""

    id: UUIDStr
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    first_touch_ts: Optional[datetime] = None
    last_touch_ts: Optional[datetime] = None

    class Config:
        from_attributes = True


class CustomerListResponse(BaseModel):
    """Paginated customer list response."""

    items: list[CustomerResponse]
    total: int
    page: int
    page_size: int
