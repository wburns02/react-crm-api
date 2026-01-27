"""
Pydantic schemas for Quote/Estimate API endpoints.
"""
from typing import Optional, List, Literal
from pydantic import BaseModel, Field


# Status literals matching frontend
QuoteStatus = Literal["draft", "sent", "accepted", "declined", "expired"]


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
    id: str
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None


class QuoteBase(BaseModel):
    """Base quote fields."""
    customer_id: int = Field(..., ge=1, description="Customer ID")
    status: QuoteStatus = Field(default="draft", description="Quote status")
    tax_rate: float = Field(default=0.0, ge=0, le=100, description="Tax rate percentage")
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
    status: Optional[QuoteStatus] = None
    line_items: Optional[List[LineItemCreate]] = None
    tax_rate: Optional[float] = Field(None, ge=0, le=100)
    valid_until: Optional[str] = None
    notes: Optional[str] = None
    terms: Optional[str] = None


class QuoteResponse(BaseModel):
    """Full quote response matching frontend Quote type."""
    id: str  # UUID as string for frontend
    quote_number: str
    customer_id: str
    customer_name: Optional[str] = None
    customer: Optional[CustomerSummary] = None

    status: QuoteStatus
    line_items: List[LineItemResponse]

    subtotal: float
    tax_rate: float
    tax: float
    total: float

    valid_until: Optional[str] = None
    notes: Optional[str] = None
    terms: Optional[str] = None

    created_at: Optional[str] = None
    updated_at: Optional[str] = None

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
