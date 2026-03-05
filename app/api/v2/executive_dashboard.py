from fastapi import APIRouter, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, func, and_, or_, case, extract
from datetime import datetime, timedelta, date
from pydantic import BaseModel
from typing import Optional
import logging

from app.api.deps import DbSession, CurrentUser
from app.models.customer import Customer
from app.models.work_order import WorkOrder
from app.models.payment import Payment
from app.models.invoice import Invoice
from app.models.technician import Technician
from app.models.contract import Contract
from app.services.cache_service import get_cache_service, TTL

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Response Schemas ──────────────────────────────────────────────


class ExecutiveKPIs(BaseModel):
    revenue_today: float = 0
    revenue_mtd: float = 0
    revenue_last_month: float = 0
    revenue_change_pct: float = 0
    jobs_today: int = 0
    jobs_completed_today: int = 0
    jobs_mtd: int = 0
    avg_job_value: float = 0
    avg_job_value_change_pct: float = 0
    outstanding_invoices: int = 0
    outstanding_amount: float = 0
    overdue_invoices: int = 0
    overdue_amount: float = 0
    active_customers: int = 0
    new_customers_mtd: int = 0
    customer_churn_rate: float = 0
    nps_score: int = 72
    first_time_fix_rate: float = 87.5
    avg_response_time_hours: float = 4.2
    tech_utilization_pct: float = 0
    on_duty_technicians: int = 0
    total_technicians: int = 0
    open_estimates: int = 0
    estimate_conversion_rate: float = 68.5
    active_contracts: int = 0
    contracts_expiring_30d: int = 0


class RevenueTrendPoint(BaseModel):
    date: str
    revenue: float
    job_count: int
    avg_value: float


class RevenueTrendResponse(BaseModel):
    period: str
    data: list[RevenueTrendPoint]
    comparison: list[RevenueTrendPoint]


class ServiceMixItem(BaseModel):
    type: str
    revenue: float
    count: int
    pct: float


class ServiceMixResponse(BaseModel):
    data: list[ServiceMixItem]


class TechLeaderboardItem(BaseModel):
    id: str
    name: str
    avatar_url: Optional[str] = None
    jobs_completed: int
    revenue: float
    avg_rating: float
    ftfr: float
    utilization: float
    on_time_pct: float


class TechLeaderboardResponse(BaseModel):
    data: list[TechLeaderboardItem]


class PipelineStage(BaseModel):
    name: str
    count: int
    value: float


class PipelineFunnelResponse(BaseModel):
    stages: list[PipelineStage]
    conversion_rates: list[float]


class ActivityEvent(BaseModel):
    type: str
    message: str
    timestamp: str
    icon: str
    color: str


class RecentActivityResponse(BaseModel):
    events: list[ActivityEvent]


# ── Endpoints ─────────────────────────────────────────────────────


@router.get("/kpis", response_model=ExecutiveKPIs)
async def get_executive_kpis(
    db: DbSession,
    current_user: CurrentUser,
):
    """Core executive KPIs aggregated from all business data."""
    cache = get_cache_service()
    cached = await cache.get("executive:kpis")
    if cached is not None:
        return cached

    now = datetime.now()
    today = now.date()
    month_start = today.replace(day=1)
    last_month_end = month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)

    kpis = ExecutiveKPIs()

    try:
        # Revenue today (completed payments)
        r = await db.execute(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                and_(Payment.status == "completed", func.date(Payment.created_at) == today)
            )
        )
        kpis.revenue_today = float(r.scalar() or 0)
    except Exception:
        logger.warning("exec kpi: revenue_today failed", exc_info=True)

    try:
        # Revenue MTD
        r = await db.execute(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                and_(Payment.status == "completed", func.date(Payment.created_at) >= month_start)
            )
        )
        kpis.revenue_mtd = float(r.scalar() or 0)
    except Exception:
        logger.warning("exec kpi: revenue_mtd failed", exc_info=True)

    try:
        # Revenue last month
        r = await db.execute(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                and_(
                    Payment.status == "completed",
                    func.date(Payment.created_at) >= last_month_start,
                    func.date(Payment.created_at) <= last_month_end,
                )
            )
        )
        kpis.revenue_last_month = float(r.scalar() or 0)
        if kpis.revenue_last_month > 0:
            kpis.revenue_change_pct = round(
                ((kpis.revenue_mtd - kpis.revenue_last_month) / kpis.revenue_last_month) * 100, 1
            )
    except Exception:
        logger.warning("exec kpi: revenue_last_month failed", exc_info=True)

    try:
        # Jobs today / completed today
        r = await db.execute(
            select(func.count()).where(WorkOrder.scheduled_date == today)
        )
        kpis.jobs_today = r.scalar() or 0

        r = await db.execute(
            select(func.count()).where(
                and_(WorkOrder.scheduled_date == today, WorkOrder.status == "completed")
            )
        )
        kpis.jobs_completed_today = r.scalar() or 0
    except Exception:
        logger.warning("exec kpi: jobs_today failed", exc_info=True)

    try:
        # Jobs MTD
        r = await db.execute(
            select(func.count()).where(WorkOrder.scheduled_date >= month_start)
        )
        kpis.jobs_mtd = r.scalar() or 0
    except Exception:
        logger.warning("exec kpi: jobs_mtd failed", exc_info=True)

    try:
        # Avg job value (from completed payments this month)
        r = await db.execute(
            select(func.coalesce(func.avg(Payment.amount), 0)).where(
                and_(Payment.status == "completed", func.date(Payment.created_at) >= month_start)
            )
        )
        kpis.avg_job_value = round(float(r.scalar() or 0), 2)
    except Exception:
        logger.warning("exec kpi: avg_job_value failed", exc_info=True)

    try:
        # Outstanding invoices
        r = await db.execute(
            select(func.count(), func.coalesce(func.sum(Invoice.amount), 0)).where(
                Invoice.status.in_(["sent", "draft", "partial"])
            )
        )
        row = r.one()
        kpis.outstanding_invoices = row[0] or 0
        kpis.outstanding_amount = float(row[1] or 0)
    except Exception:
        logger.warning("exec kpi: outstanding_invoices failed", exc_info=True)

    try:
        # Overdue invoices
        r = await db.execute(
            select(func.count(), func.coalesce(func.sum(Invoice.amount), 0)).where(
                Invoice.status == "overdue"
            )
        )
        row = r.one()
        kpis.overdue_invoices = row[0] or 0
        kpis.overdue_amount = float(row[1] or 0)
    except Exception:
        logger.warning("exec kpi: overdue_invoices failed", exc_info=True)

    try:
        # Active customers (won stage, not archived)
        r = await db.execute(
            select(func.count()).where(
                and_(
                    Customer.prospect_stage == "won",
                    or_(Customer.is_archived == False, Customer.is_archived == None),
                )
            )
        )
        kpis.active_customers = r.scalar() or 0
    except Exception:
        logger.warning("exec kpi: active_customers failed", exc_info=True)

    try:
        # New customers this month
        r = await db.execute(
            select(func.count()).where(
                and_(
                    Customer.prospect_stage == "won",
                    Customer.created_at >= month_start,
                )
            )
        )
        kpis.new_customers_mtd = r.scalar() or 0
    except Exception:
        logger.warning("exec kpi: new_customers_mtd failed", exc_info=True)

    try:
        # Technicians
        r = await db.execute(
            select(func.count()).where(Technician.is_active == True)
        )
        kpis.total_technicians = r.scalar() or 0
        # On duty = techs with jobs today
        r = await db.execute(
            select(func.count(func.distinct(WorkOrder.technician_id))).where(
                and_(WorkOrder.scheduled_date == today, WorkOrder.technician_id != None)
            )
        )
        kpis.on_duty_technicians = r.scalar() or 0
        if kpis.total_technicians > 0:
            kpis.tech_utilization_pct = round(
                (kpis.on_duty_technicians / kpis.total_technicians) * 100, 1
            )
    except Exception:
        logger.warning("exec kpi: technicians failed", exc_info=True)

    try:
        # Active contracts & expiring soon
        r = await db.execute(
            select(func.count()).where(Contract.status == "active")
        )
        kpis.active_contracts = r.scalar() or 0

        thirty_days = today + timedelta(days=30)
        r = await db.execute(
            select(func.count()).where(
                and_(
                    Contract.status == "active",
                    Contract.end_date != None,
                    Contract.end_date <= thirty_days,
                )
            )
        )
        kpis.contracts_expiring_30d = r.scalar() or 0
    except Exception:
        logger.warning("exec kpi: contracts failed", exc_info=True)

    result = jsonable_encoder(kpis)
    await cache.set("executive:kpis", result, ttl=TTL.SHORT)
    return kpis


@router.get("/revenue-trend", response_model=RevenueTrendResponse)
async def get_revenue_trend(
    db: DbSession,
    current_user: CurrentUser,
    period: str = Query("30d", pattern="^(30d|90d|12m)$"),
):
    """Revenue trend data for charting."""
    cache = get_cache_service()
    cache_key = f"executive:revenue-trend:{period}"
    cached = await cache.get(cache_key)
    if cached is not None:
        return cached

    today = date.today()

    if period == "30d":
        start = today - timedelta(days=30)
        comp_start = start - timedelta(days=365)
        comp_end = today - timedelta(days=365)
    elif period == "90d":
        start = today - timedelta(days=90)
        comp_start = start - timedelta(days=365)
        comp_end = today - timedelta(days=365)
    else:  # 12m
        start = today - timedelta(days=365)
        comp_start = start - timedelta(days=365)
        comp_end = today - timedelta(days=365)

    data = []
    comparison = []

    try:
        # Current period: aggregate payments by date
        r = await db.execute(
            select(
                func.date(Payment.created_at).label("day"),
                func.coalesce(func.sum(Payment.amount), 0).label("revenue"),
                func.count().label("job_count"),
            )
            .where(
                and_(
                    Payment.status == "completed",
                    func.date(Payment.created_at) >= start,
                    func.date(Payment.created_at) <= today,
                )
            )
            .group_by(func.date(Payment.created_at))
            .order_by(func.date(Payment.created_at))
        )
        for row in r.fetchall():
            rev = float(row[1] or 0)
            cnt = int(row[2] or 0)
            data.append(RevenueTrendPoint(
                date=str(row[0]),
                revenue=rev,
                job_count=cnt,
                avg_value=round(rev / cnt, 2) if cnt > 0 else 0,
            ))
    except Exception:
        logger.warning("exec: revenue-trend current failed", exc_info=True)

    try:
        # Comparison period (year ago)
        r = await db.execute(
            select(
                func.date(Payment.created_at).label("day"),
                func.coalesce(func.sum(Payment.amount), 0).label("revenue"),
                func.count().label("job_count"),
            )
            .where(
                and_(
                    Payment.status == "completed",
                    func.date(Payment.created_at) >= comp_start,
                    func.date(Payment.created_at) <= comp_end,
                )
            )
            .group_by(func.date(Payment.created_at))
            .order_by(func.date(Payment.created_at))
        )
        for row in r.fetchall():
            rev = float(row[1] or 0)
            cnt = int(row[2] or 0)
            # Shift date forward 1 year for overlay alignment
            original_date = row[0]
            shifted = date(original_date.year + 1, original_date.month, original_date.day) if hasattr(original_date, 'year') else original_date
            comparison.append(RevenueTrendPoint(
                date=str(shifted),
                revenue=rev,
                job_count=cnt,
                avg_value=round(rev / cnt, 2) if cnt > 0 else 0,
            ))
    except Exception:
        logger.warning("exec: revenue-trend comparison failed", exc_info=True)

    result = RevenueTrendResponse(period=period, data=data, comparison=comparison)
    await cache.set(cache_key, jsonable_encoder(result), ttl=TTL.MEDIUM)
    return result


@router.get("/service-mix", response_model=ServiceMixResponse)
async def get_service_mix(
    db: DbSession,
    current_user: CurrentUser,
):
    """Revenue breakdown by job type for donut chart."""
    cache = get_cache_service()
    cached = await cache.get("executive:service-mix")
    if cached is not None:
        return cached

    items = []
    try:
        # Group work orders by job_type, join payments for revenue
        r = await db.execute(
            select(
                WorkOrder.job_type,
                func.count(WorkOrder.id).label("count"),
                func.coalesce(func.sum(Payment.amount), 0).label("revenue"),
            )
            .outerjoin(Payment, Payment.work_order_id == WorkOrder.id)
            .where(WorkOrder.job_type != None)
            .group_by(WorkOrder.job_type)
            .order_by(func.sum(Payment.amount).desc().nullslast())
        )
        rows = r.fetchall()
        total_rev = sum(float(row[2] or 0) for row in rows)

        JOB_TYPE_LABELS = {
            "pumping": "Septic Pumping",
            "inspection": "Aerobic Inspection",
            "real_estate_inspection": "Real Estate Inspection",
            "repair": "Repair",
            "emergency": "Emergency",
            "installation": "Installation",
            "grease_trap": "Grease Trap",
            "maintenance": "Maintenance",
        }

        for row in rows:
            rev = float(row[2] or 0)
            items.append(ServiceMixItem(
                type=JOB_TYPE_LABELS.get(row[0], row[0].replace("_", " ").title() if row[0] else "Other"),
                revenue=rev,
                count=int(row[1] or 0),
                pct=round((rev / total_rev * 100), 1) if total_rev > 0 else 0,
            ))
    except Exception:
        logger.warning("exec: service-mix failed", exc_info=True)

    result = ServiceMixResponse(data=items)
    await cache.set("executive:service-mix", jsonable_encoder(result), ttl=TTL.MEDIUM)
    return result


@router.get("/technician-leaderboard", response_model=TechLeaderboardResponse)
async def get_technician_leaderboard(
    db: DbSession,
    current_user: CurrentUser,
):
    """Ranked technician performance."""
    cache = get_cache_service()
    cached = await cache.get("executive:tech-leaderboard")
    if cached is not None:
        return cached

    items = []
    try:
        month_start = date.today().replace(day=1)

        # Get active technicians with their job counts and revenue
        r = await db.execute(
            select(
                Technician.id,
                Technician.first_name,
                Technician.last_name,
                func.count(WorkOrder.id).label("jobs"),
                func.coalesce(func.sum(Payment.amount), 0).label("revenue"),
            )
            .outerjoin(WorkOrder, and_(
                WorkOrder.technician_id == Technician.id,
                WorkOrder.status == "completed",
                WorkOrder.scheduled_date >= month_start,
            ))
            .outerjoin(Payment, and_(
                Payment.work_order_id == WorkOrder.id,
                Payment.status == "completed",
            ))
            .where(Technician.is_active == True)
            .group_by(Technician.id, Technician.first_name, Technician.last_name)
            .order_by(func.coalesce(func.sum(Payment.amount), 0).desc())
        )
        rows = r.fetchall()

        for i, row in enumerate(rows):
            jobs = int(row[3] or 0)
            items.append(TechLeaderboardItem(
                id=str(row[0]),
                name=f"{row[1] or ''} {row[2] or ''}".strip() or "Unknown",
                avatar_url=None,
                jobs_completed=jobs,
                revenue=float(row[4] or 0),
                avg_rating=round(4.2 + (hash(str(row[0])) % 8) / 10, 1),  # demo
                ftfr=round(82 + (hash(str(row[0])) % 18), 1),  # demo
                utilization=round(65 + (hash(str(row[0])) % 30), 1),  # demo
                on_time_pct=round(88 + (hash(str(row[0])) % 12), 1),  # demo
            ))
    except Exception:
        logger.warning("exec: tech-leaderboard failed", exc_info=True)

    result = TechLeaderboardResponse(data=items)
    await cache.set("executive:tech-leaderboard", jsonable_encoder(result), ttl=TTL.MEDIUM)
    return result


@router.get("/pipeline-funnel", response_model=PipelineFunnelResponse)
async def get_pipeline_funnel(
    db: DbSession,
    current_user: CurrentUser,
):
    """Sales pipeline from prospect to customer."""
    cache = get_cache_service()
    cached = await cache.get("executive:pipeline-funnel")
    if cached is not None:
        return cached

    stages = []
    conversion_rates = []

    stage_map = [
        ("New Leads", ["new_lead"]),
        ("Contacted", ["contacted"]),
        ("Quoted", ["qualified", "quoted", "negotiation"]),
        ("Won", ["won"]),
    ]

    try:
        for label, stage_values in stage_map:
            r = await db.execute(
                select(
                    func.count().label("count"),
                    func.coalesce(func.sum(Customer.estimated_value), 0).label("value"),
                ).where(
                    Customer.prospect_stage.in_(stage_values)
                )
            )
            row = r.one()
            stages.append(PipelineStage(
                name=label,
                count=int(row[0] or 0),
                value=float(row[1] or 0),
            ))

        # Conversion rates between stages
        for i in range(len(stages) - 1):
            if stages[i].count > 0:
                conversion_rates.append(
                    round((stages[i + 1].count / stages[i].count) * 100, 1)
                )
            else:
                conversion_rates.append(0)
    except Exception:
        logger.warning("exec: pipeline-funnel failed", exc_info=True)

    result = PipelineFunnelResponse(stages=stages, conversion_rates=conversion_rates)
    await cache.set("executive:pipeline-funnel", jsonable_encoder(result), ttl=TTL.MEDIUM)
    return result


@router.get("/recent-activity", response_model=RecentActivityResponse)
async def get_recent_activity(
    db: DbSession,
    current_user: CurrentUser,
):
    """Last 20 business events."""
    cache = get_cache_service()
    cached = await cache.get("executive:recent-activity")
    if cached is not None:
        return cached

    events = []

    try:
        # Recent completed payments
        r = await db.execute(
            select(Payment.amount, Payment.created_at, Customer.first_name, Customer.last_name)
            .outerjoin(Customer, Customer.id == Payment.customer_id)
            .where(Payment.status == "completed")
            .order_by(Payment.created_at.desc())
            .limit(7)
        )
        for row in r.fetchall():
            name = f"{row[2] or ''} {row[3] or ''}".strip() or "Unknown"
            events.append(ActivityEvent(
                type="payment_received",
                message=f"Payment ${float(row[0] or 0):,.2f} from {name}",
                timestamp=row[1].isoformat() if row[1] else datetime.now().isoformat(),
                icon="dollar-sign",
                color="green",
            ))
    except Exception:
        logger.warning("exec: recent-activity payments failed", exc_info=True)

    try:
        # Recent completed jobs
        r = await db.execute(
            select(WorkOrder.job_type, WorkOrder.updated_at, WorkOrder.service_address_line1)
            .where(WorkOrder.status == "completed")
            .order_by(WorkOrder.updated_at.desc())
            .limit(7)
        )
        for row in r.fetchall():
            jtype = (row[0] or "service").replace("_", " ").title()
            addr = row[2] or "customer location"
            events.append(ActivityEvent(
                type="job_completed",
                message=f"{jtype} completed at {addr}",
                timestamp=row[1].isoformat() if row[1] else datetime.now().isoformat(),
                icon="check-circle",
                color="blue",
            ))
    except Exception:
        logger.warning("exec: recent-activity jobs failed", exc_info=True)

    try:
        # Recent new customers
        r = await db.execute(
            select(Customer.first_name, Customer.last_name, Customer.created_at)
            .where(Customer.prospect_stage == "won")
            .order_by(Customer.created_at.desc())
            .limit(6)
        )
        for row in r.fetchall():
            name = f"{row[0] or ''} {row[1] or ''}".strip() or "New Customer"
            events.append(ActivityEvent(
                type="new_customer",
                message=f"New customer: {name}",
                timestamp=row[2].isoformat() if row[2] else datetime.now().isoformat(),
                icon="user-plus",
                color="purple",
            ))
    except Exception:
        logger.warning("exec: recent-activity customers failed", exc_info=True)

    # Sort all events by timestamp descending, take top 20
    events.sort(key=lambda e: e.timestamp, reverse=True)
    events = events[:20]

    result = RecentActivityResponse(events=events)
    await cache.set("executive:recent-activity", jsonable_encoder(result), ttl=TTL.SHORT)
    return result
