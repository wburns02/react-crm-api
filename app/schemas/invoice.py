from pydantic import BaseModel, Field
from datetime import datetime, date
from typing import Optional, Literal
from decimal import Decimal

from app.schemas.types import UUIDStr


# Valid invoice status values
INVOICE_STATUSES = Literal["draft", "sent", "paid", "overdue", "void"]


class LineItem(BaseModel):
    """Schema for invoice line item."""

    id: Optional[str] = None
    service: str = Field(..., min_length=1)
    description: Optional[str] = None
    quantity: float = Field(..., ge=0)
    rate: float = Field(..., ge=0)
    amount: float = Field(..., ge=0)


class CustomerSummary(BaseModel):
    """Minimal customer info for invoice response."""

    id: UUIDStr
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None


class InvoiceBase(BaseModel):
    """Base invoice schema."""

    customer_id: UUIDStr
    work_order_id: Optional[UUIDStr] = None  # UUID as string
    status: Optional[str] = None  # Don't send default - let DB handle
    line_items: Optional[list[LineItem]] = []
    notes: Optional[str] = None


class InvoiceCreate(InvoiceBase):
    """Schema for creating an invoice."""

    invoice_number: Optional[str] = None
    issue_date: Optional[date] = None
    due_date: Optional[date] = None
    amount: Optional[Decimal] = 0
    currency: Optional[str] = "USD"


class InvoiceUpdate(BaseModel):
    """Schema for updating an invoice (all fields optional)."""

    customer_id: Optional[str] = None
    work_order_id: Optional[str] = None
    status: Optional[str] = None
    line_items: Optional[list[LineItem]] = None
    amount: Optional[Decimal] = None
    paid_amount: Optional[Decimal] = None
    issue_date: Optional[date] = None
    due_date: Optional[date] = None
    paid_date: Optional[date] = None
    notes: Optional[str] = None


class InvoiceResponse(BaseModel):
    """Schema for invoice response."""

    id: UUIDStr  # UUID as string
    invoice_number: Optional[str] = None
    customer_id: UUIDStr  # UUID derived from integer customer ID
    customer_name: Optional[str] = None
    customer: Optional[CustomerSummary] = None
    work_order_id: Optional[UUIDStr] = None  # UUID as string
    status: str
    line_items: Optional[list[LineItem]] = []

    # Frontend expects these calculated fields
    subtotal: Optional[float] = 0
    tax_rate: Optional[float] = 0
    tax: Optional[float] = 0
    total: Optional[float] = 0

    # Legacy fields (also kept for compatibility)
    amount: Optional[float] = 0
    paid_amount: Optional[float] = 0
    currency: Optional[str] = "USD"

    # Dates
    issue_date: Optional[date] = None
    due_date: Optional[date] = None
    paid_date: Optional[date] = None

    # Additional fields from Flask
    external_payment_link: Optional[str] = None
    pdf_url: Optional[str] = None
    notes: Optional[str] = None
    terms: Optional[str] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class InvoiceListResponse(BaseModel):
    """Paginated invoice list response."""

    items: list[InvoiceResponse]
    total: int
    page: int
    page_size: int
