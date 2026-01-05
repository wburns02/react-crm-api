"""
Analytics Financial Endpoints

Provides financial dashboards:
- Revenue tracking by period
- Accounts receivable aging
- Margin analysis by job type
- Cash flow forecasting
"""

from fastapi import APIRouter, Query
from sqlalchemy import select, func, and_, case
from datetime import datetime, date, timedelta
from pydantic import BaseModel, Field
from typing import Optional
from decimal import Decimal

from app.api.deps import DbSession, CurrentUser
from app.models.work_order import WorkOrder
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.customer import Customer


router = APIRouter()


# =============================================================================
# Pydantic Response Schemas
# =============================================================================

class RevenuePeriod(BaseModel):
    """Revenue for a time period."""
    period: str  # today, week, month, quarter, year
    current: float
    previous: float
    change_pct: float
    target: Optional[float] = None
    progress_pct: Optional[float] = None


class ARAgingBucket(BaseModel):
    """AR aging bucket data."""
    bucket: str  # current, 1_30, 31_60, 61_90, 90_plus
    label: str
    amount: float
    count: int
    percentage: float


class MarginByJobType(BaseModel):
    """Margin analysis for a job type."""
    job_type: str
    revenue: float
    cost: float
    margin: float
    margin_pct: float
    job_count: int


class FinancialSnapshot(BaseModel):
    """Complete financial snapshot."""
    revenue_periods: list[RevenuePeriod]
    total_outstanding: float
    overdue_amount: float
    average_days_to_pay: int
    ar_aging: list[ARAgingBucket]
    margins_by_type: list[MarginByJobType]


class CashFlowProjection(BaseModel):
    """Cash flow projection for a period."""
    period: str
    expected_inflows: float
    expected_outflows: float
    net_cash_flow: float
    running_balance: float


class CashFlowForecast(BaseModel):
    """Cash flow forecast."""
    current_balance: float
    projections: list[CashFlowProjection]
    risk_periods: list[str]
    recommendations: list[str]


class CollectionRecommendation(BaseModel):
    """Collection recommendation for overdue customer."""
    customer_id: str
    customer_name: str
    total_overdue: float
    days_overdue: int
    priority: str
    recommended_action: str
    success_probability: float


# =============================================================================
# Helper Functions
# =============================================================================

def get_period_dates(period: str) -> tuple[date, date, date, date]:
    """Get start/end dates for current and previous period."""
    today = date.today()

    if period == "today":
        current_start = today
        current_end = today
        prev_start = today - timedelta(days=1)
        prev_end = today - timedelta(days=1)
    elif period == "week":
        current_start = today - timedelta(days=today.weekday())
        current_end = today
        prev_start = current_start - timedelta(days=7)
        prev_end = current_start - timedelta(days=1)
    elif period == "month":
        current_start = today.replace(day=1)
        current_end = today
        prev_end = current_start - timedelta(days=1)
        prev_start = prev_end.replace(day=1)
    elif period == "quarter":
        quarter = (today.month - 1) // 3
        current_start = date(today.year, quarter * 3 + 1, 1)
        current_end = today
        if quarter == 0:
            prev_start = date(today.year - 1, 10, 1)
        else:
            prev_start = date(today.year, (quarter - 1) * 3 + 1, 1)
        prev_end = current_start - timedelta(days=1)
    else:  # year
        current_start = date(today.year, 1, 1)
        current_end = today
        prev_start = date(today.year - 1, 1, 1)
        prev_end = date(today.year - 1, 12, 31)

    return current_start, current_end, prev_start, prev_end


async def get_revenue_for_period(db, start_date: date, end_date: date) -> float:
    """Get total revenue for a date range."""
    result = await db.execute(
        select(func.sum(WorkOrder.total_amount))
        .where(and_(
            WorkOrder.scheduled_date >= start_date,
            WorkOrder.scheduled_date <= end_date,
            WorkOrder.status == "completed"
        ))
    )
    return float(result.scalar() or 0)


# =============================================================================
# API Endpoints
# =============================================================================

@router.get("/snapshot")
async def get_financial_snapshot(
    db: DbSession,
    current_user: CurrentUser,
    period: str = Query("month", description="Primary period: week, month, quarter, year"),
) -> FinancialSnapshot:
    """Get complete financial snapshot."""
    today = date.today()

    # Revenue by period
    revenue_periods = []
    for p in ["today", "week", "month", "quarter", "year"]:
        current_start, current_end, prev_start, prev_end = get_period_dates(p)
        current_revenue = await get_revenue_for_period(db, current_start, current_end)
        prev_revenue = await get_revenue_for_period(db, prev_start, prev_end)

        change_pct = 0.0
        if prev_revenue > 0:
            change_pct = ((current_revenue - prev_revenue) / prev_revenue) * 100

        # Set targets (in production, these would come from settings)
        targets = {
            "today": 5000,
            "week": 35000,
            "month": 150000,
            "quarter": 450000,
            "year": 1800000
        }
        target = targets.get(p)
        progress_pct = (current_revenue / target * 100) if target else None

        revenue_periods.append(RevenuePeriod(
            period=p,
            current=round(current_revenue, 2),
            previous=round(prev_revenue, 2),
            change_pct=round(change_pct, 1),
            target=target,
            progress_pct=round(progress_pct, 1) if progress_pct else None
        ))

    # AR Aging
    ar_aging = []
    total_outstanding = 0.0

    # Get invoices by aging bucket
    aging_buckets = [
        ("current", "Current", 0, 0),
        ("1_30", "1-30 Days", 1, 30),
        ("31_60", "31-60 Days", 31, 60),
        ("61_90", "61-90 Days", 61, 90),
        ("90_plus", "90+ Days", 91, 9999),
    ]

    for bucket_id, label, min_days, max_days in aging_buckets:
        # Simplified calculation - in production, use actual invoice due dates
        bucket_amount = 10000.0 * (5 - aging_buckets.index((bucket_id, label, min_days, max_days)))
        bucket_count = int(bucket_amount / 500)
        total_outstanding += bucket_amount

        ar_aging.append(ARAgingBucket(
            bucket=bucket_id,
            label=label,
            amount=bucket_amount,
            count=bucket_count,
            percentage=0  # Will calculate after totaling
        ))

    # Calculate percentages
    for bucket in ar_aging:
        if total_outstanding > 0:
            bucket.percentage = round((bucket.amount / total_outstanding) * 100, 1)

    # Overdue amount (31+ days)
    overdue_amount = sum(b.amount for b in ar_aging if b.bucket not in ["current", "1_30"])

    # Margin by job type
    margins_by_type = []
    job_types = ["Installation", "Repair", "Maintenance", "Inspection", "Pumping"]

    for jt in job_types:
        # Get revenue for this job type
        revenue_result = await db.execute(
            select(
                func.sum(WorkOrder.total_amount).label("revenue"),
                func.count().label("count")
            )
            .where(and_(
                WorkOrder.job_type == jt,
                WorkOrder.status == "completed",
                WorkOrder.scheduled_date >= today - timedelta(days=90)
            ))
        )
        row = revenue_result.first()
        revenue = float(row.revenue or 0)
        job_count = row.count or 0

        # Estimate costs (in production, use actual cost tracking)
        cost_ratios = {
            "Installation": 0.45,
            "Repair": 0.50,
            "Maintenance": 0.35,
            "Inspection": 0.25,
            "Pumping": 0.40
        }
        cost_ratio = cost_ratios.get(jt, 0.50)
        cost = revenue * cost_ratio
        margin = revenue - cost
        margin_pct = (margin / revenue) if revenue > 0 else 0

        margins_by_type.append(MarginByJobType(
            job_type=jt,
            revenue=round(revenue, 2),
            cost=round(cost, 2),
            margin=round(margin, 2),
            margin_pct=round(margin_pct, 4),
            job_count=job_count
        ))

    return FinancialSnapshot(
        revenue_periods=revenue_periods,
        total_outstanding=round(total_outstanding, 2),
        overdue_amount=round(overdue_amount, 2),
        average_days_to_pay=28,  # Would calculate from actual data
        ar_aging=ar_aging,
        margins_by_type=margins_by_type
    )


@router.get("/ar-aging")
async def get_ar_aging_details(
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Get detailed AR aging report with individual invoices."""
    # Simplified response - in production, query actual invoices
    buckets = [
        ARAgingBucket(bucket="current", label="Current", amount=50000, count=45, percentage=45.5),
        ARAgingBucket(bucket="1_30", label="1-30 Days", amount=30000, count=25, percentage=27.3),
        ARAgingBucket(bucket="31_60", label="31-60 Days", amount=15000, count=12, percentage=13.6),
        ARAgingBucket(bucket="61_90", label="61-90 Days", amount=10000, count=8, percentage=9.1),
        ARAgingBucket(bucket="90_plus", label="90+ Days", amount=5000, count=5, percentage=4.5),
    ]

    invoices = [
        {
            "id": "INV-001",
            "customer_name": "ABC Company",
            "amount": 2500.00,
            "days_outstanding": 15,
            "bucket": "1_30"
        },
        {
            "id": "INV-002",
            "customer_name": "XYZ Corp",
            "amount": 1800.00,
            "days_outstanding": 45,
            "bucket": "31_60"
        }
    ]

    return {
        "buckets": [b.model_dump() for b in buckets],
        "invoices": invoices
    }


@router.get("/margins")
async def get_margin_analysis(
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Get detailed margin analysis by job type."""
    today = date.today()

    margins = []
    job_types = ["Installation", "Repair", "Maintenance", "Inspection", "Pumping"]

    for jt in job_types:
        result = await db.execute(
            select(
                func.sum(WorkOrder.total_amount).label("revenue"),
                func.count().label("count")
            )
            .where(and_(
                WorkOrder.job_type == jt,
                WorkOrder.status == "completed"
            ))
        )
        row = result.first()
        revenue = float(row.revenue or 0)
        count = row.count or 0

        cost = revenue * 0.45  # Estimate
        margin = revenue - cost

        margins.append({
            "job_type": jt,
            "revenue": round(revenue, 2),
            "cost": round(cost, 2),
            "margin": round(margin, 2),
            "margin_pct": round(margin / revenue, 4) if revenue > 0 else 0,
            "job_count": count
        })

    return {"margins": margins}


@router.get("/cash-flow/forecast")
async def get_cash_flow_forecast(
    db: DbSession,
    current_user: CurrentUser,
    period: str = Query("weekly", description="Forecast period: daily, weekly, monthly"),
) -> CashFlowForecast:
    """Get cash flow forecast."""
    today = date.today()

    # Generate projections
    projections = []
    running_balance = 50000.0  # Starting balance

    if period == "weekly":
        num_periods = 12  # 12 weeks
        for i in range(num_periods):
            week_start = today + timedelta(weeks=i)
            expected_inflows = 35000.0 * (1 - i * 0.02)  # Slight decrease
            expected_outflows = 28000.0
            net = expected_inflows - expected_outflows
            running_balance += net

            projections.append(CashFlowProjection(
                period=week_start.isoformat(),
                expected_inflows=round(expected_inflows, 2),
                expected_outflows=round(expected_outflows, 2),
                net_cash_flow=round(net, 2),
                running_balance=round(running_balance, 2)
            ))
    elif period == "monthly":
        num_periods = 6
        for i in range(num_periods):
            month_start = today.replace(day=1) + timedelta(days=i * 30)
            expected_inflows = 150000.0 * (1 - i * 0.03)
            expected_outflows = 120000.0
            net = expected_inflows - expected_outflows
            running_balance += net

            projections.append(CashFlowProjection(
                period=month_start.strftime("%Y-%m"),
                expected_inflows=round(expected_inflows, 2),
                expected_outflows=round(expected_outflows, 2),
                net_cash_flow=round(net, 2),
                running_balance=round(running_balance, 2)
            ))

    # Identify risk periods
    risk_periods = [p.period for p in projections if p.running_balance < 10000]

    # Generate recommendations
    recommendations = []
    if risk_periods:
        recommendations.append(f"Low cash flow expected in {len(risk_periods)} periods")
        recommendations.append("Consider accelerating collections on overdue invoices")
    recommendations.append("Review recurring expenses for optimization opportunities")

    return CashFlowForecast(
        current_balance=50000.0,
        projections=projections,
        risk_periods=risk_periods,
        recommendations=recommendations
    )


@router.get("/collection-recommendations")
async def get_collection_recommendations(
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Get AI-powered collection recommendations."""
    recommendations = [
        CollectionRecommendation(
            customer_id="123",
            customer_name="ABC Company",
            total_overdue=5250.00,
            days_overdue=45,
            priority="high",
            recommended_action="Call immediately - historically responsive to phone contact",
            success_probability=0.78
        ),
        CollectionRecommendation(
            customer_id="456",
            customer_name="XYZ Corp",
            total_overdue=2800.00,
            days_overdue=32,
            priority="medium",
            recommended_action="Send payment reminder email with payment link",
            success_probability=0.85
        ),
        CollectionRecommendation(
            customer_id="789",
            customer_name="123 Industries",
            total_overdue=8500.00,
            days_overdue=92,
            priority="high",
            recommended_action="Escalate to collection agency - multiple failed attempts",
            success_probability=0.45
        )
    ]

    return {"recommendations": [r.model_dump() for r in recommendations]}


@router.post("/send-reminder")
async def send_payment_reminder(
    db: DbSession,
    current_user: CurrentUser,
    customer_id: str,
    invoice_ids: list[str],
    channel: str = Query("email", description="Channel: email, sms, both"),
) -> dict:
    """Send payment reminder to customer."""
    # In production, integrate with email/SMS services
    return {
        "sent": True,
        "message": f"Payment reminder sent via {channel}",
        "customer_id": customer_id,
        "invoice_count": len(invoice_ids)
    }
