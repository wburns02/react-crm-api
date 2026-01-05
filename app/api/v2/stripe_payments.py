"""
Stripe Payment Processing API Endpoints

Handles:
- Payment intent creation
- Payment confirmation
- Saved payment methods
- ACH/bank account setup
"""

from fastapi import APIRouter, HTTPException, Query
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional
from uuid import uuid4
import os

from app.api.deps import DbSession, CurrentUser


router = APIRouter()


# =============================================================================
# Configuration
# =============================================================================

# Get Stripe keys from environment (set in production)
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "sk_test_placeholder")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "pk_test_placeholder")


# =============================================================================
# Pydantic Schemas
# =============================================================================

class StripeConfig(BaseModel):
    """Stripe configuration for frontend."""
    publishable_key: str
    connected_account_id: Optional[str] = None


class CreatePaymentIntentRequest(BaseModel):
    """Request to create a payment intent."""
    invoice_id: str
    amount: int  # in cents
    currency: str = "usd"
    customer_email: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class PaymentIntentResponse(BaseModel):
    """Payment intent response."""
    client_secret: str
    payment_intent_id: str
    amount: int
    currency: str


class ConfirmPaymentRequest(BaseModel):
    """Request to confirm payment."""
    payment_intent_id: str
    invoice_id: str


class PaymentResult(BaseModel):
    """Payment result."""
    success: bool
    payment_id: str
    invoice_id: str
    amount: int
    status: str  # succeeded, processing, failed
    error_message: Optional[str] = None


class SavedPaymentMethod(BaseModel):
    """Saved payment method."""
    id: str
    stripe_payment_method_id: str
    type: str  # card, us_bank_account
    last4: str
    brand: Optional[str] = None
    is_default: bool = False


class SavePaymentMethodRequest(BaseModel):
    """Request to save payment method."""
    customer_id: int
    payment_method_id: str
    set_as_default: bool = False


class SetupACHRequest(BaseModel):
    """Request to set up ACH payment."""
    customer_id: int
    email: str


class ChargePaymentMethodRequest(BaseModel):
    """Request to charge saved payment method."""
    invoice_id: str
    payment_method_id: str
    amount: int  # in cents


class PaymentHistoryItem(BaseModel):
    """Payment history item."""
    id: str
    amount: int
    status: str
    created_at: str
    method: str


# =============================================================================
# Configuration Endpoints
# =============================================================================

@router.get("/config")
async def get_stripe_config(
    db: DbSession,
    current_user: CurrentUser,
) -> StripeConfig:
    """Get Stripe publishable key for frontend."""
    return StripeConfig(
        publishable_key=STRIPE_PUBLISHABLE_KEY,
        connected_account_id=None
    )


# =============================================================================
# Payment Intent Endpoints
# =============================================================================

@router.post("/create-intent")
async def create_payment_intent(
    request: CreatePaymentIntentRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> PaymentIntentResponse:
    """Create a payment intent for an invoice."""
    # In production, this would call Stripe API:
    # stripe.PaymentIntent.create(
    #     amount=request.amount,
    #     currency=request.currency,
    #     metadata={'invoice_id': request.invoice_id},
    # )

    # Mock response for development
    payment_intent_id = f"pi_{uuid4().hex[:24]}"
    client_secret = f"{payment_intent_id}_secret_{uuid4().hex[:24]}"

    return PaymentIntentResponse(
        client_secret=client_secret,
        payment_intent_id=payment_intent_id,
        amount=request.amount,
        currency=request.currency
    )


@router.post("/confirm")
async def confirm_payment(
    request: ConfirmPaymentRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> PaymentResult:
    """Confirm payment and update invoice status."""
    # In production:
    # 1. Verify payment intent with Stripe
    # 2. Update invoice status to 'paid'
    # 3. Create payment record

    payment_id = f"pay_{uuid4().hex[:16]}"

    return PaymentResult(
        success=True,
        payment_id=payment_id,
        invoice_id=request.invoice_id,
        amount=0,  # Would come from Stripe
        status="succeeded"
    )


# =============================================================================
# Payment Method Endpoints
# =============================================================================

@router.get("/customer/{customer_id}/payment-methods")
async def get_customer_payment_methods(
    customer_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Get saved payment methods for a customer."""
    # In production: fetch from database/Stripe

    # Mock data
    payment_methods = [
        SavedPaymentMethod(
            id="pm_1",
            stripe_payment_method_id=f"pm_{uuid4().hex[:24]}",
            type="card",
            last4="4242",
            brand="visa",
            is_default=True
        ),
        SavedPaymentMethod(
            id="pm_2",
            stripe_payment_method_id=f"pm_{uuid4().hex[:24]}",
            type="card",
            last4="1234",
            brand="mastercard",
            is_default=False
        ),
    ]

    return {"payment_methods": [pm.model_dump() for pm in payment_methods]}


@router.post("/save-payment-method")
async def save_payment_method(
    request: SavePaymentMethodRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> SavedPaymentMethod:
    """Save a payment method to customer account."""
    # In production:
    # 1. Attach payment method to Stripe customer
    # 2. Store reference in database

    return SavedPaymentMethod(
        id=f"pm_{uuid4().hex[:8]}",
        stripe_payment_method_id=request.payment_method_id,
        type="card",
        last4="4242",
        brand="visa",
        is_default=request.set_as_default
    )


@router.delete("/payment-methods/{payment_method_id}")
async def delete_payment_method(
    payment_method_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Delete a saved payment method."""
    # In production: detach from Stripe customer, delete from DB
    return {"success": True}


@router.post("/set-default-payment-method")
async def set_default_payment_method(
    customer_id: int = Query(...),
    payment_method_id: str = Query(...),
    db: DbSession = None,
    current_user: CurrentUser = None,
) -> dict:
    """Set a payment method as the default for a customer."""
    return {"success": True}


# =============================================================================
# Charge Endpoints
# =============================================================================

@router.post("/charge")
async def charge_payment_method(
    request: ChargePaymentMethodRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> PaymentResult:
    """Charge a saved payment method."""
    # In production:
    # 1. Create payment intent with saved payment method
    # 2. Confirm immediately
    # 3. Update invoice status

    payment_id = f"pay_{uuid4().hex[:16]}"

    return PaymentResult(
        success=True,
        payment_id=payment_id,
        invoice_id=request.invoice_id,
        amount=request.amount,
        status="succeeded"
    )


# =============================================================================
# ACH/Bank Account Endpoints
# =============================================================================

@router.post("/setup-ach")
async def setup_ach_payment(
    request: SetupACHRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Set up ACH payment for a customer."""
    # In production:
    # 1. Create Stripe SetupIntent for us_bank_account
    # 2. Return client secret for frontend

    setup_intent_id = f"seti_{uuid4().hex[:24]}"
    client_secret = f"{setup_intent_id}_secret_{uuid4().hex[:24]}"

    return {"setup_intent_client_secret": client_secret}


# =============================================================================
# Payment History Endpoints
# =============================================================================

@router.get("/invoice/{invoice_id}/history")
async def get_invoice_payment_history(
    invoice_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Get payment history for an invoice."""
    # Mock data
    payments = [
        PaymentHistoryItem(
            id=f"pay_{uuid4().hex[:8]}",
            amount=15000,  # $150.00 in cents
            status="succeeded",
            created_at=datetime.utcnow().isoformat(),
            method="card"
        ),
    ]

    return {"payments": [p.model_dump() for p in payments]}


# =============================================================================
# Refund Endpoints
# =============================================================================

@router.post("/refund")
async def create_refund(
    payment_id: str = Query(...),
    amount: Optional[int] = Query(None, description="Amount in cents, or null for full refund"),
    reason: Optional[str] = Query(None),
    db: DbSession = None,
    current_user: CurrentUser = None,
) -> dict:
    """Create a refund for a payment."""
    # In production: call Stripe refund API

    refund_id = f"re_{uuid4().hex[:16]}"

    return {
        "refund_id": refund_id,
        "payment_id": payment_id,
        "amount": amount,
        "status": "succeeded",
        "created_at": datetime.utcnow().isoformat()
    }


# =============================================================================
# Webhook Endpoint (for Stripe events)
# =============================================================================

@router.post("/webhook")
async def stripe_webhook(
    db: DbSession,
) -> dict:
    """Handle Stripe webhook events."""
    # In production:
    # 1. Verify webhook signature
    # 2. Process event (payment_intent.succeeded, etc.)
    # 3. Update database accordingly

    return {"received": True}
