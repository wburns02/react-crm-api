from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from decimal import Decimal


class PaymentBase(BaseModel):
    """Base payment schema - matches Flask database."""

    customer_id: int
    work_order_id: Optional[str] = None  # Flask uses work_order_id not invoice_id
    amount: Decimal = Field(..., decimal_places=2)
    currency: Optional[str] = Field("USD", max_length=3)
    payment_method: Optional[str] = Field(None, max_length=50)
    status: Optional[str] = Field("pending", max_length=30)
    description: Optional[str] = None

    # Stripe fields (optional)
    stripe_payment_intent_id: Optional[str] = None
    stripe_charge_id: Optional[str] = None
    stripe_customer_id: Optional[str] = None


class PaymentCreate(PaymentBase):
    """Schema for creating a payment."""

    pass


class PaymentUpdate(BaseModel):
    """Schema for updating a payment."""

    amount: Optional[Decimal] = None
    payment_method: Optional[str] = None
    status: Optional[str] = None
    description: Optional[str] = None
    receipt_url: Optional[str] = None


class PaymentResponse(PaymentBase):
    """Schema for payment response."""

    id: int
    receipt_url: Optional[str] = None
    failure_reason: Optional[str] = None
    refund_amount: Optional[Decimal] = None
    refund_reason: Optional[str] = None
    refunded: Optional[bool] = False
    refund_id: Optional[str] = None
    refunded_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PaymentListResponse(BaseModel):
    """Paginated payment list response."""

    items: list[PaymentResponse]
    total: int
    page: int
    page_size: int
