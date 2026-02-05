"""
Payments API - Track invoice and customer payments.
"""

from fastapi import APIRouter, HTTPException, status as http_status, Query
from sqlalchemy import select, func
from typing import Optional
from datetime import datetime
import logging

from app.api.deps import DbSession, CurrentUser
from app.models.payment import Payment
from app.models.customer import Customer
from app.schemas.payment import (
    PaymentCreate,
    PaymentUpdate,
    PaymentResponse,
    PaymentListResponse,
)
from app.services.websocket_manager import manager

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_model=PaymentListResponse)
async def list_payments(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    customer_id: Optional[str] = None,
    work_order_id: Optional[str] = None,  # Flask uses work_order_id not invoice_id
    payment_status: Optional[str] = None,
    payment_method: Optional[str] = None,
):
    """List payments with pagination and filtering."""
    try:
        # Base query
        query = select(Payment)

        # Apply filters
        if customer_id:
            query = query.where(Payment.customer_id == customer_id)

        if work_order_id:
            query = query.where(Payment.work_order_id == work_order_id)

        if payment_status:
            query = query.where(Payment.status == payment_status)

        if payment_method:
            query = query.where(Payment.payment_method == payment_method)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination - Flask uses created_at not payment_date
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(Payment.created_at.desc())

        # Execute query
        result = await db.execute(query)
        payments = result.scalars().all()

        # Batch-fetch customer names for display
        customer_ids = {p.customer_id for p in payments if p.customer_id}
        customers_map = {}
        if customer_ids:
            cust_result = await db.execute(
                select(Customer).where(Customer.id.in_(customer_ids))
            )
            for c in cust_result.scalars().all():
                name = f"{c.first_name or ''} {c.last_name or ''}".strip()
                customers_map[c.id] = name or None

        # Build response with computed fields
        items = []
        for p in payments:
            items.append(PaymentResponse(
                id=p.id,
                customer_id=p.customer_id,
                customer_name=customers_map.get(p.customer_id),
                work_order_id=p.work_order_id,
                amount=float(p.amount) if p.amount else 0,
                currency=p.currency,
                payment_method=p.payment_method,
                status=p.status,
                description=p.description,
                payment_date=p.payment_date,
                invoice_id=str(p.invoice_id) if p.invoice_id else None,
                stripe_payment_intent_id=p.stripe_payment_intent_id,
                stripe_charge_id=p.stripe_charge_id,
                stripe_customer_id=p.stripe_customer_id,
                receipt_url=p.receipt_url,
                failure_reason=p.failure_reason,
                refund_amount=float(p.refund_amount) if p.refund_amount else None,
                refund_reason=p.refund_reason,
                refunded=p.refunded,
                refund_id=p.refund_id,
                refunded_at=p.refunded_at,
                created_at=p.created_at,
                updated_at=p.updated_at,
                processed_at=p.processed_at,
            ))

        return PaymentListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        logger.error(f"Error listing payments: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {type(e).__name__}: {str(e)}",
        )


@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment(
    payment_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a single payment by ID."""
    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()

    if not payment:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        )

    # Fetch customer name
    customer_name = None
    if payment.customer_id:
        cust_result = await db.execute(
            select(Customer).where(Customer.id == payment.customer_id)
        )
        customer = cust_result.scalar_one_or_none()
        if customer:
            customer_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip() or None

    return PaymentResponse(
        id=payment.id,
        customer_id=payment.customer_id,
        customer_name=customer_name,
        work_order_id=payment.work_order_id,
        amount=float(payment.amount) if payment.amount else 0,
        currency=payment.currency,
        payment_method=payment.payment_method,
        status=payment.status,
        description=payment.description,
        payment_date=payment.payment_date,
        invoice_id=str(payment.invoice_id) if payment.invoice_id else None,
        stripe_payment_intent_id=payment.stripe_payment_intent_id,
        stripe_charge_id=payment.stripe_charge_id,
        stripe_customer_id=payment.stripe_customer_id,
        receipt_url=payment.receipt_url,
        failure_reason=payment.failure_reason,
        refund_amount=float(payment.refund_amount) if payment.refund_amount else None,
        refund_reason=payment.refund_reason,
        refunded=payment.refunded,
        refund_id=payment.refund_id,
        refunded_at=payment.refunded_at,
        created_at=payment.created_at,
        updated_at=payment.updated_at,
        processed_at=payment.processed_at,
    )


@router.post("/", response_model=PaymentResponse, status_code=http_status.HTTP_201_CREATED)
async def create_payment(
    payment_data: PaymentCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new payment."""
    data = payment_data.model_dump()
    # Flask uses created_at with server default, so we don't need to set it

    payment = Payment(**data)
    db.add(payment)
    await db.commit()
    await db.refresh(payment)

    # Broadcast payment received event via WebSocket
    await manager.broadcast_event(
        event_type="payment.received",
        data={
            "id": payment.id,
            "customer_id": payment.customer_id,
            "work_order_id": payment.work_order_id,
            "amount": float(payment.amount) if payment.amount else 0,
            "payment_method": payment.payment_method,
            "status": payment.status,
            "created_at": payment.created_at.isoformat() if payment.created_at else None,
        },
    )

    return payment


@router.patch("/{payment_id}", response_model=PaymentResponse)
async def update_payment(
    payment_id: int,
    payment_data: PaymentUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update a payment."""
    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()

    if not payment:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        )

    # Update only provided fields
    update_data = payment_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(payment, field, value)

    await db.commit()
    await db.refresh(payment)
    return payment


@router.delete("/{payment_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_payment(
    payment_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete a payment."""
    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()

    if not payment:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        )

    await db.delete(payment)
    await db.commit()
