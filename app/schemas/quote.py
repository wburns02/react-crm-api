"""
Pydantic schemas for Quote/Estimate API endpoints.
"""
from typing import Optional, List, Literal
from pydantic import BaseModel, Field
from datetime import datetime


# Status literals matching frontend
QuoteStatus = Literal["draft", "sent", "accepted", "declined", "expired", "viewed", "rejected", "converted"]


class LineItemBase(BaseModel):
    """Base line item schema."""
    service: str = Field(..., min_length=1, description="Service name")
    description: Optional[str] = Field(None, description="Item description")
    quantity: float = Field(..., gt=0, description="Quantity")
    rate: float = Field(..., ge=0, description="Rate per unit")


class LineItemCreate(LineItemBase):
    """Schema for creating a line item."""
    pass


class LineItemResponse(LineItemBase):
    """Line item in response with calculated amount."""
    id: Optional[str] = None
    amount: float = Field(..., description="Calculated amount (quantity * rate)")


class CustomerSummary(BaseModel):
    """Embedded customer info for quote responses."""
    id: int
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None


class QuoteBase(BaseModel):
    """Base quote fields."""
    customer_id: int = Field(..., ge=1, description="Customer ID")
    status: Optional[str] = Field(default="draft", description="Quote status")
    tax_rate: Optional[float] = Field(default=0.0, ge=0, le=100, description="Tax rate percentage")
    valid_until: Optional[str] = Field(None, description="Expiration date YYYY-MM-DD")
    notes: Optional[str] = Field(None, description="Additional notes")
    terms: Optional[str] = Field(None, description="Terms and conditions")


class QuoteCreate(QuoteBase):
    """Schema for creating a quote."""
    line_items: List[LineItemCreate] = Field(..., min_length=1, description="At least one line item required")
    # Optional pre-calculated totals (will be recalculated server-side)
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    total: Optional[float] = None


class QuoteUpdate(BaseModel):
    """Schema for updating a quote (all fields optional for PATCH)."""
    customer_id: Optional[int] = Field(None, ge=1)
    status: Optional[str] = None
    line_items: Optional[List[LineItemCreate]] = None
    tax_rate: Optional[float] = Field(None, ge=0, le=100)
    valid_until: Optional[str] = None
    notes: Optional[str] = None
    terms: Optional[str] = None


class QuoteResponse(BaseModel):
    """Full quote response matching frontend Quote type."""
    id: int  # Integer ID from database
    quote_number: str
    customer_id: int  # Integer customer ID
    customer_name: Optional[str] = None
    customer: Optional[CustomerSummary] = None

    # Quote details
    title: Optional[str] = None
    description: Optional[str] = None

    status: str
    line_items: Optional[List[LineItemResponse]] = []

    # Totals
    subtotal: Optional[float] = 0
    tax_rate: Optional[float] = 0
    tax: Optional[float] = 0
    discount: Optional[float] = 0
    total: Optional[float] = 0

    valid_until: Optional[str] = None
    notes: Optional[str] = None
    terms: Optional[str] = None

    # Signature fields
    signature_data: Optional[str] = None
    signed_at: Optional[datetime] = None
    signed_by: Optional[str] = None

    # Approval workflow
    approval_status: Optional[str] = None
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None

    # Conversion tracking
    converted_to_work_order_id: Optional[int] = None
    converted_at: Optional[datetime] = None

    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class QuoteListResponse(BaseModel):
    """Paginated quote list response."""
    items: List[QuoteResponse]
    total: int
    page: int
    page_size: int


class QuoteSendResponse(BaseModel):
    """Response after sending a quote."""
    success: bool
    message: str
    quote: QuoteResponse


class QuoteConvertResponse(BaseModel):
    """Response after converting quote to invoice."""
    success: bool
    invoice_id: str
    message: str
