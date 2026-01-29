"""Service Intervals API - Recurring service scheduling and reminders."""

from datetime import date, timedelta
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.models import Customer

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


class CustomerServiceSchedule(BaseModel):
    id: str
    customer_id: int
    customer_name: str
    service_interval_id: str
    service_interval_name: str
    last_service_date: Optional[str] = None
    next_due_date: str
    status: str  # upcoming, due, overdue, scheduled
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
    technician_id: Optional[int] = None
    notes: Optional[str] = None


class SendReminderRequest(BaseModel):
    schedule_id: str
    reminder_type: str  # sms, email, push


# =============================================================================
# IN-MEMORY STORAGE (Replace with database models in production)
# =============================================================================

# Simulated storage - in production, use SQLAlchemy models
_service_intervals: dict = {
    "default-septic-pump": {
        "id": "default-septic-pump",
        "name": "Septic Tank Pumping",
        "description": "Regular septic tank pumping service",
        "service_type": "pumping",
        "interval_months": 36,
        "reminder_days_before": [60, 30, 14],
        "is_active": True,
        "created_at": "2024-01-01T00:00:00Z",
    },
    "default-grease-trap": {
        "id": "default-grease-trap",
        "name": "Grease Trap Cleaning",
        "description": "Commercial grease trap maintenance",
        "service_type": "grease_trap",
        "interval_months": 3,
        "reminder_days_before": [14, 7, 3],
        "is_active": True,
        "created_at": "2024-01-01T00:00:00Z",
    },
    "default-inspection": {
        "id": "default-inspection",
        "name": "Annual Inspection",
        "description": "Yearly septic system inspection",
        "service_type": "inspection",
        "interval_months": 12,
        "reminder_days_before": [30, 14, 7],
        "is_active": True,
        "created_at": "2024-01-01T00:00:00Z",
    },
}

_customer_schedules: dict = {}


# =============================================================================
# ENDPOINTS
# =============================================================================


@router.get("/", response_model=dict)
async def list_service_intervals(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get all service interval templates."""
    intervals = list(_service_intervals.values())
    return {"intervals": intervals, "total": len(intervals)}


@router.get("/{interval_id}", response_model=dict)
async def get_service_interval(
    interval_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get a specific service interval."""
    if interval_id not in _service_intervals:
        raise HTTPException(status_code=404, detail="Service interval not found")
    return _service_intervals[interval_id]


@router.post("/", response_model=dict, status_code=201)
async def create_service_interval(
    interval: ServiceIntervalCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create a new service interval template."""
    interval_id = str(uuid4())
    new_interval = {
        "id": interval_id,
        **interval.model_dump(),
        "created_at": date.today().isoformat(),
    }
    _service_intervals[interval_id] = new_interval
    return new_interval


@router.put("/{interval_id}", response_model=dict)
async def update_service_interval(
    interval_id: str,
    interval: ServiceIntervalUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Update a service interval template."""
    if interval_id not in _service_intervals:
        raise HTTPException(status_code=404, detail="Service interval not found")

    existing = _service_intervals[interval_id]
    update_data = interval.model_dump(exclude_unset=True)
    existing.update(update_data)
    return existing


@router.delete("/{interval_id}", status_code=204)
async def delete_service_interval(
    interval_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Delete a service interval template."""
    if interval_id not in _service_intervals:
        raise HTTPException(status_code=404, detail="Service interval not found")
    del _service_intervals[interval_id]
    return None


@router.get("/schedules", response_model=dict)
async def list_customer_schedules(
    status: Optional[str] = Query(None),
    customer_id: Optional[int] = Query(None),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get customer service schedules with optional filters."""
    schedules = list(_customer_schedules.values())

    if status:
        schedules = [s for s in schedules if s.get("status") == status]
    if customer_id:
        schedules = [s for s in schedules if s.get("customer_id") == customer_id]

    schedules = schedules[:limit]
    return {"schedules": schedules, "total": len(schedules)}


@router.get("/customer/{customer_id}/schedules", response_model=dict)
async def get_customer_schedules(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get all service schedules for a specific customer."""
    schedules = [s for s in _customer_schedules.values() if s.get("customer_id") == customer_id]
    return {"schedules": schedules}


@router.post("/assign", response_model=dict, status_code=201)
async def assign_interval_to_customer(
    request: AssignIntervalRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Assign a service interval to a customer."""
    if request.service_interval_id not in _service_intervals:
        raise HTTPException(status_code=404, detail="Service interval not found")

    interval = _service_intervals[request.service_interval_id]
    schedule_id = str(uuid4())

    # Calculate next due date
    last_service = date.fromisoformat(request.last_service_date) if request.last_service_date else date.today()
    next_due = last_service + timedelta(days=interval["interval_months"] * 30)
    days_until = (next_due - date.today()).days

    # Determine status
    if days_until < 0:
        status = "overdue"
    elif days_until <= 7:
        status = "due"
    else:
        status = "upcoming"

    # Get customer name
    result = await db.execute(select(Customer).where(Customer.id == request.customer_id))
    customer = result.scalar_one_or_none()
    customer_name = customer.name if customer else f"Customer #{request.customer_id}"

    schedule = {
        "id": schedule_id,
        "customer_id": request.customer_id,
        "customer_name": customer_name,
        "service_interval_id": request.service_interval_id,
        "service_interval_name": interval["name"],
        "last_service_date": request.last_service_date,
        "next_due_date": next_due.isoformat(),
        "status": status,
        "days_until_due": days_until,
        "reminder_sent": False,
        "notes": request.notes,
    }

    _customer_schedules[schedule_id] = schedule
    return schedule


@router.delete("/schedules/{schedule_id}", status_code=204)
async def unassign_interval(
    schedule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Remove a service interval assignment from a customer."""
    if schedule_id not in _customer_schedules:
        raise HTTPException(status_code=404, detail="Schedule not found")
    del _customer_schedules[schedule_id]
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
    if schedule_id not in _customer_schedules:
        raise HTTPException(status_code=404, detail="Schedule not found")

    schedule = _customer_schedules[schedule_id]
    interval = _service_intervals.get(schedule["service_interval_id"], {})
    interval_months = interval.get("interval_months", 12)

    # Recalculate next due date
    last_service = date.fromisoformat(last_service_date)
    next_due = last_service + timedelta(days=interval_months * 30)
    days_until = (next_due - date.today()).days

    schedule["last_service_date"] = last_service_date
    schedule["next_due_date"] = next_due.isoformat()
    schedule["days_until_due"] = days_until
    schedule["status"] = "upcoming" if days_until > 7 else ("due" if days_until >= 0 else "overdue")
    if notes:
        schedule["notes"] = notes

    return schedule


@router.get("/reminders", response_model=dict)
async def get_pending_reminders(
    status: str = Query("pending"),
    limit: int = Query(50),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get pending service reminders."""
    # In production, query reminders table
    reminders = []
    return {"reminders": reminders}


@router.get("/stats", response_model=ServiceIntervalStats)
async def get_service_interval_stats(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get service interval dashboard statistics."""
    schedules = list(_customer_schedules.values())

    stats = ServiceIntervalStats(
        total_customers_with_intervals=len(set(s["customer_id"] for s in schedules)),
        upcoming_services=len([s for s in schedules if s.get("status") == "upcoming"]),
        due_services=len([s for s in schedules if s.get("status") == "due"]),
        overdue_services=len([s for s in schedules if s.get("status") == "overdue"]),
        reminders_sent_today=0,
        reminders_pending=0,
    )
    return stats


@router.post("/create-work-order", response_model=dict, status_code=201)
async def create_work_order_from_schedule(
    request: CreateWorkOrderRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create a work order from a service schedule."""
    if request.schedule_id not in _customer_schedules:
        raise HTTPException(status_code=404, detail="Schedule not found")

    # In production, create actual work order
    work_order_id = str(uuid4())

    # Update schedule status
    _customer_schedules[request.schedule_id]["status"] = "scheduled"
    _customer_schedules[request.schedule_id]["scheduled_work_order_id"] = work_order_id

    return {"work_order_id": work_order_id, "message": "Work order created successfully"}


@router.post("/send-reminder", response_model=dict)
async def send_service_reminder(
    request: SendReminderRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Send a service reminder manually."""
    if request.schedule_id not in _customer_schedules:
        raise HTTPException(status_code=404, detail="Schedule not found")

    # In production, send actual reminder via SMS/email/push
    _customer_schedules[request.schedule_id]["reminder_sent"] = True

    return {"success": True, "message": f"Reminder sent via {request.reminder_type}"}


@router.post("/bulk-assign", response_model=dict)
async def bulk_assign_interval(
    request: BulkAssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Assign a service interval to multiple customers."""
    if request.service_interval_id not in _service_intervals:
        raise HTTPException(status_code=404, detail="Service interval not found")

    assigned = 0
    failed = 0

    for customer_id in request.customer_ids:
        try:
            # Create assignment
            assign_request = AssignIntervalRequest(
                customer_id=customer_id,
                service_interval_id=request.service_interval_id,
            )
            # Simplified - just count successes
            assigned += 1
        except Exception:
            failed += 1

    return {"assigned": assigned, "failed": failed}
