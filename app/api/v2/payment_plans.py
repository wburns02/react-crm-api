"""
Payment Plans API Endpoints

Customer payment plan management for installment-based payments.
"""

from fastapi import APIRouter, Query
from datetime import datetime, date, timedelta
from pydantic import BaseModel
from typing import Optional
from uuid import uuid4

from app.api.deps import DbSession, CurrentUser


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
# Mock Data
# =============================================================================


def _get_mock_payment_plans() -> list[PaymentPlan]:
    """Generate mock payment plans for demo."""
    today = date.today()

    return [
        PaymentPlan(
            id=1,
            customer_name="Johnson Residence",
            customer_id=101,
            invoice_id=5001,
            total_amount=2400.00,
            amount_paid=800.00,
            remaining=1600.00,
            installments=6,
            frequency="monthly",
            next_payment_date=(today + timedelta(days=15)).isoformat(),
            status="active",
            created_at=(today - timedelta(days=60)).isoformat(),
        ),
        PaymentPlan(
            id=2,
            customer_name="Smith Commercial",
            customer_id=102,
            invoice_id=5002,
            total_amount=8500.00,
            amount_paid=4250.00,
            remaining=4250.00,
            installments=4,
            frequency="monthly",
            next_payment_date=(today + timedelta(days=7)).isoformat(),
            status="active",
            created_at=(today - timedelta(days=90)).isoformat(),
        ),
        PaymentPlan(
            id=3,
            customer_name="Martinez Property",
            customer_id=103,
            invoice_id=5003,
            total_amount=1200.00,
            amount_paid=1200.00,
            remaining=0.00,
            installments=3,
            frequency="monthly",
            next_payment_date="",
            status="completed",
            created_at=(today - timedelta(days=120)).isoformat(),
        ),
        PaymentPlan(
            id=4,
            customer_name="Thompson Estate",
            customer_id=104,
            invoice_id=5004,
            total_amount=3600.00,
            amount_paid=600.00,
            remaining=3000.00,
            installments=12,
            frequency="monthly",
            next_payment_date=(today - timedelta(days=5)).isoformat(),
            status="overdue",
            created_at=(today - timedelta(days=45)).isoformat(),
        ),
        PaymentPlan(
            id=5,
            customer_name="Garcia Plumbing Co",
            customer_id=105,
            invoice_id=5005,
            total_amount=5000.00,
            amount_paid=2500.00,
            remaining=2500.00,
            installments=4,
            frequency="biweekly",
            next_payment_date=(today + timedelta(days=3)).isoformat(),
            status="active",
            created_at=(today - timedelta(days=30)).isoformat(),
        ),
    ]


# =============================================================================
# Endpoints
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

    Returns paginated list of customer payment plans.
    """
    # Get mock data
    plans = _get_mock_payment_plans()

    # Apply filters
    if status:
        plans = [p for p in plans if p.status == status]
    if customer_id:
        plans = [p for p in plans if p.customer_id == customer_id]

    # Calculate pagination
    total = len(plans)
    start = (page - 1) * page_size
    end = start + page_size
    items = plans[start:end]

    return PaymentPlanListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{plan_id}", response_model=PaymentPlan)
async def get_payment_plan(
    plan_id: int,
    db: DbSession,
    user: CurrentUser,
) -> PaymentPlan:
    """
    Get a specific payment plan by ID.
    """
    plans = _get_mock_payment_plans()
    for plan in plans:
        if plan.id == plan_id:
            return plan

    from fastapi import HTTPException

    raise HTTPException(status_code=404, detail="Payment plan not found")


@router.post("/", response_model=PaymentPlan)
async def create_payment_plan(
    data: PaymentPlanCreate,
    db: DbSession,
    user: CurrentUser,
) -> PaymentPlan:
    """
    Create a new payment plan for a customer.
    """
    today = date.today()

    # Calculate next payment date based on frequency
    if data.frequency == "weekly":
        next_date = today + timedelta(days=7)
    elif data.frequency == "biweekly":
        next_date = today + timedelta(days=14)
    else:  # monthly
        next_date = today + timedelta(days=30)

    return PaymentPlan(
        id=int(uuid4().int % 10000),
        customer_name="New Customer",  # Would be fetched from DB
        customer_id=data.customer_id,
        invoice_id=data.invoice_id,
        total_amount=data.total_amount,
        amount_paid=0.0,
        remaining=data.total_amount,
        installments=data.installments,
        frequency=data.frequency,
        next_payment_date=next_date.isoformat(),
        status="active",
        created_at=today.isoformat(),
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

    Updates amount_paid and remaining balance.
    Auto-completes the plan if fully paid.
    """
    from fastapi import HTTPException

    plans = _get_mock_payment_plans()

    for plan in plans:
        if plan.id == plan_id:
            # Calculate new amounts
            new_amount_paid = plan.amount_paid + data.amount
            new_remaining = plan.total_amount - new_amount_paid

            # Determine new status
            new_status = plan.status
            if new_remaining <= 0:
                new_status = "completed"
                new_remaining = 0
            elif plan.status == "overdue":
                # If was overdue and payment made, could revert to active
                new_status = "active"

            # Return updated plan
            return PaymentPlan(
                id=plan.id,
                customer_name=plan.customer_name,
                customer_id=plan.customer_id,
                invoice_id=plan.invoice_id,
                total_amount=plan.total_amount,
                amount_paid=new_amount_paid,
                remaining=new_remaining,
                installments=plan.installments,
                frequency=plan.frequency,
                next_payment_date=plan.next_payment_date if new_status != "completed" else "",
                status=new_status,
                created_at=plan.created_at,
                updated_at=datetime.now().isoformat(),
            )

    raise HTTPException(status_code=404, detail="Payment plan not found")


@router.get("/stats/summary")
async def get_payment_plan_stats(
    db: DbSession,
    user: CurrentUser,
) -> dict:
    """
    Get payment plan statistics summary.
    """
    plans = _get_mock_payment_plans()

    active_plans = [p for p in plans if p.status == "active"]
    overdue_plans = [p for p in plans if p.status == "overdue"]

    total_outstanding = sum(p.remaining for p in plans if p.status in ["active", "overdue"])

    # Calculate due this week
    today = date.today()
    week_end = today + timedelta(days=7)
    due_this_week = sum(
        p.remaining / p.installments
        for p in active_plans
        if p.next_payment_date and date.fromisoformat(p.next_payment_date) <= week_end
    )

    return {
        "active_plans": len(active_plans),
        "total_outstanding": total_outstanding,
        "due_this_week": due_this_week,
        "overdue_count": len(overdue_plans),
        "overdue_amount": sum(p.remaining for p in overdue_plans),
    }
