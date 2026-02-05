"""
Stripe Payment Processing API Endpoints

Handles:
- Payment intent creation
- Payment confirmation
- Saved payment methods
- ACH/bank account setup
- Webhook processing
"""

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import select
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional
from uuid import uuid4
import uuid
import logging

import stripe

from app.api.deps import DbSession, CurrentUser
from app.config import settings
from app.models.invoice import Invoice
from app.models.payment import Payment

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Stripe Configuration
# =============================================================================

# Initialize Stripe with API key from settings
if settings.STRIPE_SECRET_KEY:
    stripe.api_key = settings.STRIPE_SECRET_KEY
else:
    logger.warning("STRIPE_SECRET_KEY not configured - payment processing disabled")


def is_stripe_configured() -> bool:
    """Check if Stripe is properly configured."""
    return bool(settings.STRIPE_SECRET_KEY and settings.STRIPE_PUBLISHABLE_KEY)


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
    if not settings.STRIPE_PUBLISHABLE_KEY:
        raise HTTPException(
            status_code=503,
            detail="Stripe is not configured. Please set STRIPE_PUBLISHABLE_KEY.",
        )
    return StripeConfig(publishable_key=settings.STRIPE_PUBLISHABLE_KEY, connected_account_id=None)


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
    if not is_stripe_configured():
        raise HTTPException(status_code=503, detail="Stripe is not configured")

    try:
        # Verify invoice exists
        result = await db.execute(
            select(Invoice).where(Invoice.id == uuid.UUID(request.invoice_id))
        )
        invoice = result.scalar_one_or_none()

        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice not found")

        # Use invoice total if amount not provided, otherwise use requested amount
        amount_cents = request.amount
        if amount_cents <= 0:
            # Calculate from invoice
            amount_cents = int((float(invoice.amount) or 0) * 100)

        if amount_cents <= 0:
            raise HTTPException(status_code=400, detail="Invalid payment amount")

        # Create Stripe payment intent
        intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency=request.currency,
            metadata={
                "invoice_id": str(invoice.id),
                "invoice_number": invoice.invoice_number or "",
                "customer_id": str(invoice.customer_id) if invoice.customer_id else "",
            },
            receipt_email=request.customer_email,
        )

        logger.info(f"Created payment intent {intent.id} for invoice {invoice.id}")

        return PaymentIntentResponse(
            client_secret=intent.client_secret,
            payment_intent_id=intent.id,
            amount=intent.amount,
            currency=intent.currency,
        )

    except stripe.error.StripeError as e:
        logger.error(f"Stripe error creating payment intent: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating payment intent: {e}")
        raise HTTPException(status_code=500, detail="Failed to create payment intent")


@router.post("/confirm")
async def confirm_payment(
    request: ConfirmPaymentRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> PaymentResult:
    """Confirm payment and update invoice status."""
    if not is_stripe_configured():
        raise HTTPException(status_code=503, detail="Stripe is not configured")

    try:
        # Retrieve payment intent from Stripe
        intent = stripe.PaymentIntent.retrieve(request.payment_intent_id)

        if intent.status != "succeeded":
            return PaymentResult(
                success=False,
                payment_id="",
                invoice_id=request.invoice_id,
                amount=intent.amount,
                status=intent.status,
                error_message=f"Payment status: {intent.status}",
            )

        # Get invoice
        result = await db.execute(
            select(Invoice).where(Invoice.id == uuid.UUID(request.invoice_id))
        )
        invoice = result.scalar_one_or_none()

        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice not found")

        # Update invoice status
        amount_dollars = intent.amount / 100
        invoice.status = "paid"
        invoice.paid_amount = amount_dollars
        invoice.paid_date = datetime.utcnow().date()

        # Create payment record (id is auto-generated integer)
        payment = Payment(
            invoice_id=invoice.id,
            customer_id=None,  # We don't have integer customer_id readily available
            amount=amount_dollars,
            payment_method="card",
            stripe_payment_intent_id=intent.id,
            stripe_charge_id=intent.latest_charge if hasattr(intent, "latest_charge") else None,
            status="completed",
            payment_date=datetime.utcnow(),
        )
        db.add(payment)

        await db.commit()
        await db.refresh(invoice)
        await db.refresh(payment)

        logger.info(f"Payment confirmed for invoice {invoice.id}: ${amount_dollars}")

        return PaymentResult(
            success=True,
            payment_id=str(payment.id),
            invoice_id=str(invoice.id),
            amount=intent.amount,
            status="succeeded",
        )

    except stripe.error.StripeError as e:
        logger.error(f"Stripe error confirming payment: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error confirming payment: {e}")
        raise HTTPException(status_code=500, detail="Failed to confirm payment")


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
    # For now, return empty list - saved payment methods require Stripe Customer IDs
    # which would need to be stored in the database
    return {"payment_methods": []}



# NOTE: Saved payment method endpoints (save, delete, set-default) removed 2026-02-05.
# Stripe payment methods are deprecated in favor of Clover POS integration.
# See /payments/clover/ endpoints for current payment processing.


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
    if not is_stripe_configured():
        raise HTTPException(status_code=503, detail="Stripe is not configured")

    try:
        # Create and confirm payment intent with saved payment method
        intent = stripe.PaymentIntent.create(
            amount=request.amount,
            currency="usd",
            payment_method=request.payment_method_id,
            confirm=True,
            off_session=True,
            metadata={"invoice_id": request.invoice_id},
        )

        if intent.status == "succeeded":
            # Update invoice
            result = await db.execute(
                select(Invoice).where(Invoice.id == uuid.UUID(request.invoice_id))
            )
            invoice = result.scalar_one_or_none()

            if invoice:
                invoice.status = "paid"
                invoice.paid_amount = intent.amount / 100
                invoice.paid_date = datetime.utcnow().date()

                payment = Payment(
                    invoice_id=invoice.id,
                    amount=intent.amount / 100,
                    payment_method="card",
                    stripe_payment_intent_id=intent.id,
                    status="completed",
                    payment_date=datetime.utcnow(),
                )
                db.add(payment)
                await db.commit()
                await db.refresh(payment)

            return PaymentResult(
                success=True,
                payment_id=str(payment.id) if payment else "",
                invoice_id=request.invoice_id,
                amount=intent.amount,
                status="succeeded",
            )
        else:
            return PaymentResult(
                success=False,
                payment_id="",
                invoice_id=request.invoice_id,
                amount=request.amount,
                status=intent.status,
                error_message=f"Payment {intent.status}",
            )

    except stripe.error.CardError as e:
        return PaymentResult(
            success=False,
            payment_id="",
            invoice_id=request.invoice_id,
            amount=request.amount,
            status="failed",
            error_message=str(e),
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
    if not is_stripe_configured():
        raise HTTPException(status_code=503, detail="Stripe is not configured")

    try:
        # Create SetupIntent for ACH
        setup_intent = stripe.SetupIntent.create(
            payment_method_types=["us_bank_account"],
            usage="off_session",
        )

        return {"setup_intent_client_secret": setup_intent.client_secret}

    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


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
    try:
        # Query payments from database
        result = await db.execute(
            select(Payment).where(Payment.invoice_id == uuid.UUID(invoice_id))
        )
        payments = result.scalars().all()

        history = [
            PaymentHistoryItem(
                id=str(p.id),
                amount=int((p.amount or 0) * 100),  # Convert to cents
                status=p.status or "unknown",
                created_at=p.payment_date.isoformat() if p.payment_date else "",
                method=p.payment_method or "card",
            )
            for p in payments
        ]

        return {"payments": [h.model_dump() for h in history]}

    except Exception as e:
        logger.error(f"Error fetching payment history: {e}")
        return {"payments": []}


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
    if not is_stripe_configured():
        raise HTTPException(status_code=503, detail="Stripe is not configured")

    try:
        # Get payment record
        result = await db.execute(
            select(Payment).where(Payment.id == uuid.UUID(payment_id))
        )
        payment = result.scalar_one_or_none()

        if not payment or not payment.stripe_payment_intent_id:
            raise HTTPException(status_code=404, detail="Payment not found or not refundable")

        # Create Stripe refund
        refund_params = {"payment_intent": payment.stripe_payment_intent_id}
        if amount:
            refund_params["amount"] = amount
        if reason:
            refund_params["reason"] = reason

        refund = stripe.Refund.create(**refund_params)

        return {
            "refund_id": refund.id,
            "payment_id": payment_id,
            "amount": refund.amount,
            "status": refund.status,
            "created_at": datetime.utcnow().isoformat(),
        }

    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# Webhook Endpoint (for Stripe events)
# =============================================================================


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: DbSession,
) -> dict:
    """Handle Stripe webhook events."""
    if not settings.STRIPE_WEBHOOK_SECRET:
        logger.warning("Stripe webhook received but STRIPE_WEBHOOK_SECRET not configured")
        return {"received": True, "warning": "Webhook secret not configured"}

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Handle the event
    if event.type == "payment_intent.succeeded":
        intent = event.data.object
        invoice_id = intent.metadata.get("invoice_id")

        if invoice_id:
            try:
                result = await db.execute(
                    select(Invoice).where(Invoice.id == uuid.UUID(invoice_id))
                )
                invoice = result.scalar_one_or_none()

                if invoice and invoice.status != "paid":
                    invoice.status = "paid"
                    invoice.paid_amount = intent.amount / 100
                    invoice.paid_date = datetime.utcnow().date()
                    await db.commit()
                    logger.info(f"Webhook: Updated invoice {invoice_id} to paid")
            except Exception as e:
                logger.error(f"Webhook: Error updating invoice: {e}")

    elif event.type == "payment_intent.payment_failed":
        intent = event.data.object
        logger.warning(f"Payment failed for intent {intent.id}")

    return {"received": True}
