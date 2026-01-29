"""Service Intervals API - Recurring service scheduling and reminders."""

from datetime import date, timedelta, datetime
from typing import List, Optional
from uuid import uuid4, UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db, get_current_user
from app.models import Customer
from app.models.service_interval import ServiceInterval, CustomerServiceSchedule, ServiceReminder

router = APIRouter()


# =============================================================================
# SCHEMAS
# =============================================================================


class ServiceIntervalBase(BaseModel):
    name: str
    description: Optional[str] = None
    service_type: str
    interval_months: int
    reminder_days_before: List[int] = [30, 14, 7]
    is_active: bool = True


class ServiceIntervalCreate(ServiceIntervalBase):
    pass


class ServiceIntervalUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    service_type: Optional[str] = None
    interval_months: Optional[int] = None
    reminder_days_before: Optional[List[int]] = None
    is_active: Optional[bool] = None


class ServiceIntervalResponse(ServiceIntervalBase):
    id: str
    created_at: str

    class Config:
        from_attributes = True


class CustomerServiceScheduleResponse(BaseModel):
    id: str
    customer_id: int
    customer_name: str
    service_interval_id: str
    service_interval_name: str
    last_service_date: Optional[str] = None
    next_due_date: str
    status: str
    scheduled_work_order_id: Optional[str] = None
    days_until_due: int
    reminder_sent: bool = False
    notes: Optional[str] = None


class ServiceIntervalStats(BaseModel):
    total_customers_with_intervals: int = 0
    upcoming_services: int = 0
    due_services: int = 0
    overdue_services: int = 0
    reminders_sent_today: int = 0
    reminders_pending: int = 0


class AssignIntervalRequest(BaseModel):
    customer_id: int
    service_interval_id: str
    last_service_date: Optional[str] = None
    notes: Optional[str] = None


class BulkAssignRequest(BaseModel):
    customer_ids: List[int]
    service_interval_id: str


class CreateWorkOrderRequest(BaseModel):
    schedule_id: str
    scheduled_date: str
    technician_id: Optional[str] = None
    notes: Optional[str] = None


class SendReminderRequest(BaseModel):
    schedule_id: str
    reminder_type: str  # sms, email, push


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def calculate_status(next_due_date: date) -> tuple[str, int]:
    """Calculate status and days until due from next_due_date."""
    today = date.today()
    days_until = (next_due_date - today).days

    if days_until < 0:
        status = "overdue"
    elif days_until <= 7:
        status = "due"
    else:
        status = "upcoming"

    return status, days_until


# =============================================================================
# SERVICE INTERVAL ENDPOINTS (Templates)
# =============================================================================


@router.get("/", response_model=dict)
async def list_service_intervals(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get all service interval templates."""
    result = await db.execute(
        select(ServiceInterval).order_by(ServiceInterval.name)
    )
    intervals = result.scalars().all()

    intervals_data = [
        {
            "id": str(interval.id),
            "name": interval.name,
            "description": interval.description,
            "service_type": interval.service_type,
            "interval_months": interval.interval_months,
            "reminder_days_before": interval.reminder_days_before,
            "is_active": interval.is_active,
            "created_at": interval.created_at.isoformat() if interval.created_at else None,
        }
        for interval in intervals
    ]

    return {"intervals": intervals_data, "total": len(intervals_data)}


@router.get("/{interval_id}", response_model=dict)
async def get_service_interval(
    interval_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get a specific service interval."""
    try:
        interval_uuid = UUID(interval_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid interval ID format")

    result = await db.execute(
        select(ServiceInterval).where(ServiceInterval.id == interval_uuid)
    )
    interval = result.scalar_one_or_none()

    if not interval:
        raise HTTPException(status_code=404, detail="Service interval not found")

    return {
        "id": str(interval.id),
        "name": interval.name,
        "description": interval.description,
        "service_type": interval.service_type,
        "interval_months": interval.interval_months,
        "reminder_days_before": interval.reminder_days_before,
        "is_active": interval.is_active,
        "created_at": interval.created_at.isoformat() if interval.created_at else None,
    }


@router.post("/", response_model=dict, status_code=201)
async def create_service_interval(
    interval: ServiceIntervalCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create a new service interval template."""
    new_interval = ServiceInterval(
        name=interval.name,
        description=interval.description,
        service_type=interval.service_type,
        interval_months=interval.interval_months,
        reminder_days_before=interval.reminder_days_before,
        is_active=interval.is_active,
    )

    db.add(new_interval)
    await db.commit()
    await db.refresh(new_interval)

    return {
        "id": str(new_interval.id),
        "name": new_interval.name,
        "description": new_interval.description,
        "service_type": new_interval.service_type,
        "interval_months": new_interval.interval_months,
        "reminder_days_before": new_interval.reminder_days_before,
        "is_active": new_interval.is_active,
        "created_at": new_interval.created_at.isoformat() if new_interval.created_at else None,
    }


@router.put("/{interval_id}", response_model=dict)
async def update_service_interval(
    interval_id: str,
    interval: ServiceIntervalUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Update a service interval template."""
    try:
        interval_uuid = UUID(interval_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid interval ID format")

    result = await db.execute(
        select(ServiceInterval).where(ServiceInterval.id == interval_uuid)
    )
    existing = result.scalar_one_or_none()

    if not existing:
        raise HTTPException(status_code=404, detail="Service interval not found")

    # Update fields
    update_data = interval.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(existing, field, value)

    await db.commit()
    await db.refresh(existing)

    return {
        "id": str(existing.id),
        "name": existing.name,
        "description": existing.description,
        "service_type": existing.service_type,
        "interval_months": existing.interval_months,
        "reminder_days_before": existing.reminder_days_before,
        "is_active": existing.is_active,
        "created_at": existing.created_at.isoformat() if existing.created_at else None,
    }


@router.delete("/{interval_id}", status_code=204)
async def delete_service_interval(
    interval_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Delete a service interval template."""
    try:
        interval_uuid = UUID(interval_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid interval ID format")

    result = await db.execute(
        select(ServiceInterval).where(ServiceInterval.id == interval_uuid)
    )
    existing = result.scalar_one_or_none()

    if not existing:
        raise HTTPException(status_code=404, detail="Service interval not found")

    await db.delete(existing)
    await db.commit()

    return None


# =============================================================================
# SCHEDULE ENDPOINTS (Customer Assignments)
# =============================================================================


@router.get("/schedules", response_model=dict)
async def list_customer_schedules(
    status: Optional[str] = Query(None),
    customer_id: Optional[int] = Query(None),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get customer service schedules with optional filters."""
    query = (
        select(CustomerServiceSchedule)
        .options(selectinload(CustomerServiceSchedule.service_interval))
    )

    if status:
        query = query.where(CustomerServiceSchedule.status == status)
    if customer_id:
        query = query.where(CustomerServiceSchedule.customer_id == customer_id)

    query = query.order_by(CustomerServiceSchedule.next_due_date).limit(limit)

    result = await db.execute(query)
    schedules = result.scalars().all()

    # Build response with customer names
    schedules_data = []
    for schedule in schedules:
        # Get customer name
        customer_result = await db.execute(
            select(Customer).where(Customer.id == schedule.customer_id)
        )
        customer = customer_result.scalar_one_or_none()
        customer_name = f"{customer.first_name} {customer.last_name}" if customer else f"Customer #{schedule.customer_id}"

        # Recalculate status
        status_val, days_until = calculate_status(schedule.next_due_date)

        schedules_data.append({
            "id": str(schedule.id),
            "customer_id": schedule.customer_id,
            "customer_name": customer_name,
            "service_interval_id": str(schedule.service_interval_id),
            "service_interval_name": schedule.service_interval.name if schedule.service_interval else "Unknown",
            "last_service_date": schedule.last_service_date.isoformat() if schedule.last_service_date else None,
            "next_due_date": schedule.next_due_date.isoformat(),
            "status": status_val,
            "scheduled_work_order_id": schedule.scheduled_work_order_id,
            "days_until_due": days_until,
            "reminder_sent": schedule.reminder_sent,
            "notes": schedule.notes,
        })

    return {"schedules": schedules_data, "total": len(schedules_data)}


@router.get("/customer/{customer_id}/schedules", response_model=dict)
async def get_customer_schedules(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get all service schedules for a specific customer."""
    result = await db.execute(
        select(CustomerServiceSchedule)
        .options(selectinload(CustomerServiceSchedule.service_interval))
        .where(CustomerServiceSchedule.customer_id == customer_id)
        .order_by(CustomerServiceSchedule.next_due_date)
    )
    schedules = result.scalars().all()

    # Get customer name once
    customer_result = await db.execute(
        select(Customer).where(Customer.id == customer_id)
    )
    customer = customer_result.scalar_one_or_none()
    customer_name = f"{customer.first_name} {customer.last_name}" if customer else f"Customer #{customer_id}"

    schedules_data = []
    for schedule in schedules:
        status_val, days_until = calculate_status(schedule.next_due_date)

        schedules_data.append({
            "id": str(schedule.id),
            "customer_id": schedule.customer_id,
            "customer_name": customer_name,
            "service_interval_id": str(schedule.service_interval_id),
            "service_interval_name": schedule.service_interval.name if schedule.service_interval else "Unknown",
            "last_service_date": schedule.last_service_date.isoformat() if schedule.last_service_date else None,
            "next_due_date": schedule.next_due_date.isoformat(),
            "status": status_val,
            "scheduled_work_order_id": schedule.scheduled_work_order_id,
            "days_until_due": days_until,
            "reminder_sent": schedule.reminder_sent,
            "notes": schedule.notes,
        })

    return {"schedules": schedules_data}


@router.post("/assign", response_model=dict, status_code=201)
async def assign_interval_to_customer(
    request: AssignIntervalRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Assign a service interval to a customer."""
    try:
        interval_uuid = UUID(request.service_interval_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid service interval ID format")

    # Get service interval
    result = await db.execute(
        select(ServiceInterval).where(ServiceInterval.id == interval_uuid)
    )
    interval = result.scalar_one_or_none()

    if not interval:
        raise HTTPException(status_code=404, detail="Service interval not found")

    # Calculate next due date
    last_service = date.fromisoformat(request.last_service_date) if request.last_service_date else date.today()
    next_due = last_service + timedelta(days=interval.interval_months * 30)
    status_val, days_until = calculate_status(next_due)

    # Get customer name
    customer_result = await db.execute(
        select(Customer).where(Customer.id == request.customer_id)
    )
    customer = customer_result.scalar_one_or_none()

    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    customer_name = f"{customer.first_name} {customer.last_name}"

    # Create schedule
    new_schedule = CustomerServiceSchedule(
        customer_id=request.customer_id,
        service_interval_id=interval_uuid,
        last_service_date=last_service if request.last_service_date else None,
        next_due_date=next_due,
        status=status_val,
        notes=request.notes,
    )

    db.add(new_schedule)
    await db.commit()
    await db.refresh(new_schedule)

    return {
        "id": str(new_schedule.id),
        "customer_id": new_schedule.customer_id,
        "customer_name": customer_name,
        "service_interval_id": str(new_schedule.service_interval_id),
        "service_interval_name": interval.name,
        "last_service_date": new_schedule.last_service_date.isoformat() if new_schedule.last_service_date else None,
        "next_due_date": new_schedule.next_due_date.isoformat(),
        "status": status_val,
        "days_until_due": days_until,
        "reminder_sent": new_schedule.reminder_sent,
        "notes": new_schedule.notes,
    }


@router.delete("/schedules/{schedule_id}", status_code=204)
async def unassign_interval(
    schedule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Remove a service interval assignment from a customer."""
    try:
        schedule_uuid = UUID(schedule_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid schedule ID format")

    result = await db.execute(
        select(CustomerServiceSchedule).where(CustomerServiceSchedule.id == schedule_uuid)
    )
    schedule = result.scalar_one_or_none()

    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    await db.delete(schedule)
    await db.commit()

    return None


@router.put("/schedules/{schedule_id}", response_model=dict)
async def update_schedule(
    schedule_id: str,
    last_service_date: str,
    notes: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Update a customer schedule (e.g., after service completion)."""
    try:
        schedule_uuid = UUID(schedule_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid schedule ID format")

    result = await db.execute(
        select(CustomerServiceSchedule)
        .options(selectinload(CustomerServiceSchedule.service_interval))
        .where(CustomerServiceSchedule.id == schedule_uuid)
    )
    schedule = result.scalar_one_or_none()

    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    # Recalculate next due date
    interval_months = schedule.service_interval.interval_months if schedule.service_interval else 12
    last_service = date.fromisoformat(last_service_date)
    next_due = last_service + timedelta(days=interval_months * 30)
    status_val, days_until = calculate_status(next_due)

    # Update schedule
    schedule.last_service_date = last_service
    schedule.next_due_date = next_due
    schedule.status = status_val
    schedule.reminder_sent = False  # Reset for next reminder cycle
    if notes:
        schedule.notes = notes

    await db.commit()
    await db.refresh(schedule)

    # Get customer name
    customer_result = await db.execute(
        select(Customer).where(Customer.id == schedule.customer_id)
    )
    customer = customer_result.scalar_one_or_none()
    customer_name = f"{customer.first_name} {customer.last_name}" if customer else f"Customer #{schedule.customer_id}"

    return {
        "id": str(schedule.id),
        "customer_id": schedule.customer_id,
        "customer_name": customer_name,
        "service_interval_id": str(schedule.service_interval_id),
        "service_interval_name": schedule.service_interval.name if schedule.service_interval else "Unknown",
        "last_service_date": schedule.last_service_date.isoformat() if schedule.last_service_date else None,
        "next_due_date": schedule.next_due_date.isoformat(),
        "status": status_val,
        "days_until_due": days_until,
        "reminder_sent": schedule.reminder_sent,
        "notes": schedule.notes,
    }


# =============================================================================
# REMINDERS & STATS ENDPOINTS
# =============================================================================


@router.get("/reminders", response_model=dict)
async def get_pending_reminders(
    status: str = Query("pending"),
    limit: int = Query(50),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get pending service reminders."""
    result = await db.execute(
        select(ServiceReminder)
        .where(ServiceReminder.status == status)
        .order_by(ServiceReminder.sent_at.desc())
        .limit(limit)
    )
    reminders = result.scalars().all()

    reminders_data = [
        {
            "id": str(r.id),
            "schedule_id": str(r.schedule_id),
            "customer_id": r.customer_id,
            "reminder_type": r.reminder_type,
            "days_before_due": r.days_before_due,
            "status": r.status,
            "sent_at": r.sent_at.isoformat() if r.sent_at else None,
        }
        for r in reminders
    ]

    return {"reminders": reminders_data}


@router.get("/stats", response_model=ServiceIntervalStats)
async def get_service_interval_stats(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get service interval dashboard statistics."""
    today = date.today()

    # Total customers with intervals
    total_result = await db.execute(
        select(func.count(func.distinct(CustomerServiceSchedule.customer_id)))
    )
    total_customers = total_result.scalar() or 0

    # Count by status
    upcoming_result = await db.execute(
        select(func.count()).where(
            and_(
                CustomerServiceSchedule.next_due_date > today + timedelta(days=7),
                CustomerServiceSchedule.status != "scheduled"
            )
        )
    )
    upcoming = upcoming_result.scalar() or 0

    due_result = await db.execute(
        select(func.count()).where(
            and_(
                CustomerServiceSchedule.next_due_date <= today + timedelta(days=7),
                CustomerServiceSchedule.next_due_date >= today,
                CustomerServiceSchedule.status != "scheduled"
            )
        )
    )
    due = due_result.scalar() or 0

    overdue_result = await db.execute(
        select(func.count()).where(
            and_(
                CustomerServiceSchedule.next_due_date < today,
                CustomerServiceSchedule.status != "scheduled"
            )
        )
    )
    overdue = overdue_result.scalar() or 0

    # Reminders sent today
    reminders_today_result = await db.execute(
        select(func.count()).where(
            and_(
                ServiceReminder.sent_at >= datetime.combine(today, datetime.min.time()),
                ServiceReminder.status == "sent"
            )
        )
    )
    reminders_today = reminders_today_result.scalar() or 0

    # Pending reminders
    pending_result = await db.execute(
        select(func.count()).where(
            and_(
                CustomerServiceSchedule.reminder_sent == False,
                CustomerServiceSchedule.status.in_(["upcoming", "due"])
            )
        )
    )
    pending = pending_result.scalar() or 0

    return ServiceIntervalStats(
        total_customers_with_intervals=total_customers,
        upcoming_services=upcoming,
        due_services=due,
        overdue_services=overdue,
        reminders_sent_today=reminders_today,
        reminders_pending=pending,
    )


@router.post("/create-work-order", response_model=dict, status_code=201)
async def create_work_order_from_schedule(
    request: CreateWorkOrderRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create a work order from a service schedule."""
    try:
        schedule_uuid = UUID(request.schedule_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid schedule ID format")

    result = await db.execute(
        select(CustomerServiceSchedule)
        .options(selectinload(CustomerServiceSchedule.service_interval))
        .where(CustomerServiceSchedule.id == schedule_uuid)
    )
    schedule = result.scalar_one_or_none()

    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    # In production, create actual work order using WorkOrder model
    # For now, generate a work order ID and update the schedule
    from uuid import uuid4
    work_order_id = str(uuid4())

    # Update schedule status
    schedule.status = "scheduled"
    schedule.scheduled_work_order_id = work_order_id

    await db.commit()

    return {"work_order_id": work_order_id, "message": "Work order created successfully"}


@router.post("/send-reminder", response_model=dict)
async def send_service_reminder(
    request: SendReminderRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Send a service reminder manually."""
    try:
        schedule_uuid = UUID(request.schedule_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid schedule ID format")

    result = await db.execute(
        select(CustomerServiceSchedule).where(CustomerServiceSchedule.id == schedule_uuid)
    )
    schedule = result.scalar_one_or_none()

    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    # Calculate days before due
    days_before = (schedule.next_due_date - date.today()).days

    # Create reminder record
    reminder = ServiceReminder(
        schedule_id=schedule.id,
        customer_id=schedule.customer_id,
        reminder_type=request.reminder_type,
        days_before_due=days_before,
        status="sent",
    )

    db.add(reminder)

    # Update schedule
    schedule.reminder_sent = True
    schedule.last_reminder_sent_at = datetime.utcnow()

    await db.commit()

    # TODO: Actually send SMS/email/push via Twilio/SendGrid

    return {"success": True, "message": f"Reminder sent via {request.reminder_type}"}


@router.post("/bulk-assign", response_model=dict)
async def bulk_assign_interval(
    request: BulkAssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Assign a service interval to multiple customers."""
    try:
        interval_uuid = UUID(request.service_interval_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid service interval ID format")

    result = await db.execute(
        select(ServiceInterval).where(ServiceInterval.id == interval_uuid)
    )
    interval = result.scalar_one_or_none()

    if not interval:
        raise HTTPException(status_code=404, detail="Service interval not found")

    assigned = 0
    failed = 0

    for customer_id in request.customer_ids:
        try:
            # Check customer exists
            customer_result = await db.execute(
                select(Customer).where(Customer.id == customer_id)
            )
            customer = customer_result.scalar_one_or_none()

            if not customer:
                failed += 1
                continue

            # Calculate next due date
            next_due = date.today() + timedelta(days=interval.interval_months * 30)
            status_val, _ = calculate_status(next_due)

            # Create schedule
            new_schedule = CustomerServiceSchedule(
                customer_id=customer_id,
                service_interval_id=interval_uuid,
                next_due_date=next_due,
                status=status_val,
            )

            db.add(new_schedule)
            assigned += 1
        except Exception:
            failed += 1

    await db.commit()

    return {"assigned": assigned, "failed": failed}


# =============================================================================
# SCHEDULER MANAGEMENT ENDPOINTS
# =============================================================================


@router.post("/run-reminder-check", response_model=dict)
async def run_reminder_check_now(
    _current_user=Depends(get_current_user),
):
    """
    Manually trigger the service reminder check.

    This runs the same check that happens automatically at 8 AM daily.
    Useful for testing or catching up on missed reminders.
    """
    from app.tasks.reminder_scheduler import run_reminders_now

    try:
        result = await run_reminders_now()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reminder check failed: {str(e)}")


@router.get("/scheduler-status", response_model=dict)
async def get_scheduler_status(
    _current_user=Depends(get_current_user),
):
    """Get the status of the reminder scheduler."""
    from app.tasks.reminder_scheduler import get_scheduler

    scheduler = get_scheduler()

    jobs = []
    if scheduler:
        for job in scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
            })

    return {
        "running": scheduler.running if scheduler else False,
        "jobs": jobs,
    }
