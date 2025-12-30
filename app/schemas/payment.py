from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from decimal import Decimal


class PaymentBase(BaseModel):
    """Base payment schema."""
    invoice_id: Optional[int] = None
    customer_id: int
    amount: Decimal = Field(..., decimal_places=2)
    payment_method: Optional[str] = Field(None, max_length=50)
    payment_date: Optional[datetime] = None
    reference_number: Optional[str] = Field(None, max_length=100)
    status: Optional[str] = Field("completed", max_length=20)
    notes: Optional[str] = None


class PaymentCreate(PaymentBase):
    """Schema for creating a payment."""
    pass


class PaymentUpdate(BaseModel):
    """Schema for updating a payment."""
    invoice_id: Optional[int] = None
    amount: Optional[Decimal] = None
    payment_method: Optional[str] = None
    payment_date: Optional[datetime] = None
    reference_number: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class PaymentResponse(PaymentBase):
    """Schema for payment response."""
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PaymentListResponse(BaseModel):
    """Paginated payment list response."""
    items: list[PaymentResponse]
    total: int
    page: int
    page_size: int
