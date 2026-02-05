"""
Payment Plans API Endpoints

Customer payment plan management for installment-based payments.

NOTE: Payment plans are not yet backed by a database model.
Endpoints return empty results until a PaymentPlan model and migration are created.
The frontend handles empty states gracefully with "No payment plans found" UI.
"""

import logging
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from app.api.deps import DbSession, CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Pydantic Schemas
# =============================================================================


class PaymentPlan(BaseModel):
    """Customer payment plan."""

    id: int
    customer_name: str
    customer_id: int
    invoice_id: int
    total_amount: float
    amount_paid: float
    remaining: float
    installments: int
    frequency: str  # weekly, biweekly, monthly
    next_payment_date: str
    status: str  # active, completed, overdue, paused, cancelled
    created_at: str
    updated_at: Optional[str] = None


class PaymentPlanListResponse(BaseModel):
    """Paginated payment plans response."""

    items: list[PaymentPlan]
    total: int
    page: int
    page_size: int


class PaymentPlanCreate(BaseModel):
    """Create payment plan request."""

    customer_id: int
    invoice_id: int
    total_amount: float
    installments: int
    frequency: str = "monthly"


class RecordPaymentRequest(BaseModel):
    """Record a payment against a payment plan."""

    amount: float
    payment_method: str = "cash"
    payment_date: str
    notes: Optional[str] = None


# =============================================================================
# Endpoints
# NOTE: /stats/summary MUST come before /{plan_id} to avoid route conflict
# =============================================================================


@router.get("/", response_model=PaymentPlanListResponse)
async def list_payment_plans(
    db: DbSession,
    user: CurrentUser,
    status: Optional[str] = Query(None, description="Filter by status"),
    customer_id: Optional[int] = Query(None, description="Filter by customer"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PaymentPlanListResponse:
    """
    List payment plans with optional filtering.

    Returns empty list until payment plans are implemented with a database model.
    """
    return PaymentPlanListResponse(
        items=[],
        total=0,
        page=page,
        page_size=page_size,
    )


@router.get("/stats/summary")
async def get_payment_plan_stats(
    db: DbSession,
    user: CurrentUser,
) -> dict:
    """
    Get payment plan statistics summary.

    Returns zero stats until payment plans are implemented with a database model.
    """
    return {
        "active_plans": 0,
        "total_outstanding": 0.0,
        "due_this_week": 0.0,
        "overdue_count": 0,
        "overdue_amount": 0.0,
    }


@router.get("/{plan_id}", response_model=PaymentPlan)
async def get_payment_plan(
    plan_id: int,
    db: DbSession,
    user: CurrentUser,
) -> PaymentPlan:
    """
    Get a specific payment plan by ID.
    """
    raise HTTPException(status_code=404, detail="Payment plan not found")


@router.post("/", response_model=PaymentPlan)
async def create_payment_plan(
    data: PaymentPlanCreate,
    db: DbSession,
    user: CurrentUser,
) -> PaymentPlan:
    """
    Create a new payment plan for a customer.

    Not yet implemented - requires PaymentPlan database model and migration.
    """
    raise HTTPException(
        status_code=501,
        detail="Payment plan creation requires database model implementation. Feature coming soon.",
    )


@router.post("/{plan_id}/payments", response_model=PaymentPlan)
async def record_payment(
    plan_id: int,
    data: RecordPaymentRequest,
    db: DbSession,
    user: CurrentUser,
) -> PaymentPlan:
    """
    Record a payment against a payment plan.
    """
    raise HTTPException(status_code=404, detail="Payment plan not found")
