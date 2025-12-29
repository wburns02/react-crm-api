from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from app.models.invoice import InvoiceStatus


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
    id: str
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None


class InvoiceBase(BaseModel):
    """Base invoice schema."""
    customer_id: int
    work_order_id: Optional[int] = None
    status: InvoiceStatus = InvoiceStatus.draft
    line_items: list[LineItem] = []
    tax_rate: float = Field(0, ge=0, le=100)
    due_date: Optional[str] = None
    notes: Optional[str] = None
    terms: Optional[str] = None


class InvoiceCreate(InvoiceBase):
    """Schema for creating an invoice."""
    # Calculated fields are passed from frontend
    subtotal: Optional[float] = 0
    tax: Optional[float] = 0
    total: Optional[float] = 0


class InvoiceUpdate(BaseModel):
    """Schema for updating an invoice (all fields optional)."""
    customer_id: Optional[int] = None
    work_order_id: Optional[int] = None
    status: Optional[InvoiceStatus] = None
    line_items: Optional[list[LineItem]] = None
    subtotal: Optional[float] = None
    tax_rate: Optional[float] = Field(None, ge=0, le=100)
    tax: Optional[float] = None
    total: Optional[float] = None
    due_date: Optional[str] = None
    paid_date: Optional[str] = None
    notes: Optional[str] = None
    terms: Optional[str] = None


class InvoiceResponse(BaseModel):
    """Schema for invoice response."""
    id: str
    invoice_number: str
    customer_id: str
    customer_name: Optional[str] = None
    customer: Optional[CustomerSummary] = None
    work_order_id: Optional[str] = None
    status: InvoiceStatus
    line_items: list[LineItem]
    subtotal: float
    tax_rate: float
    tax: float
    total: float
    due_date: Optional[str] = None
    paid_date: Optional[str] = None
    notes: Optional[str] = None
    terms: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class InvoiceListResponse(BaseModel):
    """Paginated invoice list response."""
    items: list[InvoiceResponse]
    total: int
    page: int
    page_size: int
