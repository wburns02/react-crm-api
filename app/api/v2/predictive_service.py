"""Predictive Service Engine — "Know Before They Call"

Scores every customer's septic system risk and surfaces proactive service needs.
No new tables — computes from customers, work_orders, service intervals.
"""

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select, func, and_, or_, desc, case
from sqlalchemy.orm import selectinload
from datetime import date, timedelta, datetime
from typing import Optional
import logging
import math

from app.api.deps import DbSession, CurrentUser
from app.models.customer import Customer
from app.models.work_order import WorkOrder
from app.models.service_interval import CustomerServiceSchedule, ServiceInterval

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Scoring Constants ────────────────────────────────────

# Base pumping intervals by system type (months)
BASE_INTERVALS = {
    "conventional": 36,  # 3 years
    "aerobic": 6,        # 6 months (requires regular maintenance)
}

# Manufacturer-specific overrides (months)
MANUFACTURER_INTERVALS = {
    "norweco": 6,
    "fuji": 6,
    "jet": 6,
    "clearstream": 6,
}

# Tank size adjustment (gallons → interval multiplier)
def _tank_interval_multiplier(gallons: int | None) -> float:
    if not gallons or gallons <= 0:
        return 1.0
    if gallons <= 500:
        return 0.8   # small tank, pump more often
    if gallons <= 1000:
        return 1.0
    if gallons <= 1500:
        return 1.1
    return 1.2  # large tank, slightly longer


# ─── Scoring Engine ───────────────────────────────────────

def _score_customer(
    customer: Customer,
    last_pump_date: date | None,
    last_service_date: date | None,
    emergency_count: int,
    total_services: int,
    overdue_schedules: int,
) -> dict:
    """Score a customer's system risk (0-100, higher = more urgent)."""
    today = date.today()
    score = 0
    factors = []

    # 1. System type baseline interval
    sys_type = (customer.system_type or "conventional").lower()
    base_months = BASE_INTERVALS.get(sys_type, 36)

    # 2. Manufacturer override
    mfr = (customer.manufacturer or "").lower()
    if mfr in MANUFACTURER_INTERVALS:
        base_months = MANUFACTURER_INTERVALS[mfr]

    # 3. Tank size adjustment
    multiplier = _tank_interval_multiplier(customer.tank_size_gallons)
    expected_interval_days = int(base_months * 30.44 * multiplier)

    # 4. Days since last pumping
    if last_pump_date:
        days_since_pump = (today - last_pump_date).days
        pump_ratio = days_since_pump / expected_interval_days if expected_interval_days > 0 else 2.0

        if pump_ratio >= 1.5:
            score += 40
            factors.append(f"Severely overdue: {days_since_pump} days since last pumping (expected every {expected_interval_days} days)")
        elif pump_ratio >= 1.0:
            score += 30
            factors.append(f"Overdue: {days_since_pump} days since last pumping")
        elif pump_ratio >= 0.8:
            score += 15
            factors.append(f"Due soon: {days_since_pump} days since last pumping")
        else:
            factors.append(f"Recently serviced: {days_since_pump} days ago")
    else:
        # No pumping history — high risk if we have system info
        if customer.system_type or customer.tank_size_gallons:
            score += 25
            factors.append("No pumping history on record")

    # 5. System age
    if customer.system_issued_date:
        system_age_years = (today - customer.system_issued_date).days / 365.25
        if system_age_years >= 25:
            score += 15
            factors.append(f"Aging system: {system_age_years:.0f} years old")
        elif system_age_years >= 15:
            score += 8
            factors.append(f"Mature system: {system_age_years:.0f} years old")

    # 6. Emergency history (indicator of neglect)
    if emergency_count >= 3:
        score += 15
        factors.append(f"High emergency frequency: {emergency_count} emergency calls")
    elif emergency_count >= 1:
        score += 8
        factors.append(f"Previous emergency call ({emergency_count})")

    # 7. Overdue service schedules
    if overdue_schedules > 0:
        score += 10 * min(overdue_schedules, 3)
        factors.append(f"{overdue_schedules} overdue service schedule(s)")

    # 8. Aerobic systems need more attention
    if sys_type == "aerobic":
        score += 5
        factors.append("Aerobic system (requires regular maintenance)")

    # 9. No recent contact at all
    if last_service_date:
        days_since_any = (today - last_service_date).days
        if days_since_any > 365 * 2:
            score += 10
            factors.append(f"No service contact in {days_since_any // 365} years")

    # Clamp to 0-100
    score = max(0, min(100, score))

    # Risk level
    if score >= 70:
        risk_level = "critical"
    elif score >= 50:
        risk_level = "high"
    elif score >= 30:
        risk_level = "medium"
    else:
        risk_level = "low"

    # Predicted service needed
    if last_pump_date:
        predicted_due = last_pump_date + timedelta(days=expected_interval_days)
        days_until_due = (predicted_due - today).days
    else:
        predicted_due = None
        days_until_due = None

    # Recommended action
    if score >= 70:
        action = "Immediate outreach — system likely needs service now"
    elif score >= 50:
        action = "Schedule proactive contact within 2 weeks"
    elif score >= 30:
        action = "Add to upcoming campaign — service due within 60 days"
    else:
        action = "No action needed — recently serviced"

    return {
        "customer_id": str(customer.id),
        "customer_name": f"{customer.first_name or ''} {customer.last_name or ''}".strip(),
        "phone": customer.phone,
        "email": customer.email,
        "address": f"{customer.address_line1 or ''}, {customer.city or ''} {customer.state or ''}".strip(", "),
        "system_type": customer.system_type or "unknown",
        "manufacturer": customer.manufacturer or "unknown",
        "tank_size_gallons": customer.tank_size_gallons,
        "risk_score": score,
        "risk_level": risk_level,
        "factors": factors,
        "last_pump_date": str(last_pump_date) if last_pump_date else None,
        "last_service_date": str(last_service_date) if last_service_date else None,
        "predicted_due_date": str(predicted_due) if predicted_due else None,
        "days_until_due": days_until_due,
        "expected_interval_days": expected_interval_days,
        "emergency_count": emergency_count,
        "total_services": total_services,
        "recommended_action": action,
    }


# ─── Endpoints ────────────────────────────────────────────


@router.get("/scores")
async def get_predictive_scores(
    db: DbSession,
    user: CurrentUser,
    risk_level: Optional[str] = Query(None, description="Filter: critical, high, medium, low"),
    min_score: int = Query(0, ge=0, le=100),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    sort_by: str = Query("risk_score", description="risk_score or days_until_due"),
):
    """Score all active customers and return risk-ranked list."""
    # Get active customers
    customers_q = await db.execute(
        select(Customer).where(
            and_(
                Customer.is_active == True,
                or_(Customer.is_archived == False, Customer.is_archived == None),
            )
        )
    )
    customers = customers_q.scalars().all()

    # Batch-fetch last pumping dates
    pump_dates = await db.execute(
        select(
            WorkOrder.customer_id,
            func.max(WorkOrder.scheduled_date).label("last_pump"),
        )
        .where(
            and_(
                WorkOrder.status == "completed",
                WorkOrder.job_type.in_(["pumping", "grease_trap"]),
            )
        )
        .group_by(WorkOrder.customer_id)
    )
    pump_map = {str(r.customer_id): r.last_pump for r in pump_dates.all()}

    # Batch-fetch last any-service dates
    svc_dates = await db.execute(
        select(
            WorkOrder.customer_id,
            func.max(WorkOrder.scheduled_date).label("last_svc"),
        )
        .where(WorkOrder.status == "completed")
        .group_by(WorkOrder.customer_id)
    )
    svc_map = {str(r.customer_id): r.last_svc for r in svc_dates.all()}

    # Batch-fetch emergency counts
    emg_counts = await db.execute(
        select(
            WorkOrder.customer_id,
            func.count().label("emg_count"),
        )
        .where(
            and_(
                WorkOrder.status == "completed",
                or_(
                    WorkOrder.job_type == "emergency",
                    WorkOrder.priority == "emergency",
                ),
            )
        )
        .group_by(WorkOrder.customer_id)
    )
    emg_map = {str(r.customer_id): r.emg_count for r in emg_counts.all()}

    # Batch-fetch total service counts
    total_counts = await db.execute(
        select(
            WorkOrder.customer_id,
            func.count().label("total"),
        )
        .where(WorkOrder.status == "completed")
        .group_by(WorkOrder.customer_id)
    )
    total_map = {str(r.customer_id): r.total for r in total_counts.all()}

    # Batch-fetch overdue schedules
    overdue_q = await db.execute(
        select(
            CustomerServiceSchedule.customer_id,
            func.count().label("overdue"),
        )
        .where(CustomerServiceSchedule.status == "overdue")
        .group_by(CustomerServiceSchedule.customer_id)
    )
    overdue_map = {str(r.customer_id): r.overdue for r in overdue_q.all()}

    # Score all customers
    scores = []
    for cust in customers:
        cid = str(cust.id)
        result = _score_customer(
            customer=cust,
            last_pump_date=pump_map.get(cid),
            last_service_date=svc_map.get(cid),
            emergency_count=emg_map.get(cid, 0),
            total_services=total_map.get(cid, 0),
            overdue_schedules=overdue_map.get(cid, 0),
        )
        if result["risk_score"] >= min_score:
            if risk_level and result["risk_level"] != risk_level:
                continue
            scores.append(result)

    # Sort
    reverse = True
    if sort_by == "days_until_due":
        scores.sort(key=lambda x: x["days_until_due"] if x["days_until_due"] is not None else 9999)
        reverse = False
    else:
        scores.sort(key=lambda x: x["risk_score"], reverse=True)

    # Summary stats
    total_scored = len(scores)
    critical_count = sum(1 for s in scores if s["risk_level"] == "critical")
    high_count = sum(1 for s in scores if s["risk_level"] == "high")
    medium_count = sum(1 for s in scores if s["risk_level"] == "medium")

    # Estimate revenue opportunity (avg pumping job ~$350)
    actionable = [s for s in scores if s["risk_score"] >= 30]
    revenue_opportunity = len(actionable) * 350

    paginated = scores[offset:offset + limit]

    return {
        "scores": paginated,
        "summary": {
            "total_scored": total_scored,
            "critical": critical_count,
            "high": high_count,
            "medium": medium_count,
            "low": total_scored - critical_count - high_count - medium_count,
            "revenue_opportunity": revenue_opportunity,
            "actionable_customers": len(actionable),
        },
        "pagination": {
            "total": total_scored,
            "limit": limit,
            "offset": offset,
        },
    }


@router.get("/scores/{customer_id}")
async def get_customer_score(db: DbSession, user: CurrentUser, customer_id: str):
    """Get detailed predictive score for a single customer."""
    cust = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = cust.scalar_one_or_none()
    if not customer:
        raise HTTPException(404, "Customer not found")

    # Last pump
    pump = await db.execute(
        select(func.max(WorkOrder.scheduled_date)).where(
            and_(
                WorkOrder.customer_id == customer_id,
                WorkOrder.status == "completed",
                WorkOrder.job_type.in_(["pumping", "grease_trap"]),
            )
        )
    )
    last_pump = pump.scalar()

    # Last any service
    svc = await db.execute(
        select(func.max(WorkOrder.scheduled_date)).where(
            and_(WorkOrder.customer_id == customer_id, WorkOrder.status == "completed")
        )
    )
    last_svc = svc.scalar()

    # Emergency count
    emg = await db.execute(
        select(func.count()).where(
            and_(
                WorkOrder.customer_id == customer_id,
                WorkOrder.status == "completed",
                or_(WorkOrder.job_type == "emergency", WorkOrder.priority == "emergency"),
            )
        )
    )
    emg_count = emg.scalar() or 0

    # Total services
    total = await db.execute(
        select(func.count()).where(
            and_(WorkOrder.customer_id == customer_id, WorkOrder.status == "completed")
        )
    )
    total_count = total.scalar() or 0

    # Overdue
    overdue = await db.execute(
        select(func.count()).where(
            and_(
                CustomerServiceSchedule.customer_id == customer_id,
                CustomerServiceSchedule.status == "overdue",
            )
        )
    )
    overdue_count = overdue.scalar() or 0

    # Service history (last 10)
    history = await db.execute(
        select(
            WorkOrder.id, WorkOrder.job_type, WorkOrder.scheduled_date,
            WorkOrder.status, WorkOrder.system_type, WorkOrder.total_amount,
        )
        .where(
            and_(WorkOrder.customer_id == customer_id, WorkOrder.status == "completed")
        )
        .order_by(desc(WorkOrder.scheduled_date))
        .limit(10)
    )

    score = _score_customer(customer, last_pump, last_svc, emg_count, total_count, overdue_count)
    score["service_history"] = [
        {
            "id": str(r.id),
            "job_type": r.job_type,
            "date": str(r.scheduled_date) if r.scheduled_date else None,
            "system_type": r.system_type,
            "amount": float(r.total_amount) if r.total_amount else None,
        }
        for r in history.all()
    ]

    return score


@router.get("/campaign-preview")
async def preview_campaign(
    db: DbSession,
    user: CurrentUser,
    min_score: int = Query(30, ge=0, le=100),
    days_horizon: int = Query(60, ge=7, le=365),
):
    """Preview an auto-generated outreach campaign for at-risk customers."""
    # Get scored customers above threshold
    # Reuse the scoring endpoint logic but lighter
    customers_q = await db.execute(
        select(Customer).where(
            and_(
                Customer.is_active == True,
                or_(Customer.is_archived == False, Customer.is_archived == None),
                Customer.phone != None,
                Customer.phone != "",
            )
        )
    )
    customers = customers_q.scalars().all()

    pump_dates = await db.execute(
        select(WorkOrder.customer_id, func.max(WorkOrder.scheduled_date).label("last_pump"))
        .where(and_(WorkOrder.status == "completed", WorkOrder.job_type.in_(["pumping", "grease_trap"])))
        .group_by(WorkOrder.customer_id)
    )
    pump_map = {str(r.customer_id): r.last_pump for r in pump_dates.all()}

    svc_dates = await db.execute(
        select(WorkOrder.customer_id, func.max(WorkOrder.scheduled_date).label("last_svc"))
        .where(WorkOrder.status == "completed")
        .group_by(WorkOrder.customer_id)
    )
    svc_map = {str(r.customer_id): r.last_svc for r in svc_dates.all()}

    targets = []
    for cust in customers:
        cid = str(cust.id)
        result = _score_customer(cust, pump_map.get(cid), svc_map.get(cid), 0, 0, 0)
        if result["risk_score"] >= min_score:
            # Check if predicted due within horizon
            if result["days_until_due"] is not None and result["days_until_due"] <= days_horizon:
                targets.append(result)
            elif result["days_until_due"] is None and result["risk_score"] >= 50:
                targets.append(result)

    targets.sort(key=lambda x: x["risk_score"], reverse=True)

    # Generate message templates
    campaign = {
        "name": f"Proactive Service — {date.today().strftime('%B %Y')}",
        "target_count": len(targets),
        "estimated_revenue": len(targets) * 350,
        "message_template": (
            "Hi {first_name}, this is MAC Septic Services. "
            "Based on your system records, your septic system may be due for service soon. "
            "Schedule your appointment at https://react.ecbtx.com/book or reply to this text. "
            "Questions? Call us at (512) 555-1234."
        ),
        "targets": targets[:50],  # Preview first 50
        "breakdown": {
            "critical": sum(1 for t in targets if t["risk_level"] == "critical"),
            "high": sum(1 for t in targets if t["risk_level"] == "high"),
            "medium": sum(1 for t in targets if t["risk_level"] == "medium"),
        },
    }

    return campaign


@router.get("/dashboard-stats")
async def get_dashboard_stats(db: DbSession, user: CurrentUser):
    """Quick KPI stats for the predictive service dashboard."""
    today = date.today()

    # Total active customers
    total_active = (await db.execute(
        select(func.count()).select_from(Customer).where(
            and_(Customer.is_active == True, or_(Customer.is_archived == False, Customer.is_archived == None))
        )
    )).scalar() or 0

    # Overdue service schedules
    overdue_count = (await db.execute(
        select(func.count()).select_from(CustomerServiceSchedule).where(
            CustomerServiceSchedule.status == "overdue"
        )
    )).scalar() or 0

    # Customers with no service in 2+ years
    two_years_ago = today - timedelta(days=730)
    # Subquery: customers with recent service
    recent_svc = (
        select(WorkOrder.customer_id)
        .where(and_(WorkOrder.status == "completed", WorkOrder.scheduled_date >= two_years_ago))
        .distinct()
        .subquery()
    )
    no_recent = (await db.execute(
        select(func.count()).select_from(Customer).where(
            and_(
                Customer.is_active == True,
                or_(Customer.is_archived == False, Customer.is_archived == None),
                ~Customer.id.in_(select(recent_svc.c.customer_id)),
            )
        )
    )).scalar() or 0

    # Jobs completed this month
    month_start = today.replace(day=1)
    month_jobs = (await db.execute(
        select(func.count()).where(
            and_(WorkOrder.status == "completed", WorkOrder.scheduled_date >= month_start)
        )
    )).scalar() or 0

    # Aerobic systems count (need more frequent service)
    aerobic_count = (await db.execute(
        select(func.count()).select_from(Customer).where(
            and_(
                Customer.is_active == True,
                func.lower(Customer.system_type) == "aerobic",
            )
        )
    )).scalar() or 0

    return {
        "total_active_customers": total_active,
        "overdue_schedules": overdue_count,
        "no_recent_service": no_recent,
        "aerobic_systems": aerobic_count,
        "jobs_this_month": month_jobs,
        "estimated_pipeline_revenue": (overdue_count + no_recent) * 350,
    }
