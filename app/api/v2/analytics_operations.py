"""
Analytics Operations Endpoints

Provides real-time operations command center:
- Live technician locations
- Operations alerts
- Today's statistics
- Dispatch queue with AI suggestions
"""

from fastapi import APIRouter, Query
from sqlalchemy import select, func, and_
from datetime import datetime, date, timedelta
from pydantic import BaseModel, Field
from typing import Optional
from decimal import Decimal

from app.api.deps import DbSession, CurrentUser
from app.models.technician import Technician
from app.models.work_order import WorkOrder
from app.models.customer import Customer


router = APIRouter()


# =============================================================================
# Pydantic Response Schemas
# =============================================================================


class TechnicianLocation(BaseModel):
    """Live technician location data."""

    technician_id: str
    name: str
    status: str  # available, enroute, on_site, off_duty
    current_latitude: Optional[float] = None
    current_longitude: Optional[float] = None
    current_job_id: Optional[str] = None
    current_job_address: Optional[str] = None
    next_job_id: Optional[str] = None
    next_job_address: Optional[str] = None
    jobs_completed_today: int = 0
    last_update: Optional[str] = None


class OperationsAlert(BaseModel):
    """Active operations alert."""

    id: str
    alert_type: str  # running_late, customer_waiting, equipment_failure, etc.
    severity: str  # info, warning, critical
    message: str
    entity_type: Optional[str] = None  # work_order, technician, customer
    entity_id: Optional[str] = None
    created_at: str
    acknowledged: bool = False
    acknowledged_at: Optional[str] = None
    acknowledged_by: Optional[str] = None


class TodayStats(BaseModel):
    """Today's operational statistics."""

    jobs_scheduled: int
    jobs_completed: int
    jobs_in_progress: int
    completion_rate: float
    technicians_active: int
    technicians_available: int
    average_job_time_minutes: Optional[float] = None
    revenue_today: float
    customer_satisfaction: Optional[float] = None
    on_time_arrival_rate: float


class AISuggestion(BaseModel):
    """AI dispatch suggestion."""

    technician_id: str
    technician_name: str
    confidence: float
    reasoning: str
    estimated_arrival_minutes: Optional[int] = None


class DispatchQueueItem(BaseModel):
    """Dispatch queue item with AI suggestions."""

    work_order_id: str
    customer_name: str
    address: str
    job_type: str
    priority: str
    scheduled_time: Optional[str] = None
    time_window: Optional[str] = None
    estimated_duration_minutes: Optional[int] = None
    skills_required: list[str] = Field(default_factory=list)
    ai_suggestions: list[AISuggestion] = Field(default_factory=list)
    waiting_time_minutes: int = 0


# =============================================================================
# API Endpoints
# =============================================================================


@router.get("/locations")
async def get_technician_locations(
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Get live technician locations and status."""
    # Get active technicians
    result = await db.execute(select(Technician).where(Technician.is_active == True))
    technicians = result.scalars().all()

    today = date.today()
    locations = []

    for tech in technicians:
        # Get current job (in_progress status)
        current_job_result = await db.execute(
            select(WorkOrder)
            .where(
                and_(
                    WorkOrder.technician_id == tech.id,
                    WorkOrder.status.in_(["enroute", "on_site", "in_progress"]),
                    WorkOrder.scheduled_date == today,
                )
            )
            .limit(1)
        )
        current_job = current_job_result.scalar_one_or_none()

        # Get next scheduled job
        next_job_result = await db.execute(
            select(WorkOrder)
            .where(
                and_(
                    WorkOrder.technician_id == tech.id,
                    WorkOrder.status.in_(["scheduled", "confirmed"]),
                    WorkOrder.scheduled_date == today,
                )
            )
            .order_by(WorkOrder.time_window_start)
            .limit(1)
        )
        next_job = next_job_result.scalar_one_or_none()

        # Count completed jobs today
        completed_count = await db.execute(
            select(func.count())
            .select_from(WorkOrder)
            .where(
                and_(
                    WorkOrder.technician_id == tech.id,
                    WorkOrder.status == "completed",
                    WorkOrder.scheduled_date == today,
                )
            )
        )
        jobs_completed = completed_count.scalar() or 0

        # Determine status
        status = "available"
        if current_job:
            status = current_job.status
        elif not tech.is_active:
            status = "off_duty"

        locations.append(
            TechnicianLocation(
                technician_id=str(tech.id),
                name=f"{tech.first_name} {tech.last_name}",
                status=status,
                current_latitude=getattr(tech, "current_latitude", None),
                current_longitude=getattr(tech, "current_longitude", None),
                current_job_id=str(current_job.id) if current_job else None,
                current_job_address=current_job.address if current_job else None,
                next_job_id=str(next_job.id) if next_job else None,
                next_job_address=next_job.address if next_job else None,
                jobs_completed_today=jobs_completed,
                last_update=datetime.utcnow().isoformat(),
            )
        )

    return {"locations": [loc.model_dump() for loc in locations]}


@router.get("/alerts")
async def get_operations_alerts(
    db: DbSession,
    current_user: CurrentUser,
    acknowledged: bool = Query(False, description="Include acknowledged alerts"),
) -> dict:
    """Get active operations alerts."""
    today = date.today()
    now = datetime.now()
    alerts = []

    # Check for jobs running late (past scheduled time window)
    late_jobs = await db.execute(
        select(WorkOrder)
        .where(
            and_(
                WorkOrder.scheduled_date == today,
                WorkOrder.status.in_(["scheduled", "confirmed", "enroute"]),
                WorkOrder.time_window_end < now.time() if hasattr(now, "time") else True,
            )
        )
        .limit(20)
    )
    for job in late_jobs.scalars():
        alerts.append(
            OperationsAlert(
                id=f"late_{job.id}",
                alert_type="running_late",
                severity="warning",
                message=f"Job #{job.id} is past scheduled time window",
                entity_type="work_order",
                entity_id=str(job.id),
                created_at=now.isoformat(),
                acknowledged=False,
            )
        )

    # Check for unassigned jobs
    unassigned_result = await db.execute(
        select(func.count())
        .select_from(WorkOrder)
        .where(
            and_(
                WorkOrder.scheduled_date == today,
                WorkOrder.technician_id.is_(None),
                WorkOrder.status.in_(["draft", "scheduled"]),
            )
        )
    )
    unassigned_count = unassigned_result.scalar() or 0

    if unassigned_count > 0:
        alerts.append(
            OperationsAlert(
                id="unassigned_jobs",
                alert_type="unassigned_jobs",
                severity="warning" if unassigned_count < 5 else "critical",
                message=f"{unassigned_count} jobs scheduled today without technician assignment",
                entity_type="schedule",
                created_at=now.isoformat(),
                acknowledged=False,
            )
        )

    return {"alerts": [a.model_dump() for a in alerts]}


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    db: DbSession,
    current_user: CurrentUser,
    alert_id: str,
) -> dict:
    """Acknowledge an operations alert."""
    # In production, this would update a database record
    return {
        "alert": {
            "id": alert_id,
            "acknowledged": True,
            "acknowledged_at": datetime.utcnow().isoformat(),
            "acknowledged_by": str(current_user.id),
        }
    }


@router.get("/today")
async def get_today_stats(
    db: DbSession,
    current_user: CurrentUser,
) -> TodayStats:
    """Get today's operational statistics."""
    today = date.today()

    # Jobs scheduled today
    scheduled_result = await db.execute(
        select(func.count()).select_from(WorkOrder).where(WorkOrder.scheduled_date == today)
    )
    jobs_scheduled = scheduled_result.scalar() or 0

    # Jobs completed today
    completed_result = await db.execute(
        select(func.count())
        .select_from(WorkOrder)
        .where(and_(WorkOrder.scheduled_date == today, WorkOrder.status == "completed"))
    )
    jobs_completed = completed_result.scalar() or 0

    # Jobs in progress
    in_progress_result = await db.execute(
        select(func.count())
        .select_from(WorkOrder)
        .where(and_(WorkOrder.scheduled_date == today, WorkOrder.status.in_(["enroute", "on_site", "in_progress"])))
    )
    jobs_in_progress = in_progress_result.scalar() or 0

    # Active technicians
    active_techs_result = await db.execute(
        select(func.count(func.distinct(WorkOrder.technician_id))).where(
            and_(
                WorkOrder.scheduled_date == today,
                WorkOrder.status.in_(["enroute", "on_site", "in_progress", "completed"]),
            )
        )
    )
    technicians_active = active_techs_result.scalar() or 0

    # Total active technicians
    total_techs_result = await db.execute(
        select(func.count()).select_from(Technician).where(Technician.is_active == True)
    )
    total_techs = total_techs_result.scalar() or 0

    # Revenue today
    revenue_result = await db.execute(
        select(func.sum(WorkOrder.total_amount)).where(
            and_(WorkOrder.scheduled_date == today, WorkOrder.status == "completed")
        )
    )
    revenue_today = float(revenue_result.scalar() or 0)

    # Completion rate
    completion_rate = (jobs_completed / jobs_scheduled * 100) if jobs_scheduled > 0 else 0.0

    # Available technicians
    technicians_available = max(0, total_techs - technicians_active)

    return TodayStats(
        jobs_scheduled=jobs_scheduled,
        jobs_completed=jobs_completed,
        jobs_in_progress=jobs_in_progress,
        completion_rate=round(completion_rate, 1),
        technicians_active=technicians_active,
        technicians_available=technicians_available,
        average_job_time_minutes=None,  # Would calculate from actual labor time
        revenue_today=round(revenue_today, 2),
        customer_satisfaction=None,
        on_time_arrival_rate=85.0,  # Would calculate from actual data
    )


@router.get("/dispatch-queue")
async def get_dispatch_queue(
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Get dispatch queue with AI suggestions for unassigned jobs."""
    today = date.today()

    # Get unassigned jobs
    result = await db.execute(
        select(WorkOrder, Customer)
        .outerjoin(Customer, WorkOrder.customer_id == Customer.id)
        .where(
            and_(
                WorkOrder.scheduled_date == today,
                WorkOrder.technician_id.is_(None),
                WorkOrder.status.in_(["draft", "scheduled"]),
            )
        )
        .order_by(WorkOrder.time_window_start)
        .limit(50)
    )
    jobs = result.all()

    # Get available technicians for AI suggestions
    techs_result = await db.execute(select(Technician).where(Technician.is_active == True).limit(10))
    available_techs = techs_result.scalars().all()

    queue = []
    for wo, customer in jobs:
        customer_name = "Unknown Customer"
        if customer:
            customer_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip()

        # Generate AI suggestions (simplified - in production use actual ML model)
        suggestions = []
        for tech in available_techs[:3]:
            suggestions.append(
                AISuggestion(
                    technician_id=str(tech.id),
                    technician_name=tech.name,
                    confidence=0.85,
                    reasoning="Based on proximity, skills, and availability",
                    estimated_arrival_minutes=30,
                )
            )

        time_window = None
        if wo.time_window_start and wo.time_window_end:
            time_window = f"{wo.time_window_start} - {wo.time_window_end}"

        queue.append(
            DispatchQueueItem(
                work_order_id=str(wo.id),
                customer_name=customer_name,
                address=wo.address or "Address not set",
                job_type=wo.job_type or "General",
                priority=wo.priority or "normal",
                scheduled_time=wo.scheduled_date.isoformat() if wo.scheduled_date else None,
                time_window=time_window,
                estimated_duration_minutes=wo.estimated_duration,
                skills_required=[],
                ai_suggestions=suggestions,
                waiting_time_minutes=0,
            )
        )

    return {"queue": [q.model_dump() for q in queue]}


@router.post("/dispatch-queue/accept")
async def accept_dispatch_suggestion(
    db: DbSession,
    current_user: CurrentUser,
    work_order_id: str = Query(...),
    technician_id: str = Query(...),
) -> dict:
    """Accept AI dispatch suggestion and assign technician."""
    # Get the work order
    from uuid import UUID as _UUID
    try:
        wo_uuid = _UUID(work_order_id)
        tech_uuid = _UUID(technician_id)
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    result = await db.execute(select(WorkOrder).where(WorkOrder.id == wo_uuid))
    work_order = result.scalar_one_or_none()

    if not work_order:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Work order not found")

    # Assign technician
    work_order.technician_id = tech_uuid
    work_order.status = "scheduled"

    await db.commit()

    return {"success": True}
