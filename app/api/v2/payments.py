"""
Payments API - Track invoice and customer payments.
"""
from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, func
from typing import Optional
from datetime import datetime
import logging

from app.api.deps import DbSession, CurrentUser
from app.models.payment import Payment
from app.schemas.payment import (
    PaymentCreate,
    PaymentUpdate,
    PaymentResponse,
    PaymentListResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_model=PaymentListResponse)
async def list_payments(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    customer_id: Optional[int] = None,
    invoice_id: Optional[int] = None,
    status: Optional[str] = None,
    payment_method: Optional[str] = None,
):
    """List payments with pagination and filtering."""
    try:
        # Base query
        query = select(Payment)

        # Apply filters
        if customer_id:
            query = query.where(Payment.customer_id == customer_id)

        if invoice_id:
            query = query.where(Payment.invoice_id == invoice_id)

        if status:
            query = query.where(Payment.status == status)

        if payment_method:
            query = query.where(Payment.payment_method == payment_method)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(Payment.payment_date.desc())

        # Execute query
        result = await db.execute(query)
        payments = result.scalars().all()

        return PaymentListResponse(
            items=payments,
            total=total,
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        logger.error(f"Error listing payments: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {type(e).__name__}: {str(e)}"
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
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        )

    return payment


@router.post("/", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
async def create_payment(
    payment_data: PaymentCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new payment."""
    data = payment_data.model_dump()
    if not data.get('payment_date'):
        data['payment_date'] = datetime.utcnow()

    payment = Payment(**data)
    db.add(payment)
    await db.commit()
    await db.refresh(payment)
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
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        )

    # Update only provided fields
    update_data = payment_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(payment, field, value)

    await db.commit()
    await db.refresh(payment)
    return payment


@router.delete("/{payment_id}", status_code=status.HTTP_204_NO_CONTENT)
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
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        )

    await db.delete(payment)
    await db.commit()
