from fastapi import APIRouter
from sqlalchemy import select, func, and_, text
from datetime import datetime, timedelta
from pydantic import BaseModel
from typing import Optional

from app.api.deps import DbSession, CurrentUser
from app.models.customer import Customer
from app.models.work_order import WorkOrder
from app.models.invoice import Invoice

router = APIRouter()


@router.get("/debug/schema")
async def debug_schema(
    db: DbSession,
    current_user: CurrentUser,
):
    """Debug endpoint to check database schema."""
    result = {}

    # List all tables
    try:
        tables_result = await db.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        )
        result["tables"] = [row[0] for row in tables_result.fetchall()]
    except Exception as e:
        result["tables_error"] = str(e)

    # Check technicians table columns
    try:
        cols_result = await db.execute(
            text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'technicians'")
        )
        result["technicians_columns"] = {row[0]: row[1] for row in cols_result.fetchall()}
    except Exception as e:
        result["technicians_error"] = str(e)

    # Check invoices table columns
    try:
        cols_result = await db.execute(
            text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'invoices'")
        )
        result["invoices_columns"] = {row[0]: row[1] for row in cols_result.fetchall()}
    except Exception as e:
        result["invoices_error"] = str(e)

    # Check payments table columns
    try:
        cols_result = await db.execute(
            text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'payments'")
        )
        result["payments_columns"] = {row[0]: row[1] for row in cols_result.fetchall()}
    except Exception as e:
        result["payments_error"] = str(e)

    # Check alembic version
    try:
        version_result = await db.execute(text("SELECT version_num FROM alembic_version"))
        result["alembic_version"] = [row[0] for row in version_result.fetchall()]
    except Exception as e:
        result["alembic_error"] = str(e)

    # Try simple technician query to debug
    try:
        tech_result = await db.execute(text("SELECT id, first_name, last_name FROM technicians LIMIT 3"))
        result["technicians_sample"] = [{"id": row[0], "name": f"{row[1]} {row[2]}"} for row in tech_result.fetchall()]
    except Exception as e:
        result["technicians_query_error"] = str(e)

    return result


class DashboardStats(BaseModel):
    """Dashboard statistics response."""

    total_prospects: int
    active_prospects: int
    total_customers: int
    total_work_orders: int
    scheduled_work_orders: int
    in_progress_work_orders: int
    today_jobs: int
    pipeline_value: float
    revenue_mtd: float
    invoices_pending: int
    invoices_overdue: int
    upcoming_followups: int
    recent_prospect_ids: list[str]
    recent_customer_ids: list[str]


class RecentProspect(BaseModel):
    id: str
    first_name: str
    last_name: str
    company_name: Optional[str] = None
    prospect_stage: str
    estimated_value: Optional[float] = None
    created_at: Optional[str] = None


class RecentCustomer(BaseModel):
    id: str
    first_name: str
    last_name: str
    city: Optional[str] = None
    state: Optional[str] = None
    is_active: bool
    created_at: Optional[str] = None


class TodayJob(BaseModel):
    id: str
    customer_id: str
    customer_name: Optional[str] = None
    job_type: str
    status: str
    time_window_start: Optional[str] = None
    assigned_technician: Optional[str] = None


class DashboardFullStats(BaseModel):
    stats: DashboardStats
    recent_prospects: list[RecentProspect]
    recent_customers: list[RecentCustomer]
    today_jobs: list[TodayJob]


@router.get("/stats", response_model=DashboardFullStats)
async def get_dashboard_stats(
    db: DbSession,
    current_user: CurrentUser,
):
    """Get aggregated dashboard statistics."""
    now = datetime.now()
    today = now.date()

    # Default values in case of errors
    total_prospects = 0
    total_customers = 0
    total_work_orders = 0
    scheduled_work_orders = 0
    in_progress_work_orders = 0
    today_jobs_count = 0
    revenue_mtd = 0.0
    invoices_pending = 0
    invoices_overdue = 0
    recent_prospects_models = []
    recent_customers_models = []
    today_jobs_models = []

    prospect_stages = ["new_lead", "contacted", "qualified", "quoted", "negotiation"]

    # Wrap all database queries in try/except for robustness
    try:
        # Total prospects
        total_prospects_result = await db.execute(
            select(func.count()).where(Customer.prospect_stage.in_(prospect_stages))
        )
        total_prospects = total_prospects_result.scalar() or 0
    except Exception:
        pass

    try:
        # Total customers (won)
        total_customers_result = await db.execute(select(func.count()).where(Customer.prospect_stage == "won"))
        total_customers = total_customers_result.scalar() or 0
    except Exception:
        pass

    try:
        # Work order stats
        total_wo_result = await db.execute(select(func.count()).select_from(WorkOrder))
        total_work_orders = total_wo_result.scalar() or 0
    except Exception:
        pass

    try:
        scheduled_wo_result = await db.execute(
            select(func.count()).where(WorkOrder.status.in_(["scheduled", "confirmed"]))
        )
        scheduled_work_orders = scheduled_wo_result.scalar() or 0
    except Exception:
        pass

    try:
        in_progress_wo_result = await db.execute(
            select(func.count()).where(WorkOrder.status.in_(["enroute", "on_site", "in_progress"]))
        )
        in_progress_work_orders = in_progress_wo_result.scalar() or 0
    except Exception:
        pass

    try:
        today_jobs_result = await db.execute(select(func.count()).where(WorkOrder.scheduled_date == today))
        today_jobs_count = today_jobs_result.scalar() or 0
    except Exception:
        pass

    # Invoice queries - table may not exist
    try:
        month_start = today.replace(day=1)
        revenue_result = await db.execute(
            select(func.sum(Invoice.total)).where(
                and_(
                    Invoice.status == "paid",
                    Invoice.paid_date >= month_start.isoformat(),
                )
            )
        )
        revenue_mtd = revenue_result.scalar() or 0.0

        pending_result = await db.execute(select(func.count()).where(Invoice.status.in_(["draft", "sent"])))
        invoices_pending = pending_result.scalar() or 0

        overdue_result = await db.execute(select(func.count()).where(Invoice.status == "overdue"))
        invoices_overdue = overdue_result.scalar() or 0
    except Exception:
        pass

    # Recent prospects - order by id if created_at is unreliable
    try:
        recent_prospects_result = await db.execute(
            select(Customer).where(Customer.prospect_stage.in_(prospect_stages)).order_by(Customer.id.desc()).limit(5)
        )
        recent_prospects_models = recent_prospects_result.scalars().all()
    except Exception:
        pass

    recent_prospects = [
        RecentProspect(
            id=str(p.id),
            first_name=p.first_name or "",
            last_name=p.last_name or "",
            company_name=None,
            prospect_stage=p.prospect_stage or "new_lead",
            estimated_value=p.estimated_value,
            created_at=p.created_at.isoformat() if p.created_at else None,
        )
        for p in recent_prospects_models
    ]

    # Recent customers - order by id if created_at is unreliable
    try:
        recent_customers_result = await db.execute(
            select(Customer).where(Customer.prospect_stage == "won").order_by(Customer.id.desc()).limit(5)
        )
        recent_customers_models = recent_customers_result.scalars().all()
    except Exception:
        pass

    recent_customers = [
        RecentCustomer(
            id=str(c.id),
            first_name=c.first_name or "",
            last_name=c.last_name or "",
            city=c.city,
            state=c.state,
            is_active=c.is_active or False,
            created_at=c.created_at.isoformat() if c.created_at else None,
        )
        for c in recent_customers_models
    ]

    # Today's jobs
    try:
        today_jobs_query = await db.execute(select(WorkOrder).where(WorkOrder.scheduled_date == today).limit(10))
        today_jobs_models = today_jobs_query.scalars().all()
    except Exception:
        pass

    today_jobs_list = [
        TodayJob(
            id=str(j.id),
            customer_id=str(j.customer_id),
            customer_name=None,
            job_type=j.job_type or "pumping",
            status=j.status or "draft",
            time_window_start=str(j.time_window_start) if j.time_window_start else None,
            assigned_technician=j.assigned_technician,
        )
        for j in today_jobs_models
    ]

    stats = DashboardStats(
        total_prospects=total_prospects,
        active_prospects=total_prospects,
        total_customers=total_customers,
        total_work_orders=total_work_orders,
        scheduled_work_orders=scheduled_work_orders,
        in_progress_work_orders=in_progress_work_orders,
        today_jobs=today_jobs_count,
        pipeline_value=0.0,
        revenue_mtd=float(revenue_mtd),
        invoices_pending=invoices_pending,
        invoices_overdue=invoices_overdue,
        upcoming_followups=0,
        recent_prospect_ids=[str(p.id) for p in recent_prospects_models],
        recent_customer_ids=[str(c.id) for c in recent_customers_models],
    )

    return DashboardFullStats(
        stats=stats,
        recent_prospects=recent_prospects,
        recent_customers=recent_customers,
        today_jobs=today_jobs_list,
    )
