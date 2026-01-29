"""
Pydantic schemas for booking API.
"""

from datetime import date, time, datetime
from typing import Optional
from decimal import Decimal
from pydantic import BaseModel, Field, EmailStr


class BookingCreate(BaseModel):
    """Schema for creating a new booking."""

    # Customer info
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    phone: str = Field(..., min_length=10, max_length=20)
    service_address: Optional[str] = None

    # Service details
    service_type: str = Field(default="pumping")
    scheduled_date: date
    time_slot: Optional[str] = Field(None, pattern="^(morning|afternoon|any)$")

    # Payment
    payment_token: Optional[str] = None  # Clover token (not needed for test mode)

    # Consent
    overage_acknowledged: bool = Field(default=False)
    sms_consent: bool = Field(default=False)

    # Notes
    notes: Optional[str] = None

    # Test mode
    test_mode: bool = Field(default=False, description="If true, simulates payment without charging")


class BookingResponse(BaseModel):
    """Schema for booking response."""

    id: str
    customer_first_name: str
    customer_last_name: str
    customer_email: Optional[str]
    customer_phone: str
    service_address: Optional[str]

    service_type: str
    scheduled_date: date
    time_slot: Optional[str]
    time_window_start: Optional[time]
    time_window_end: Optional[time]

    # Pricing
    base_price: Decimal
    included_gallons: int
    overage_rate: Decimal
    preauth_amount: Optional[Decimal]

    # Status
    status: str
    payment_status: str
    is_test: bool

    # Timestamps
    created_at: datetime

    class Config:
        from_attributes = True


class BookingCaptureRequest(BaseModel):
    """Schema for capturing payment after service."""

    actual_gallons: int = Field(..., ge=0, le=50000)
    notes: Optional[str] = None


class BookingCaptureResponse(BaseModel):
    """Schema for capture response."""

    id: str
    actual_gallons: int
    overage_gallons: int
    overage_amount: Decimal
    final_amount: Decimal
    payment_status: str
    captured_at: Optional[datetime]

    class Config:
        from_attributes = True


class PricingInfo(BaseModel):
    """Schema for pricing information."""

    service_type: str
    base_price: Decimal
    included_gallons: int
    overage_rate: Decimal
    preauth_amount: Decimal
    description: str


class BookingListResponse(BaseModel):
    """Schema for listing bookings."""

    items: list[BookingResponse]
    total: int
    page: int
    page_size: int
