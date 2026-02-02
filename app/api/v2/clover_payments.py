"""
Clover Payment Processing API Endpoints for Invoices

Handles:
- Payment creation for invoices
- Payment confirmation
- Payment history
"""

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional
import uuid
import logging

from app.api.deps import DbSession, CurrentUser
from app.config import settings
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.services.clover_service import get_clover_service

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Pydantic Schemas
# =============================================================================


class CloverConfig(BaseModel):
    """Clover configuration for frontend."""

    merchant_id: str
    environment: str  # "sandbox" or "production"
    is_configured: bool


class CreatePaymentRequest(BaseModel):
    """Request to create a payment."""

    invoice_id: str
    amount: int  # in cents
    token: str  # Clover card token from frontend
    customer_email: Optional[str] = None


class PaymentResult(BaseModel):
    """Payment result."""

    success: bool
    payment_id: Optional[str] = None
    invoice_id: str
    amount: int
    status: str  # succeeded, processing, failed
    error_message: Optional[str] = None


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
async def get_clover_config(
    db: DbSession,
    current_user: CurrentUser,
) -> CloverConfig:
    """Get Clover configuration for frontend."""
    clover = get_clover_service()

    if not clover.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Clover is not configured. Please set CLOVER_MERCHANT_ID and CLOVER_API_KEY.",
        )

    return CloverConfig(
        merchant_id=settings.CLOVER_MERCHANT_ID or "",
        environment=settings.CLOVER_ENVIRONMENT,
        is_configured=True,
    )


# =============================================================================
# Payment Endpoints
# =============================================================================


@router.post("/charge")
async def charge_invoice(
    request: CreatePaymentRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> PaymentResult:
    """Charge a payment for an invoice using Clover."""
    clover = get_clover_service()

    if not clover.is_configured():
        raise HTTPException(status_code=503, detail="Clover is not configured")

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

        # Charge via Clover (capture immediately for invoice payments)
        payment_result = await clover.preauthorize(
            amount_cents=amount_cents,
            token=request.token,
            description=f"Invoice {invoice.invoice_number or invoice.id}",
            test_mode=False,
        )

        if not payment_result.success:
            return PaymentResult(
                success=False,
                invoice_id=request.invoice_id,
                amount=amount_cents,
                status="failed",
                error_message=payment_result.error_message,
            )

        # Capture the pre-auth immediately
        capture_result = await clover.capture(
            charge_id=payment_result.charge_id,
            amount_cents=amount_cents,
            test_mode=payment_result.is_test,
        )

        if not capture_result.success:
            return PaymentResult(
                success=False,
                invoice_id=request.invoice_id,
                amount=amount_cents,
                status="failed",
                error_message=capture_result.error_message,
            )

        # Update invoice status
        amount_dollars = amount_cents / 100
        invoice.status = "paid"
        invoice.paid_amount = amount_dollars
        invoice.paid_date = datetime.utcnow().date()

        # Create payment record
        payment = Payment(
            invoice_id=invoice.id,
            customer_id=None,
            amount=amount_dollars,
            payment_method="card",
            status="completed",
            payment_date=datetime.utcnow(),
        )
        # Store Clover charge ID in stripe field for now (or add clover_charge_id column)
        if hasattr(payment, 'stripe_payment_intent_id'):
            payment.stripe_payment_intent_id = capture_result.charge_id
        db.add(payment)

        await db.commit()
        await db.refresh(invoice)
        await db.refresh(payment)

        logger.info(f"Payment captured for invoice {invoice.id}: ${amount_dollars}")

        return PaymentResult(
            success=True,
            payment_id=str(payment.id),
            invoice_id=str(invoice.id),
            amount=amount_cents,
            status="succeeded",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error charging invoice: {e}")
        raise HTTPException(status_code=500, detail="Failed to process payment")


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
# Refund Endpoint
# =============================================================================


@router.post("/refund")
async def create_refund(
    payment_id: str = Query(...),
    amount: Optional[int] = Query(None, description="Amount in cents, or null for full refund"),
    db: DbSession = None,
    current_user: CurrentUser = None,
) -> dict:
    """Create a refund for a payment."""
    clover = get_clover_service()

    if not clover.is_configured():
        raise HTTPException(status_code=503, detail="Clover is not configured")

    try:
        # Get payment record
        result = await db.execute(
            select(Payment).where(Payment.id == int(payment_id))
        )
        payment = result.scalar_one_or_none()

        if not payment:
            raise HTTPException(status_code=404, detail="Payment not found")

        # Get charge ID (stored in stripe_payment_intent_id field)
        charge_id = getattr(payment, 'stripe_payment_intent_id', None)
        if not charge_id:
            raise HTTPException(status_code=400, detail="Payment has no charge ID for refund")

        # Create refund via Clover
        refund_result = await clover.refund(
            charge_id=charge_id,
            amount_cents=amount,
            test_mode=charge_id.startswith("test_"),
        )

        if not refund_result.success:
            raise HTTPException(status_code=400, detail=refund_result.error_message)

        return {
            "refund_id": f"refund_{uuid.uuid4().hex[:12]}",
            "payment_id": payment_id,
            "amount": amount or int((payment.amount or 0) * 100),
            "status": "succeeded",
            "created_at": datetime.utcnow().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating refund: {e}")
        raise HTTPException(status_code=500, detail="Failed to process refund")
