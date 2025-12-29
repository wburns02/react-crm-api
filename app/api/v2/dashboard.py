from fastapi import APIRouter
from sqlalchemy import select, func, and_
from datetime import datetime, timedelta
from pydantic import BaseModel
from typing import Optional

from app.api.deps import DbSession, CurrentUser
from app.models.customer import Customer, ProspectStage
from app.models.work_order import WorkOrder, WorkOrderStatus
from app.models.invoice import Invoice, InvoiceStatus

router = APIRouter()


class DashboardStats(BaseModel):
    """Dashboard statistics response."""
    # Counts
    total_prospects: int
    active_prospects: int
    total_customers: int
    total_work_orders: int
    scheduled_work_orders: int
    in_progress_work_orders: int
    today_jobs: int

    # Pipeline
    pipeline_value: float

    # Revenue
    revenue_mtd: float
    invoices_pending: int
    invoices_overdue: int

    # Follow-ups
    upcoming_followups: int

    # Recent items (IDs only for minimal payload)
    recent_prospect_ids: list[str]
    recent_customer_ids: list[str]


class RecentProspect(BaseModel):
    """Recent prospect summary."""
    id: str
    first_name: str
    last_name: str
    company_name: Optional[str] = None
    prospect_stage: str
    estimated_value: Optional[float] = None
    created_at: Optional[str] = None


class RecentCustomer(BaseModel):
    """Recent customer summary."""
    id: str
    first_name: str
    last_name: str
    city: Optional[str] = None
    state: Optional[str] = None
    is_active: bool
    created_at: Optional[str] = None


class TodayJob(BaseModel):
    """Today's job summary."""
    id: str
    customer_id: str
    customer_name: Optional[str] = None
    job_type: str
    status: str
    time_window_start: Optional[str] = None
    assigned_technician: Optional[str] = None


class DashboardFullStats(BaseModel):
    """Full dashboard statistics with recent items."""
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
    month_start = today.replace(day=1)
    seven_days_later = today + timedelta(days=7)

    # --- PROSPECT STATS ---
    # Total prospects (customers with prospect_stage not 'won')
    prospect_stages = [
        ProspectStage.new_lead,
        ProspectStage.contacted,
        ProspectStage.qualified,
        ProspectStage.quoted,
        ProspectStage.negotiation,
    ]

    total_prospects_result = await db.execute(
        select(func.count()).where(Customer.prospect_stage.in_(prospect_stages))
    )
    total_prospects = total_prospects_result.scalar() or 0

    # Active prospects (not won or lost)
    active_prospects = total_prospects  # All non-won/lost are active

    # --- CUSTOMER STATS ---
    # Total customers (prospect_stage = 'won')
    total_customers_result = await db.execute(
        select(func.count()).where(Customer.prospect_stage == ProspectStage.won)
    )
    total_customers = total_customers_result.scalar() or 0

    # --- WORK ORDER STATS ---
    total_wo_result = await db.execute(select(func.count()).select_from(WorkOrder))
    total_work_orders = total_wo_result.scalar() or 0

    scheduled_wo_result = await db.execute(
        select(func.count()).where(
            WorkOrder.status.in_([WorkOrderStatus.scheduled, WorkOrderStatus.confirmed])
        )
    )
    scheduled_work_orders = scheduled_wo_result.scalar() or 0

    in_progress_wo_result = await db.execute(
        select(func.count()).where(
            WorkOrder.status.in_([
                WorkOrderStatus.en_route,
                WorkOrderStatus.on_site,
                WorkOrderStatus.in_progress,
            ])
        )
    )
    in_progress_work_orders = in_progress_wo_result.scalar() or 0

    # Today's jobs
    today_str = today.isoformat()
    today_jobs_result = await db.execute(
        select(func.count()).where(
            func.date(WorkOrder.scheduled_date) == today
        )
    )
    today_jobs = today_jobs_result.scalar() or 0

    # --- PIPELINE VALUE ---
    # Sum estimated_value from prospects (stored as tags or in a different field)
    # For now, we'll assume there's no estimated_value field in Customer model
    # This would require adding an estimated_value field to Customer
    pipeline_value = 0.0

    # --- REVENUE STATS ---
    # Revenue MTD (sum of paid invoices this month)
    revenue_result = await db.execute(
        select(func.sum(Invoice.total)).where(
            and_(
                Invoice.status == InvoiceStatus.paid,
                Invoice.paid_date >= month_start.isoformat(),
            )
        )
    )
    revenue_mtd = revenue_result.scalar() or 0.0

    # Pending invoices
    pending_result = await db.execute(
        select(func.count()).where(
            Invoice.status.in_([InvoiceStatus.draft, InvoiceStatus.sent])
        )
    )
    invoices_pending = pending_result.scalar() or 0

    # Overdue invoices
    overdue_result = await db.execute(
        select(func.count()).where(Invoice.status == InvoiceStatus.overdue)
    )
    invoices_overdue = overdue_result.scalar() or 0

    # --- UPCOMING FOLLOW-UPS ---
    # Count prospects with next_follow_up_date in next 7 days
    # This requires a next_follow_up_date field in Customer model
    upcoming_followups = 0

    # --- RECENT PROSPECTS ---
    recent_prospects_result = await db.execute(
        select(Customer)
        .where(Customer.prospect_stage.in_(prospect_stages))
        .order_by(Customer.created_at.desc())
        .limit(5)
    )
    recent_prospects_models = recent_prospects_result.scalars().all()

    recent_prospects = [
        RecentProspect(
            id=str(p.id),
            first_name=p.first_name,
            last_name=p.last_name,
            company_name=p.company_name,
            prospect_stage=p.prospect_stage.value if p.prospect_stage else "new_lead",
            estimated_value=None,  # Add if field exists
            created_at=p.created_at.isoformat() if p.created_at else None,
        )
        for p in recent_prospects_models
    ]

    # --- RECENT CUSTOMERS ---
    recent_customers_result = await db.execute(
        select(Customer)
        .where(Customer.prospect_stage == ProspectStage.won)
        .order_by(Customer.created_at.desc())
        .limit(5)
    )
    recent_customers_models = recent_customers_result.scalars().all()

    recent_customers = [
        RecentCustomer(
            id=str(c.id),
            first_name=c.first_name,
            last_name=c.last_name,
            city=c.city,
            state=c.state,
            is_active=c.is_active,
            created_at=c.created_at.isoformat() if c.created_at else None,
        )
        for c in recent_customers_models
    ]

    # --- TODAY'S JOBS ---
    today_jobs_result = await db.execute(
        select(WorkOrder)
        .where(func.date(WorkOrder.scheduled_date) == today)
        .order_by(WorkOrder.time_window_start)
        .limit(10)
    )
    today_jobs_models = today_jobs_result.scalars().all()

    today_jobs_list = [
        TodayJob(
            id=str(j.id),
            customer_id=str(j.customer_id),
            customer_name=None,  # Would need to join with customer
            job_type=j.job_type.value if j.job_type else "pumping",
            status=j.status.value if j.status else "draft",
            time_window_start=j.time_window_start,
            assigned_technician=j.assigned_technician,
        )
        for j in today_jobs_models
    ]

    stats = DashboardStats(
        total_prospects=total_prospects,
        active_prospects=active_prospects,
        total_customers=total_customers,
        total_work_orders=total_work_orders,
        scheduled_work_orders=scheduled_work_orders,
        in_progress_work_orders=in_progress_work_orders,
        today_jobs=today_jobs,
        pipeline_value=pipeline_value,
        revenue_mtd=revenue_mtd,
        invoices_pending=invoices_pending,
        invoices_overdue=invoices_overdue,
        upcoming_followups=upcoming_followups,
        recent_prospect_ids=[str(p.id) for p in recent_prospects_models],
        recent_customer_ids=[str(c.id) for c in recent_customers_models],
    )

    return DashboardFullStats(
        stats=stats,
        recent_prospects=recent_prospects,
        recent_customers=recent_customers,
        today_jobs=today_jobs_list,
    )
