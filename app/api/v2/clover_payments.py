"""
Clover Payment Processing API Endpoints

Handles:
- REST API data access (merchant, payments, orders, items)
- Payment sync from Clover to CRM
- Payment reconciliation
- Payment creation for invoices (ecommerce - future)
- Payment history
"""

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select, text
from datetime import datetime, timezone
from decimal import Decimal
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
    merchant_name: Optional[str] = None
    environment: str
    is_configured: bool
    rest_api_available: bool = False
    ecommerce_available: bool = False


class CreatePaymentRequest(BaseModel):
    """Request to create a payment."""

    invoice_id: str
    amount: int  # in cents
    token: str  # Clover card token from frontend
    customer_email: Optional[str] = None


class CollectPaymentRequest(BaseModel):
    """Request to collect a payment (admin or tech, any method)."""

    work_order_id: Optional[str] = None
    invoice_id: Optional[str] = None
    customer_id: Optional[str] = None
    amount: float  # in dollars
    payment_method: str = "cash"  # cash, check, card, ach, other
    check_number: Optional[str] = None
    reference_number: Optional[str] = None
    notes: Optional[str] = None
    auto_create_invoice: bool = True


class PaymentResultSchema(BaseModel):
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
) -> dict:
    """Get Clover configuration for frontend with capability detection."""
    clover = get_clover_service()

    if not clover.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Clover is not configured. Please set CLOVER_MERCHANT_ID and CLOVER_API_KEY.",
        )

    # Check REST API access by fetching merchant info
    merchant = await clover.get_merchant()
    rest_available = merchant is not None
    merchant_name = merchant.get("name") if merchant else None

    # Check ecommerce access
    ecomm_available = await clover.check_ecommerce_access()

    return {
        "merchant_id": settings.CLOVER_MERCHANT_ID or "",
        "merchant_name": merchant_name,
        "environment": settings.CLOVER_ENVIRONMENT,
        "is_configured": True,
        "rest_api_available": rest_available,
        "ecommerce_available": ecomm_available,
    }


# =============================================================================
# REST API Data Endpoints (read-only, works with current token)
# =============================================================================


@router.get("/merchant")
async def get_merchant_info(
    current_user: CurrentUser,
) -> dict:
    """Get merchant profile from Clover."""
    clover = get_clover_service()
    if not clover.is_configured():
        raise HTTPException(status_code=503, detail="Clover is not configured")

    merchant = await clover.get_merchant()
    if not merchant:
        raise HTTPException(status_code=502, detail="Failed to fetch merchant data from Clover")

    return {
        "id": merchant.get("id"),
        "name": merchant.get("name"),
        "website": merchant.get("website"),
        "owner": merchant.get("owner", {}).get("id") if isinstance(merchant.get("owner"), dict) else merchant.get("owner"),
        "address": merchant.get("address"),
        "phone": merchant.get("phoneNumber"),
    }


@router.get("/payments")
async def list_clover_payments(
    current_user: CurrentUser,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    """List payments from Clover POS device."""
    try:
        clover = get_clover_service()
        if not clover.is_configured():
            # Return empty list instead of 503 - not configured is not an error
            return {"payments": [], "total": 0, "error": "Clover not configured"}

        data = await clover.list_payments(limit=limit, offset=offset)
        if data is None:
            # Return empty list instead of 502 - failed API calls shouldn't break UI
            return {"payments": [], "total": 0, "error": "Could not fetch from Clover API"}

        elements = data.get("elements", [])
        payments = []
        for p in elements:
            tender = p.get("tender", {})
            payments.append({
                "id": p.get("id"),
                "amount": p.get("amount", 0),
                "amount_dollars": round(p.get("amount", 0) / 100, 2),
                "tip_amount": p.get("tipAmount", 0),
                "tax_amount": p.get("taxAmount", 0),
                "result": p.get("result"),
                "tender_label": tender.get("label", "Unknown"),
                "tender_id": tender.get("id"),
                "order_id": p.get("order", {}).get("id") if isinstance(p.get("order"), dict) else None,
                "employee_id": p.get("employee", {}).get("id") if isinstance(p.get("employee"), dict) else None,
                "created_time": p.get("createdTime"),
                "offline": p.get("offline", False),
            })

        return {"payments": payments, "total": len(payments)}
    except Exception as e:
        import logging
        logging.error(f"Clover payments endpoint error: {e}")
        # Return empty list instead of 500 - don't break UI
        return {"payments": [], "total": 0, "error": str(e)}


@router.get("/orders")
async def list_clover_orders(
    current_user: CurrentUser,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    """List orders from Clover with line items."""
    clover = get_clover_service()
    if not clover.is_configured():
        raise HTTPException(status_code=503, detail="Clover is not configured")

    data = await clover.list_orders(limit=limit, offset=offset)
    if data is None:
        raise HTTPException(status_code=502, detail="Failed to fetch orders from Clover")

    elements = data.get("elements", [])
    orders = []
    for o in elements:
        line_items_data = o.get("lineItems", {}).get("elements", [])
        line_items = [
            {
                "id": li.get("id"),
                "name": li.get("name"),
                "price": li.get("price", 0),
                "price_dollars": round(li.get("price", 0) / 100, 2),
            }
            for li in line_items_data
        ]
        orders.append({
            "id": o.get("id"),
            "total": o.get("total", 0),
            "total_dollars": round(o.get("total", 0) / 100, 2),
            "state": o.get("state"),
            "payment_state": o.get("paymentState"),
            "currency": o.get("currency", "USD"),
            "line_items": line_items,
            "created_time": o.get("createdTime"),
            "modified_time": o.get("modifiedTime"),
        })

    return {"orders": orders, "total": len(orders)}


@router.get("/items")
async def list_clover_items(
    current_user: CurrentUser,
) -> dict:
    """List service catalog items from Clover inventory."""
    clover = get_clover_service()
    if not clover.is_configured():
        raise HTTPException(status_code=503, detail="Clover is not configured")

    data = await clover.list_items()
    if data is None:
        raise HTTPException(status_code=502, detail="Failed to fetch items from Clover")

    elements = data.get("elements", [])
    items = [
        {
            "id": item.get("id"),
            "name": item.get("name"),
            "price": item.get("price", 0),
            "price_dollars": round(item.get("price", 0) / 100, 2),
            "price_type": item.get("priceType", "FIXED"),
            "color_code": item.get("colorCode"),
            "available": item.get("available", True),
            "hidden": item.get("hidden", False),
        }
        for item in elements
        if not item.get("deleted", False)
    ]

    return {"items": items, "total": len(items)}


@router.post("/sync")
async def sync_clover_payments(
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Sync Clover payments to CRM Payment records."""
    clover = get_clover_service()
    if not clover.is_configured():
        raise HTTPException(status_code=503, detail="Clover is not configured")

    try:
        data = await clover.list_payments(limit=100)
        if data is None:
            raise HTTPException(status_code=502, detail="Failed to fetch payments from Clover")

        clover_payments = data.get("elements", [])
        synced = 0
        skipped = 0
        errors = 0
        error_details = []

        for cp in clover_payments:
            clover_id = cp.get("id")
            if not clover_id:
                continue

            # Check if already synced
            existing = await db.execute(
                select(Payment).where(Payment.stripe_payment_intent_id == clover_id)
            )
            if existing.scalar_one_or_none():
                skipped += 1
                continue

            # Only sync successful payments
            if cp.get("result") != "SUCCESS":
                skipped += 1
                continue

            try:
                amount_cents = cp.get("amount", 0) or 0
                tender = cp.get("tender") or {}
                created_ms = cp.get("createdTime") or 0
                created_dt = datetime.utcfromtimestamp(created_ms / 1000) if created_ms else datetime.utcnow()

                amount_val = round(amount_cents / 100, 2)
                method_label = (tender.get("label") or "card").lower()[:50]

                # Use raw SQL to avoid ORM type mismatch (model has invoice_id as UUID
                # but actual DB column is integer)
                await db.execute(
                    text("""
                        INSERT INTO payments (amount, currency, payment_method, status,
                            stripe_payment_intent_id, description, payment_date, processed_at)
                        VALUES (:amount, :currency, :method, :status,
                            :charge_id, :description, :payment_date, :processed_at)
                    """),
                    {
                        "amount": amount_val,
                        "currency": "USD",
                        "method": method_label,
                        "status": "completed",
                        "charge_id": clover_id,
                        "description": "Clover POS payment (synced)",
                        "payment_date": created_dt,
                        "processed_at": created_dt,
                    },
                )
                synced += 1
            except Exception as e:
                logger.error(f"Error syncing Clover payment {clover_id}: {e}")
                error_details.append(f"{clover_id}: {str(e)}")
                errors += 1

        if synced > 0:
            await db.commit()

        return {
            "synced": synced,
            "skipped": skipped,
            "errors": errors,
            "total_clover_payments": len(clover_payments),
            "error_details": error_details[:5] if error_details else [],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sync failed: {e}", exc_info=True)
        await db.rollback()
        return {
            "synced": 0,
            "skipped": 0,
            "errors": 1,
            "total_clover_payments": 0,
            "error_details": [str(e)],
        }


@router.get("/reconciliation")
async def get_reconciliation(
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Compare CRM payments vs Clover payments for reconciliation."""
    clover = get_clover_service()
    if not clover.is_configured():
        raise HTTPException(status_code=503, detail="Clover is not configured")

    # Fetch Clover payments
    clover_data = await clover.list_payments(limit=100)
    clover_payments = clover_data.get("elements", []) if clover_data else []

    # Fetch CRM payments that have Clover IDs
    result = await db.execute(
        select(Payment).where(Payment.stripe_payment_intent_id.isnot(None))
    )
    crm_payments = result.scalars().all()

    # Build lookup maps
    clover_ids = {p.get("id") for p in clover_payments}
    crm_clover_ids = {p.stripe_payment_intent_id for p in crm_payments if p.stripe_payment_intent_id}

    matched = []
    unmatched_clover = []
    unmatched_crm = []

    for cp in clover_payments:
        cid = cp.get("id")
        tender = cp.get("tender", {})
        entry = {
            "clover_id": cid,
            "amount_dollars": round(cp.get("amount", 0) / 100, 2),
            "result": cp.get("result"),
            "tender": tender.get("label", "Unknown"),
            "created_time": cp.get("createdTime"),
        }
        if cid in crm_clover_ids:
            matched.append(entry)
        else:
            unmatched_clover.append(entry)

    for crm_p in crm_payments:
        if crm_p.stripe_payment_intent_id and crm_p.stripe_payment_intent_id not in clover_ids:
            unmatched_crm.append({
                "crm_id": crm_p.id,
                "clover_id": crm_p.stripe_payment_intent_id,
                "amount_dollars": float(crm_p.amount) if crm_p.amount else 0,
                "status": crm_p.status,
                "method": crm_p.payment_method,
            })

    clover_total = sum(cp.get("amount", 0) for cp in clover_payments if cp.get("result") == "SUCCESS")
    crm_total = sum(float(p.amount or 0) for p in crm_payments if p.status == "completed")

    return {
        "matched": matched,
        "unmatched_clover": unmatched_clover,
        "unmatched_crm": unmatched_crm,
        "summary": {
            "total_clover_payments": len(clover_payments),
            "total_crm_payments": len(crm_payments),
            "matched_count": len(matched),
            "unmatched_clover_count": len(unmatched_clover),
            "unmatched_crm_count": len(unmatched_crm),
            "clover_total_dollars": round(clover_total / 100, 2),
            "crm_total_dollars": round(crm_total, 2),
        },
    }


# =============================================================================
# Payment Collection Endpoint (admin/tech — any method)
# =============================================================================


@router.post("/collect")
async def collect_payment(
    request: CollectPaymentRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Collect a payment (any method) and auto-create invoice if needed.

    Works for both admin and technician roles. Records the payment,
    optionally auto-creates an invoice, and updates related records.
    """
    from app.models.customer import Customer
    from app.models.work_order import WorkOrder
    from app.services.websocket_manager import manager

    now = datetime.now(timezone.utc)
    now_naive = now.replace(tzinfo=None)
    payment_id = uuid.uuid4()

    # Resolve work order if provided
    work_order = None
    customer_id = request.customer_id
    if request.work_order_id:
        wo_result = await db.execute(
            select(WorkOrder).where(WorkOrder.id == request.work_order_id)
        )
        work_order = wo_result.scalar_one_or_none()
        if not work_order:
            raise HTTPException(status_code=404, detail="Work order not found")
        if not customer_id:
            customer_id = str(work_order.customer_id) if work_order.customer_id else None

    # Resolve invoice
    invoice = None
    invoice_id_str = None
    if request.invoice_id:
        inv_result = await db.execute(
            select(Invoice).where(Invoice.id == uuid.UUID(request.invoice_id))
        )
        invoice = inv_result.scalar_one_or_none()
        if invoice:
            invoice_id_str = str(invoice.id)
    elif request.auto_create_invoice and work_order:
        # Check for existing invoice on this WO
        inv_result = await db.execute(
            select(Invoice).where(Invoice.work_order_id == request.work_order_id).limit(1)
        )
        invoice = inv_result.scalar_one_or_none()

        if not invoice:
            # Auto-create invoice
            invoice_id_val = uuid.uuid4()
            invoice_number = f"INV-{now.strftime('%Y%m%d')}-{str(invoice_id_val)[:8].upper()}"

            job_type_label = (work_order.job_type or "service").replace("_", " ").title()
            line_items = [{
                "description": f"{job_type_label} - WO #{work_order.work_order_number or str(work_order.id)[:8]}",
                "quantity": 1,
                "unit_price": request.amount,
                "total": request.amount,
            }]

            invoice = Invoice(
                id=invoice_id_val,
                customer_id=uuid.UUID(customer_id) if customer_id else None,
                work_order_id=uuid.UUID(request.work_order_id),
                invoice_number=invoice_number,
                status="paid",
                amount=request.amount,
                paid_amount=request.amount,
                issue_date=now.date(),
                due_date=now.date(),
                paid_date=now.date(),
                line_items=line_items,
                notes=f"Auto-generated from payment collection.",
            )
            db.add(invoice)
            await db.flush()
            invoice_id_str = str(invoice_id_val)
            logger.info(f"Auto-created invoice {invoice_number} for WO {request.work_order_id}")
        else:
            invoice_id_str = str(invoice.id)

    # Update existing invoice if we have one
    if invoice and not request.auto_create_invoice:
        pass  # Don't auto-update if not creating
    elif invoice and invoice_id_str:
        current_paid = float(invoice.paid_amount or 0)
        new_paid = current_paid + request.amount
        if invoice.status != "paid":
            invoice.paid_amount = new_paid
            if invoice.amount and new_paid >= float(invoice.amount):
                invoice.status = "paid"
                invoice.paid_date = now.date()
            else:
                invoice.status = "partial"

    # Build description
    desc_parts = [f"Payment collected by {current_user.email}"]
    if request.payment_method == "check" and request.check_number:
        desc_parts.append(f"Check #{request.check_number}")
    if request.reference_number:
        desc_parts.append(f"Ref: {request.reference_number}")
    if request.notes:
        desc_parts.append(request.notes)
    description = ". ".join(desc_parts)

    # Insert payment via raw SQL (invoice_id type mismatch workaround)
    await db.execute(
        text("""
            INSERT INTO payments (id, customer_id, work_order_id, amount, currency,
                payment_method, status, description, payment_date, processed_at)
            VALUES (:id, :customer_id, :work_order_id, :amount, :currency,
                :payment_method, :status, :description, :payment_date, :processed_at)
        """),
        {
            "id": str(payment_id),
            "customer_id": customer_id,
            "work_order_id": request.work_order_id,
            "amount": request.amount,
            "currency": "USD",
            "payment_method": request.payment_method,
            "status": "completed",
            "description": description,
            "payment_date": now_naive,
            "processed_at": now_naive,
        },
    )

    # Add payment note to work order
    if work_order:
        timestamp_str = now.strftime("%Y-%m-%d %H:%M")
        existing_notes = work_order.notes or ""
        method_label = request.payment_method.replace("_", " ").title()
        work_order.notes = f"{existing_notes}\n[{timestamp_str}] Payment: ${request.amount:.2f} via {method_label}".strip()

    await db.commit()

    # Broadcast payment event
    try:
        await manager.broadcast_event(
            event_type="payment.received",
            data={
                "payment_id": str(payment_id),
                "work_order_id": request.work_order_id,
                "customer_id": customer_id,
                "amount": request.amount,
                "payment_method": request.payment_method,
                "invoice_id": invoice_id_str,
            },
        )
    except Exception:
        pass

    # Fetch customer name for receipt
    customer_name = "Customer"
    if customer_id:
        from app.models.customer import Customer
        cust_result = await db.execute(
            select(Customer).where(Customer.id == customer_id)
        )
        cust = cust_result.scalar_one_or_none()
        if cust:
            customer_name = f"{cust.first_name or ''} {cust.last_name or ''}".strip() or "Customer"

    logger.info(f"Payment collected: ${request.amount} via {request.payment_method} by {current_user.email}")

    return {
        "status": "recorded",
        "payment_id": str(payment_id),
        "work_order_id": request.work_order_id,
        "invoice_id": invoice_id_str,
        "customer_id": customer_id,
        "customer_name": customer_name,
        "amount": request.amount,
        "payment_method": request.payment_method,
        "description": description,
        "payment_date": now.isoformat(),
    }


# =============================================================================
# Card Payment Endpoints (Clover ecommerce)
# =============================================================================


@router.post("/charge")
async def charge_invoice(
    request: CreatePaymentRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> PaymentResultSchema:
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
            return PaymentResultSchema(
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
            return PaymentResultSchema(
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

        return PaymentResultSchema(
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
            select(Payment).where(Payment.id == payment_id)
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
