"""
Financing API Endpoints

Customer financing and technician payouts:
- Financing offers and applications
- Technician earnings and instant payouts
"""

from fastapi import APIRouter, Query, HTTPException
from datetime import datetime, date, timedelta
from pydantic import BaseModel, Field
from typing import Optional
from uuid import uuid4

from app.api.deps import DbSession, CurrentUser


router = APIRouter()


# =============================================================================
# Pydantic Schemas
# =============================================================================


class FinancingTerm(BaseModel):
    """Financing term option."""

    term_months: int
    apr: float
    monthly_payment_per_1000: float


class FinancingOffer(BaseModel):
    """Available financing offer."""

    id: str
    provider: str  # wisetack, affirm, greensky, internal
    min_amount: float
    max_amount: float
    terms: list[FinancingTerm]
    promo_apr: Optional[float] = None
    promo_term_months: Optional[int] = None


class FinancingApplication(BaseModel):
    """Customer financing application."""

    id: str
    customer_id: str
    amount: float
    provider: str
    status: str  # pending, approved, declined, funded, cancelled
    application_url: Optional[str] = None
    approved_amount: Optional[float] = None
    term_months: Optional[int] = None
    apr: Optional[float] = None
    monthly_payment: Optional[float] = None
    funded_date: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None


class TechnicianEarnings(BaseModel):
    """Technician earnings summary."""

    technician_id: str
    period_start: str
    period_end: str
    base_pay: float
    overtime_pay: float
    commission: float
    bonuses: float
    deductions: float
    total_gross: float
    available_for_payout: float
    pending_payout: float
    last_payout_date: Optional[str] = None
    job_count: int


class TechnicianPayout(BaseModel):
    """Technician payout record."""

    id: str
    technician_id: str
    amount: float
    fee: float
    net_amount: float
    method: str  # standard, instant
    status: str  # pending, processing, completed, failed
    initiated_at: str
    completed_at: Optional[str] = None
    reference: Optional[str] = None


# =============================================================================
# Mock Data
# =============================================================================

FINANCING_OFFERS = [
    FinancingOffer(
        id="offer-wisetack",
        provider="wisetack",
        min_amount=500,
        max_amount=25000,
        terms=[
            FinancingTerm(term_months=6, apr=0.0, monthly_payment_per_1000=166.67),
            FinancingTerm(term_months=12, apr=9.99, monthly_payment_per_1000=87.92),
            FinancingTerm(term_months=24, apr=14.99, monthly_payment_per_1000=48.49),
            FinancingTerm(term_months=36, apr=17.99, monthly_payment_per_1000=36.15),
        ],
        promo_apr=0.0,
        promo_term_months=6,
    ),
    FinancingOffer(
        id="offer-greensky",
        provider="greensky",
        min_amount=1000,
        max_amount=50000,
        terms=[
            FinancingTerm(term_months=12, apr=7.99, monthly_payment_per_1000=86.99),
            FinancingTerm(term_months=24, apr=12.99, monthly_payment_per_1000=47.54),
            FinancingTerm(term_months=36, apr=14.99, monthly_payment_per_1000=34.67),
            FinancingTerm(term_months=48, apr=17.99, monthly_payment_per_1000=29.29),
        ],
    ),
]


# =============================================================================
# Financing Endpoints
# =============================================================================


@router.get("/offers")
async def get_financing_offers(
    db: DbSession,
    current_user: CurrentUser,
    amount: float = Query(..., gt=0),
) -> dict:
    """Get available financing offers for an amount."""
    offers = [o for o in FINANCING_OFFERS if o.min_amount <= amount <= o.max_amount]
    return {"offers": [o.model_dump() for o in offers]}


@router.get("/applications")
async def get_financing_applications(
    db: DbSession,
    current_user: CurrentUser,
    customer_id: Optional[str] = None,
) -> dict:
    """Get financing applications."""
    applications = [
        FinancingApplication(
            id="app-001",
            customer_id=customer_id or "cust-123",
            amount=5000.00,
            provider="wisetack",
            status="approved",
            approved_amount=5000.00,
            term_months=12,
            apr=9.99,
            monthly_payment=439.58,
            created_at="2024-02-15T00:00:00Z",
        ),
    ]
    return {"applications": [a.model_dump() for a in applications]}


@router.get("/applications/{application_id}")
async def get_financing_application(
    db: DbSession,
    current_user: CurrentUser,
    application_id: str,
) -> dict:
    """Get single financing application."""
    application = FinancingApplication(
        id=application_id,
        customer_id="cust-123",
        amount=5000.00,
        provider="wisetack",
        status="approved",
        approved_amount=5000.00,
        term_months=12,
        apr=9.99,
        monthly_payment=439.58,
        created_at="2024-02-15T00:00:00Z",
    )
    return {"application": application.model_dump()}


@router.post("/prequalify")
async def request_financing(
    db: DbSession,
    current_user: CurrentUser,
    customer_id: str,
    amount: float,
    provider: str,
    invoice_id: Optional[str] = None,
) -> dict:
    """Request financing prequalification."""
    application = FinancingApplication(
        id=f"app-{uuid4().hex[:8]}",
        customer_id=customer_id,
        amount=amount,
        provider=provider,
        status="pending",
        application_url=f"https://apply.{provider}.com/{uuid4().hex}",
        created_at=datetime.utcnow().isoformat(),
    )
    return {"application": application.model_dump()}


@router.post("/applications/{application_id}/cancel")
async def cancel_financing(
    db: DbSession,
    current_user: CurrentUser,
    application_id: str,
) -> dict:
    """Cancel a financing application."""
    return {"success": True, "message": "Application cancelled"}


@router.post("/generate-link")
async def generate_financing_link(
    db: DbSession,
    current_user: CurrentUser,
    customer_id: str,
    amount: float,
    invoice_id: Optional[str] = None,
) -> dict:
    """Generate a financing application link to send to customer."""
    link_id = uuid4().hex[:12]
    return {
        "link": f"https://financing.example.com/apply/{link_id}",
        "expires_at": (datetime.utcnow() + timedelta(days=7)).isoformat(),
    }


# =============================================================================
# Payout Endpoints
# =============================================================================


@router.get("/technicians/{technician_id}/earnings")
async def get_technician_earnings(
    db: DbSession,
    current_user: CurrentUser,
    technician_id: str,
    period_start: Optional[str] = None,
) -> dict:
    """Get technician earnings summary."""
    today = date.today()
    start = date.fromisoformat(period_start) if period_start else today.replace(day=1)

    earnings = TechnicianEarnings(
        technician_id=technician_id,
        period_start=start.isoformat(),
        period_end=today.isoformat(),
        base_pay=2800.00,
        overtime_pay=450.00,
        commission=1250.00,
        bonuses=200.00,
        deductions=150.00,
        total_gross=4550.00,
        available_for_payout=3200.00,
        pending_payout=0.00,
        last_payout_date="2024-02-28",
        job_count=32,
    )
    return {"earnings": earnings.model_dump()}


@router.get("/technicians/{technician_id}")
async def get_technician_payouts(
    db: DbSession,
    current_user: CurrentUser,
    technician_id: str,
) -> dict:
    """Get technician payout history."""
    payouts = [
        TechnicianPayout(
            id="pay-001",
            technician_id=technician_id,
            amount=2500.00,
            fee=0.00,
            net_amount=2500.00,
            method="standard",
            status="completed",
            initiated_at="2024-02-28T00:00:00Z",
            completed_at="2024-03-01T00:00:00Z",
        ),
        TechnicianPayout(
            id="pay-002",
            technician_id=technician_id,
            amount=500.00,
            fee=5.00,
            net_amount=495.00,
            method="instant",
            status="completed",
            initiated_at="2024-02-15T00:00:00Z",
            completed_at="2024-02-15T00:05:00Z",
        ),
    ]
    return {"payouts": [p.model_dump() for p in payouts]}


@router.post("/instant")
async def request_instant_payout(
    db: DbSession,
    current_user: CurrentUser,
    technician_id: str,
    amount: float,
) -> dict:
    """Request instant payout for technician."""
    fee = amount * 0.01  # 1% fee
    payout = TechnicianPayout(
        id=f"pay-{uuid4().hex[:8]}",
        technician_id=technician_id,
        amount=amount,
        fee=round(fee, 2),
        net_amount=round(amount - fee, 2),
        method="instant",
        status="processing",
        initiated_at=datetime.utcnow().isoformat(),
    )
    return {"payout": payout.model_dump()}


@router.get("/instant/fee")
async def get_instant_payout_fee(
    db: DbSession,
    current_user: CurrentUser,
    amount: float = Query(..., gt=0),
) -> dict:
    """Get instant payout fee estimate."""
    fee = round(amount * 0.01, 2)  # 1% fee
    return {"fee": fee, "net_amount": round(amount - fee, 2)}
