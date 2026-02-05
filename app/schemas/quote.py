from pydantic import BaseModel, Field, field_validator
from datetime import datetime, date
from typing import Optional, List, Any, Union
from decimal import Decimal

from app.schemas.types import UUIDStr


class QuoteLineItem(BaseModel):
    """Schema for quote line item."""

    service: str
    description: Optional[str] = None
    quantity: float = 1
    rate: float
    amount: float


class QuoteBase(BaseModel):
    """Base quote schema."""

    customer_id: UUIDStr
    title: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    line_items: Optional[List[Any]] = []
    # Removed decimal_places constraint - let the database handle precision
    subtotal: Optional[Decimal] = None
    tax_rate: Optional[Decimal] = None
    tax: Optional[Decimal] = None
    discount: Optional[Decimal] = None
    total: Optional[Decimal] = None
    status: Optional[str] = Field("draft", max_length=30)
    valid_until: Optional[datetime] = None
    notes: Optional[str] = None
    terms: Optional[str] = None

    @field_validator("valid_until", mode="before")
    @classmethod
    def parse_valid_until(cls, v):
        """Parse date strings to datetime - accepts 'YYYY-MM-DD' or full ISO datetime."""
        if v is None:
            return None
        if isinstance(v, datetime):
            return v
        if isinstance(v, date):
            return datetime.combine(v, datetime.min.time())
        if isinstance(v, str):
            # Handle empty string
            if not v.strip():
                return None
            # Try parsing as date first (YYYY-MM-DD from HTML date input)
            try:
                parsed_date = datetime.strptime(v, "%Y-%m-%d")
                return parsed_date
            except ValueError:
                pass
            # Try parsing as ISO datetime
            try:
                return datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                pass
            # Try with timezone
            try:
                return datetime.fromisoformat(v)
            except ValueError:
                raise ValueError(f"Cannot parse date/datetime: {v}")
        return v


class QuoteCreate(QuoteBase):
    """Schema for creating a quote."""

    pass


class QuoteUpdate(BaseModel):
    """Schema for updating a quote."""

    title: Optional[str] = None
    description: Optional[str] = None
    line_items: Optional[List[Any]] = None
    subtotal: Optional[Decimal] = None
    tax_rate: Optional[Decimal] = None
    tax: Optional[Decimal] = None
    discount: Optional[Decimal] = None
    total: Optional[Decimal] = None
    status: Optional[str] = None
    valid_until: Optional[datetime] = None
    notes: Optional[str] = None
    terms: Optional[str] = None

    @field_validator("valid_until", mode="before")
    @classmethod
    def parse_valid_until(cls, v):
        """Parse date strings to datetime - accepts 'YYYY-MM-DD' or full ISO datetime."""
        if v is None:
            return None
        if isinstance(v, datetime):
            return v
        if isinstance(v, date):
            return datetime.combine(v, datetime.min.time())
        if isinstance(v, str):
            # Handle empty string
            if not v.strip():
                return None
            # Try parsing as date first (YYYY-MM-DD from HTML date input)
            try:
                parsed_date = datetime.strptime(v, "%Y-%m-%d")
                return parsed_date
            except ValueError:
                pass
            # Try parsing as ISO datetime
            try:
                return datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                pass
            # Try with timezone
            try:
                return datetime.fromisoformat(v)
            except ValueError:
                raise ValueError(f"Cannot parse date/datetime: {v}")
        return v


class QuoteResponse(QuoteBase):
    """Schema for quote response."""

    id: UUIDStr
    quote_number: Optional[str] = None
    # Customer details (populated from JOIN with customers table)
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_address: Optional[str] = None
    # Signature fields
    signature_data: Optional[str] = None
    signed_at: Optional[datetime] = None
    signed_by: Optional[str] = None
    approval_status: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    converted_to_work_order_id: Optional[UUIDStr] = None
    converted_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class QuoteListResponse(BaseModel):
    """Paginated quote list response."""

    items: list[QuoteResponse]
    total: int
    page: int
    page_size: int


class QuoteConvertRequest(BaseModel):
    """Schema for converting a quote to a work order."""

    job_type: str = Field(
        ...,
        description="Required job type: pumping, inspection, repair, installation, emergency, maintenance, grease_trap, camera_inspection",
    )
    scheduled_date: Optional[date] = Field(None, description="Optional scheduled date for the work order")
    technician_id: Optional[str] = Field(None, description="Optional technician UUID to assign")
    priority: str = Field("normal", description="Priority level: low, normal, high, urgent, emergency")
    notes: Optional[str] = Field(None, description="Additional notes for the work order")

    @field_validator("job_type")
    @classmethod
    def validate_job_type(cls, v):
        valid_types = [
            "pumping",
            "inspection",
            "repair",
            "installation",
            "emergency",
            "maintenance",
            "grease_trap",
            "camera_inspection",
        ]
        if v not in valid_types:
            raise ValueError(f"job_type must be one of: {', '.join(valid_types)}")
        return v

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v):
        valid_priorities = ["low", "normal", "high", "urgent", "emergency"]
        if v not in valid_priorities:
            raise ValueError(f"priority must be one of: {', '.join(valid_priorities)}")
        return v


class QuoteConvertResponse(BaseModel):
    """Response after converting a quote to a work order."""

    quote: QuoteResponse
    work_order_id: UUIDStr
    message: str
