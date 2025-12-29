from fastapi import APIRouter, Query
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload
from typing import Optional
from datetime import datetime, date, timedelta
from pydantic import BaseModel

from app.api.deps import DbSession, CurrentUser
from app.models.work_order import WorkOrder, WorkOrderStatus
from app.models.customer import Customer
from app.models.technician import Technician

router = APIRouter()


class ScheduleStats(BaseModel):
    """Schedule statistics."""
    today_jobs: int
    week_jobs: int
    unscheduled_jobs: int
    emergency_jobs: int


class ScheduleWorkOrder(BaseModel):
    """Work order for schedule views."""
    id: str
    customer_id: str
    customer_name: Optional[str] = None
    job_type: str
    status: str
    priority: str
    scheduled_date: Optional[str] = None
    time_window_start: Optional[str] = None
    time_window_end: Optional[str] = None
    assigned_technician: Optional[str] = None
    service_address: Optional[str] = None
    service_city: Optional[str] = None


class UnscheduledResponse(BaseModel):
    """Unscheduled work orders response."""
    items: list[ScheduleWorkOrder]
    total: int


class TechnicianSchedule(BaseModel):
    """Technician with their scheduled jobs."""
    id: str
    name: str
    is_active: bool
    jobs: list[ScheduleWorkOrder]
    total_hours: float


class ScheduleByTechnicianResponse(BaseModel):
    """Schedule grouped by technician."""
    technicians: list[TechnicianSchedule]
    unassigned: list[ScheduleWorkOrder]


def work_order_to_schedule(wo: WorkOrder) -> dict:
    """Convert WorkOrder to schedule format."""
    return {
        "id": str(wo.id),
        "customer_id": str(wo.customer_id),
        "customer_name": None,  # Would need join
        "job_type": wo.job_type.value if wo.job_type else "pumping",
        "status": wo.status.value if wo.status else "draft",
        "priority": wo.priority.value if wo.priority else "normal",
        "scheduled_date": wo.scheduled_date.isoformat() if wo.scheduled_date else None,
        "time_window_start": wo.time_window_start,
        "time_window_end": wo.time_window_end,
        "assigned_technician": wo.assigned_technician,
        "service_address": wo.service_address,
        "service_city": wo.service_city,
    }


@router.get("/stats", response_model=ScheduleStats)
async def get_schedule_stats(
    db: DbSession,
    current_user: CurrentUser,
):
    """Get schedule statistics."""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())  # Monday
    week_end = week_start + timedelta(days=6)  # Sunday

    # Today's jobs
    today_result = await db.execute(
        select(func.count()).where(
            func.date(WorkOrder.scheduled_date) == today
        )
    )
    today_jobs = today_result.scalar() or 0

    # This week's jobs
    week_result = await db.execute(
        select(func.count()).where(
            and_(
                func.date(WorkOrder.scheduled_date) >= week_start,
                func.date(WorkOrder.scheduled_date) <= week_end,
            )
        )
    )
    week_jobs = week_result.scalar() or 0

    # Unscheduled (draft without date)
    unscheduled_result = await db.execute(
        select(func.count()).where(
            and_(
                WorkOrder.status == WorkOrderStatus.draft,
                or_(
                    WorkOrder.scheduled_date.is_(None),
                    WorkOrder.scheduled_date == None,
                ),
            )
        )
    )
    unscheduled_jobs = unscheduled_result.scalar() or 0

    # Emergency jobs (any status)
    emergency_result = await db.execute(
        select(func.count()).where(
            WorkOrder.priority == "emergency"
        )
    )
    emergency_jobs = emergency_result.scalar() or 0

    return ScheduleStats(
        today_jobs=today_jobs,
        week_jobs=week_jobs,
        unscheduled_jobs=unscheduled_jobs,
        emergency_jobs=emergency_jobs,
    )


@router.get("/unscheduled", response_model=UnscheduledResponse)
async def get_unscheduled_work_orders(
    db: DbSession,
    current_user: CurrentUser,
    page_size: int = Query(100, ge=1, le=500),
):
    """Get unscheduled work orders (draft without date)."""
    query = select(WorkOrder).where(
        and_(
            WorkOrder.status == WorkOrderStatus.draft,
            or_(
                WorkOrder.scheduled_date.is_(None),
                WorkOrder.scheduled_date == None,
            ),
        )
    ).order_by(WorkOrder.created_at.desc()).limit(page_size)

    result = await db.execute(query)
    work_orders = result.scalars().all()

    return UnscheduledResponse(
        items=[work_order_to_schedule(wo) for wo in work_orders],
        total=len(work_orders),
    )


@router.get("/by-date", response_model=UnscheduledResponse)
async def get_schedule_by_date(
    db: DbSession,
    current_user: CurrentUser,
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
):
    """Get all work orders scheduled for a specific date."""
    query = select(WorkOrder).where(
        func.date(WorkOrder.scheduled_date) == date
    ).order_by(WorkOrder.time_window_start)

    result = await db.execute(query)
    work_orders = result.scalars().all()

    return UnscheduledResponse(
        items=[work_order_to_schedule(wo) for wo in work_orders],
        total=len(work_orders),
    )


@router.get("/by-technician/{technician_name}")
async def get_schedule_by_technician(
    technician_name: str,
    db: DbSession,
    current_user: CurrentUser,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """Get work orders assigned to a specific technician."""
    query = select(WorkOrder).where(
        WorkOrder.assigned_technician == technician_name
    )

    if date_from:
        query = query.where(func.date(WorkOrder.scheduled_date) >= date_from)
    if date_to:
        query = query.where(func.date(WorkOrder.scheduled_date) <= date_to)

    query = query.order_by(WorkOrder.scheduled_date, WorkOrder.time_window_start)

    result = await db.execute(query)
    work_orders = result.scalars().all()

    return {
        "technician": technician_name,
        "items": [work_order_to_schedule(wo) for wo in work_orders],
        "total": len(work_orders),
    }


@router.get("/week-view")
async def get_week_view(
    db: DbSession,
    current_user: CurrentUser,
    start_date: str = Query(..., description="Start date (Monday) in YYYY-MM-DD format"),
):
    """Get all work orders for a week, grouped by date."""
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = start + timedelta(days=6)

    query = select(WorkOrder).where(
        and_(
            func.date(WorkOrder.scheduled_date) >= start,
            func.date(WorkOrder.scheduled_date) <= end,
        )
    ).order_by(WorkOrder.scheduled_date, WorkOrder.time_window_start)

    result = await db.execute(query)
    work_orders = result.scalars().all()

    # Group by date
    by_date: dict[str, list[dict]] = {}
    for i in range(7):
        day = (start + timedelta(days=i)).isoformat()
        by_date[day] = []

    for wo in work_orders:
        if wo.scheduled_date:
            day_str = wo.scheduled_date.date().isoformat() if hasattr(wo.scheduled_date, 'date') else str(wo.scheduled_date)[:10]
            if day_str in by_date:
                by_date[day_str].append(work_order_to_schedule(wo))

    return {
        "start_date": start_date,
        "end_date": end.isoformat(),
        "days": by_date,
        "total": len(work_orders),
    }
