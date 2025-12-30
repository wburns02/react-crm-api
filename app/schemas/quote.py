from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Any
from decimal import Decimal


class QuoteLineItem(BaseModel):
    """Schema for quote line item."""
    service: str
    description: Optional[str] = None
    quantity: float = 1
    rate: float
    amount: float


class QuoteBase(BaseModel):
    """Base quote schema."""
    customer_id: int
    title: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    line_items: Optional[List[Any]] = []
    subtotal: Optional[Decimal] = Field(None, decimal_places=2)
    tax_rate: Optional[Decimal] = Field(None, decimal_places=2)
    tax: Optional[Decimal] = Field(None, decimal_places=2)
    discount: Optional[Decimal] = Field(None, decimal_places=2)
    total: Optional[Decimal] = Field(None, decimal_places=2)
    status: Optional[str] = Field("draft", max_length=30)
    valid_until: Optional[datetime] = None
    notes: Optional[str] = None
    terms: Optional[str] = None


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


class QuoteResponse(QuoteBase):
    """Schema for quote response."""
    id: int
    quote_number: Optional[str] = None
    signature_data: Optional[str] = None
    signed_at: Optional[datetime] = None
    signed_by: Optional[str] = None
    approval_status: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    converted_to_work_order_id: Optional[str] = None
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
