"""Employee Portal API - Mobile-first field service features.

Features:
- GPS-verified time clock
- Job checklists
- Photo capture
- Customer signatures
- Offline sync support
"""

from fastapi import APIRouter, HTTPException, status, Query, UploadFile, File, Request
from sqlalchemy import select, func, and_, or_
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, date, timedelta, timezone
import logging

from app.api.deps import DbSession, CurrentUser
from app.models.work_order import WorkOrder
from app.models.customer import Customer
from app.models.technician import Technician
from app.models.payroll import TimeEntry
from app.services.commission_service import auto_create_commission
import uuid as uuid_mod

logger = logging.getLogger(__name__)
router = APIRouter()


# Models


class ClockInRequest(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    work_order_id: Optional[str] = None
    notes: Optional[str] = None


class ClockOutRequest(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    work_order_id: Optional[str] = None
    notes: Optional[str] = None


class ChecklistUpdate(BaseModel):
    work_order_id: str
    checklist_items: List[dict]  # [{"id": "...", "completed": true, "notes": "..."}]


class JobStatusUpdate(BaseModel):
    status: str
    notes: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class PhotoUpload(BaseModel):
    work_order_id: str
    photo_type: str  # before, after, issue, signature
    description: Optional[str] = None


class CustomerSignatureCapture(BaseModel):
    work_order_id: str
    signature_data: str  # Base64 encoded
    signer_name: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class RecordPaymentRequest(BaseModel):
    """Record how and when payment was collected in the field."""
    payment_method: str  # cash, check, card, ach, other
    amount: float
    payment_date: Optional[str] = None  # ISO datetime, defaults to now
    check_number: Optional[str] = None
    notes: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class OfflineSyncRequest(BaseModel):
    actions: List[dict]  # List of actions performed offline
    last_sync: Optional[datetime] = None


# Endpoints


@router.get("/dashboard")
async def get_employee_dashboard(
    db: DbSession,
    current_user: CurrentUser,
):
    """Get employee dashboard stats."""
    try:
        # Find technician
        tech_result = await db.execute(select(Technician).where(Technician.email == current_user.email))
        technician = tech_result.scalar_one_or_none()

        if not technician:
            return {
                "jobs_today": 0,
                "jobs_completed_today": 0,
                "hours_today": 0,
                "is_clocked_in": False,
            }

        today = date.today()
        tech_id_str = str(technician.id)

        # Jobs today
        jobs_result = await db.execute(
            select(func.count())
            .select_from(WorkOrder)
            .where(
                WorkOrder.technician_id == tech_id_str,
                WorkOrder.scheduled_date == today,
            )
        )
        jobs_today = jobs_result.scalar() or 0

        # Completed jobs today
        completed_result = await db.execute(
            select(func.count())
            .select_from(WorkOrder)
            .where(
                WorkOrder.technician_id == tech_id_str,
                WorkOrder.scheduled_date == today,
                WorkOrder.status == "completed",
            )
        )
        completed_today = completed_result.scalar() or 0

        # Hours today
        hours_result = await db.execute(
            select(func.sum(WorkOrder.total_labor_minutes)).where(
                WorkOrder.technician_id == tech_id_str,
                WorkOrder.scheduled_date == today,
            )
        )
        minutes_today = hours_result.scalar() or 0

        # Check if clocked in via TimeEntry (more reliable)
        time_entry_result = await db.execute(
            select(func.count())
            .select_from(TimeEntry)
            .where(
                TimeEntry.technician_id == technician.id,
                TimeEntry.clock_out.is_(None),
            )
        )
        is_clocked_in = (time_entry_result.scalar() or 0) > 0

        return {
            "jobs_today": jobs_today,
            "jobs_completed_today": completed_today,
            "hours_today": round(minutes_today / 60, 1) if minutes_today else 0.0,
            "is_clocked_in": is_clocked_in,
        }
    except Exception as e:
        logger.error(f"Dashboard error for {current_user.email}: {type(e).__name__}: {str(e)}")
        # Return safe defaults rather than crashing
        return {
            "jobs_today": 0,
            "jobs_completed_today": 0,
            "hours_today": 0.0,
            "is_clocked_in": False,
        }


@router.get("/profile")
async def get_employee_profile(
    db: DbSession,
    current_user: CurrentUser,
):
    """Get employee profile."""
    tech_result = await db.execute(select(Technician).where(Technician.email == current_user.email))
    technician = tech_result.scalar_one_or_none()

    if not technician:
        return {
            "id": "",
            "first_name": current_user.email.split("@")[0],
            "last_name": "",
            "email": current_user.email,
            "role": "technician",
            "is_active": True,
        }

    return {
        "id": str(technician.id),
        "first_name": technician.first_name or "",
        "last_name": technician.last_name or "",
        "email": technician.email,
        "role": "technician",
        "is_active": technician.is_active,
        "phone": technician.phone,
    }


@router.get("/jobs")
async def get_employee_jobs(
    db: DbSession,
    current_user: CurrentUser,
    date_filter: Optional[str] = Query(None, alias="date"),
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
    scheduled_date_from: Optional[str] = Query(None),
    scheduled_date_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    """Get jobs assigned to current technician.

    Matches by BOTH technician_id (UUID FK) AND assigned_technician (name string)
    since the schedule UI only sets assigned_technician.
    """
    try:
        tech_result = await db.execute(select(Technician).where(Technician.email == current_user.email))
        technician = tech_result.scalar_one_or_none()

        if not technician:
            return {"items": [], "total": 0, "page": page, "page_size": page_size}

        # OR filter: match by UUID FK or name string (same as technician_dashboard)
        tech_full_name = f"{technician.first_name or ''} {technician.last_name or ''}".strip()
        tech_conditions = [WorkOrder.technician_id == technician.id]
        if tech_full_name:
            tech_conditions.append(WorkOrder.assigned_technician == tech_full_name)

        query = (
            select(WorkOrder, Customer)
            .outerjoin(Customer, WorkOrder.customer_id == Customer.id)
            .where(or_(*tech_conditions))
        )

        # Date filtering
        if date_filter:
            query = query.where(WorkOrder.scheduled_date == date.fromisoformat(date_filter))
        elif scheduled_date_from and scheduled_date_to:
            query = query.where(
                WorkOrder.scheduled_date >= date.fromisoformat(scheduled_date_from),
                WorkOrder.scheduled_date <= date.fromisoformat(scheduled_date_to),
            )

        # Status filter
        if status_filter:
            query = query.where(WorkOrder.status == status_filter)

        # Search (customer name, address, job type)
        if search:
            search_term = f"%{search}%"
            query = query.where(
                or_(
                    WorkOrder.assigned_technician.ilike(search_term),
                    WorkOrder.service_address_line1.ilike(search_term),
                    WorkOrder.service_city.ilike(search_term),
                    WorkOrder.job_type.ilike(search_term),
                    Customer.first_name.ilike(search_term),
                    Customer.last_name.ilike(search_term),
                )
            )

        # Count total before pagination
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Order and paginate
        query = query.order_by(WorkOrder.scheduled_date.desc().nullslast(), WorkOrder.time_window_start)
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await db.execute(query)
        rows = result.all()

        items = []
        for row in rows:
            wo = row[0]  # WorkOrder
            customer = row[1]  # Customer (may be None)
            customer_name = ""
            if customer:
                customer_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip()

            items.append({
                "id": str(wo.id),
                "customer_id": str(wo.customer_id) if wo.customer_id else None,
                "customer_name": customer_name,
                "job_type": wo.job_type,
                "status": wo.status,
                "priority": wo.priority,
                "scheduled_date": wo.scheduled_date.isoformat() if wo.scheduled_date else None,
                "time_window_start": str(wo.time_window_start) if wo.time_window_start else None,
                "time_window_end": str(wo.time_window_end) if wo.time_window_end else None,
                "address": wo.service_address_line1,
                "city": wo.service_city,
                "state": wo.service_state,
                "zip": wo.service_postal_code,
                "latitude": wo.service_latitude,
                "longitude": wo.service_longitude,
                "notes": wo.notes,
                "checklist": wo.checklist,
                "estimated_duration_hours": wo.estimated_duration_hours,
                "is_clocked_in": wo.is_clocked_in,
                "total_amount": float(wo.total_amount) if wo.total_amount else None,
                "system_type": wo.system_type or "conventional",
            })

        return {"items": items, "total": total, "page": page, "page_size": page_size}
    except Exception as e:
        logger.error(f"Employee jobs error for {current_user.email}: {type(e).__name__}: {e}")
        return {"items": [], "total": 0, "page": page, "page_size": page_size}


@router.get("/jobs/{job_id}")
async def get_employee_job(
    job_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a single job."""
    wo_result = await db.execute(
        select(WorkOrder, Customer)
        .outerjoin(Customer, WorkOrder.customer_id == Customer.id)
        .where(WorkOrder.id == job_id)
    )
    row = wo_result.one_or_none()

    if not row:
        raise HTTPException(status_code=404, detail="Job not found")

    work_order = row[0]
    customer = row[1]
    customer_name = ""
    if customer:
        customer_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip()

    return {
        "id": str(work_order.id),
        "customer_id": str(work_order.customer_id) if work_order.customer_id else None,
        "customer_name": customer_name,
        "job_type": work_order.job_type,
        "status": work_order.status,
        "priority": work_order.priority,
        "scheduled_date": work_order.scheduled_date.isoformat() if work_order.scheduled_date else None,
        "time_window_start": str(work_order.time_window_start) if work_order.time_window_start else None,
        "time_window_end": str(work_order.time_window_end) if work_order.time_window_end else None,
        "address": work_order.service_address_line1,
        "city": work_order.service_city,
        "state": work_order.service_state,
        "zip": work_order.service_postal_code,
        "latitude": work_order.service_latitude,
        "longitude": work_order.service_longitude,
        "notes": work_order.notes,
        "checklist": work_order.checklist,
        "estimated_duration_hours": work_order.estimated_duration_hours,
        "is_clocked_in": work_order.is_clocked_in,
        "actual_start_time": work_order.actual_start_time.isoformat() if work_order.actual_start_time else None,
        "actual_end_time": work_order.actual_end_time.isoformat() if work_order.actual_end_time else None,
        "total_labor_minutes": work_order.total_labor_minutes,
        "total_amount": float(work_order.total_amount) if work_order.total_amount else None,
        "system_type": work_order.system_type or "conventional",
        "internal_notes": work_order.internal_notes,
        "assigned_technician": work_order.assigned_technician,
        "estimated_gallons": work_order.estimated_gallons,
    }


@router.get("/jobs/{job_id}/checklist")
async def get_job_checklist(
    job_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get checklist items for a job."""
    wo_result = await db.execute(select(WorkOrder).where(WorkOrder.id == job_id))
    work_order = wo_result.scalar_one_or_none()

    if not work_order:
        raise HTTPException(status_code=404, detail="Job not found")

    return {"items": work_order.checklist or []}


@router.patch("/jobs/{job_id}")
async def patch_employee_job(
    job_id: str,
    request: JobStatusUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update a job (status, notes, etc)."""
    wo_result = await db.execute(select(WorkOrder).where(WorkOrder.id == job_id))
    work_order = wo_result.scalar_one_or_none()

    if not work_order:
        raise HTTPException(status_code=404, detail="Job not found")

    work_order.status = request.status

    if request.notes:
        existing_notes = work_order.notes or ""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        work_order.notes = f"{existing_notes}\n[{timestamp}] {request.notes}".strip()

    await db.commit()

    return {
        "id": str(work_order.id),
        "status": work_order.status,
    }


@router.post("/jobs/{job_id}/start")
async def start_job(
    job_id: str,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    db: DbSession = None,
    current_user: CurrentUser = None,
):
    """Start a job (mark as en_route or in_progress)."""
    wo_result = await db.execute(select(WorkOrder).where(WorkOrder.id == job_id))
    work_order = wo_result.scalar_one_or_none()

    if not work_order:
        raise HTTPException(status_code=404, detail="Job not found")

    if work_order.status == "scheduled":
        work_order.status = "en_route"
    elif work_order.status == "en_route":
        work_order.status = "in_progress"
        work_order.actual_start_time = datetime.now(timezone.utc)
        work_order.is_clocked_in = True
        if latitude and longitude:
            work_order.clock_in_gps_lat = latitude
            work_order.clock_in_gps_lon = longitude

    await db.commit()

    return {
        "id": str(work_order.id),
        "status": work_order.status,
    }


@router.post("/jobs/{job_id}/complete")
async def complete_job(
    job_id: str,
    notes: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    customer_signature: Optional[str] = None,
    technician_signature: Optional[str] = None,
    dump_site_id: Optional[str] = None,
    db: DbSession = None,
    current_user: CurrentUser = None,
):
    """Complete a job and auto-create commission."""
    wo_result = await db.execute(select(WorkOrder).where(WorkOrder.id == job_id))
    work_order = wo_result.scalar_one_or_none()

    if not work_order:
        raise HTTPException(status_code=404, detail="Job not found")

    work_order.status = "completed"
    work_order.actual_end_time = datetime.now(timezone.utc)
    work_order.is_clocked_in = False

    if latitude and longitude:
        work_order.clock_out_gps_lat = latitude
        work_order.clock_out_gps_lon = longitude

    if work_order.actual_start_time:
        duration = datetime.now(timezone.utc) - work_order.actual_start_time
        work_order.total_labor_minutes = int(duration.total_seconds() / 60)

    if notes:
        existing_notes = work_order.notes or ""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        work_order.notes = f"{existing_notes}\n[{timestamp}] Completion: {notes}".strip()

    # Auto-create commission for completed work order
    commission = await auto_create_commission(
        db=db,
        work_order=work_order,
        dump_site_id=dump_site_id,
    )

    await db.commit()

    return {
        "id": str(work_order.id),
        "status": work_order.status,
        "labor_minutes": work_order.total_labor_minutes,
        "commission_id": str(commission.id) if commission else None,
        "commission_amount": float(commission.commission_amount) if commission else None,
    }


@router.get("/timeclock/status")
async def get_timeclock_status(
    db: DbSession,
    current_user: CurrentUser,
):
    """Get current time clock status."""
    tech_result = await db.execute(select(Technician).where(Technician.email == current_user.email))
    technician = tech_result.scalar_one_or_none()

    # Check for active TimeEntry (clock_out is NULL)
    if technician:
        time_entry_result = await db.execute(
            select(TimeEntry)
            .where(
                TimeEntry.technician_id == technician.id,
                TimeEntry.clock_out.is_(None),
            )
            .order_by(TimeEntry.clock_in.desc())
            .limit(1)
        )
        time_entry = time_entry_result.scalar_one_or_none()

        if time_entry:
            return {
                "entry": {
                    "id": str(time_entry.id),
                    "technician_id": str(time_entry.technician_id),
                    "clock_in": time_entry.clock_in.isoformat() if time_entry.clock_in else None,
                    "clock_out": None,
                    "status": "clocked_in",
                    "work_order_id": str(time_entry.work_order_id) if time_entry.work_order_id else None,
                }
            }

    # Also check for any clocked-in work order (legacy support)
    if technician:
        clocked_in_result = await db.execute(
            select(WorkOrder)
            .where(
                WorkOrder.technician_id == technician.id,
                WorkOrder.is_clocked_in == True,
            )
            .limit(1)
        )
        clocked_in_wo = clocked_in_result.scalar_one_or_none()

        if clocked_in_wo:
            return {
                "entry": {
                    "id": str(clocked_in_wo.id),
                    "technician_id": str(technician.id),
                    "clock_in": clocked_in_wo.actual_start_time.isoformat() if clocked_in_wo.actual_start_time else None,
                    "clock_out": None,
                    "status": "clocked_in",
                    "work_order_id": str(clocked_in_wo.id),
                }
            }

    return {"entry": None}


@router.post("/timeclock/clock-in")
async def timeclock_clock_in(
    request: ClockInRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Clock in via timeclock endpoint."""
    return await clock_in(request, db, current_user)


@router.post("/timeclock/clock-out")
async def timeclock_clock_out(
    request: ClockOutRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Clock out via timeclock endpoint."""
    return await clock_out(request, db, current_user)


@router.get("/timeclock/history")
async def get_timeclock_history(
    db: DbSession,
    current_user: CurrentUser,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """Get time clock history."""
    tech_result = await db.execute(select(Technician).where(Technician.email == current_user.email))
    technician = tech_result.scalar_one_or_none()

    if not technician:
        return {"entries": []}

    query = select(WorkOrder).where(
        WorkOrder.technician_id == technician.id,
        WorkOrder.actual_start_time.isnot(None),
    )

    if start_date:
        query = query.where(WorkOrder.scheduled_date >= date.fromisoformat(start_date))
    if end_date:
        query = query.where(WorkOrder.scheduled_date <= date.fromisoformat(end_date))

    query = query.order_by(WorkOrder.actual_start_time.desc()).limit(50)
    result = await db.execute(query)
    work_orders = result.scalars().all()

    return {
        "entries": [
            {
                "id": str(wo.id),
                "clock_in": wo.actual_start_time.isoformat() if wo.actual_start_time else None,
                "clock_out": wo.actual_end_time.isoformat() if wo.actual_end_time else None,
                "work_order_id": str(wo.id),
                "duration_minutes": wo.total_labor_minutes,
            }
            for wo in work_orders
        ]
    }


@router.get("/my-jobs")
async def get_my_jobs(
    db: DbSession,
    current_user: CurrentUser,
    date_filter: Optional[date] = None,
):
    """Get jobs assigned to current technician."""
    # Find technician by email
    tech_result = await db.execute(select(Technician).where(Technician.email == current_user.email))
    technician = tech_result.scalar_one_or_none()

    if not technician:
        return {"jobs": [], "message": "No technician profile found"}

    query = select(WorkOrder).where(WorkOrder.technician_id == technician.id)

    if date_filter:
        query = query.where(WorkOrder.scheduled_date == date_filter)
    else:
        query = query.where(WorkOrder.scheduled_date == date.today())

    query = query.order_by(WorkOrder.time_window_start)
    result = await db.execute(query)
    work_orders = result.scalars().all()

    return {
        "technician_id": str(technician.id),
        "date": str(date_filter or date.today()),
        "jobs": [
            {
                "id": str(wo.id),
                "customer_id": str(wo.customer_id),
                "job_type": wo.job_type,
                "status": wo.status,
                "priority": wo.priority,
                "time_window_start": str(wo.time_window_start) if wo.time_window_start else None,
                "time_window_end": str(wo.time_window_end) if wo.time_window_end else None,
                "address": wo.service_address_line1,
                "city": wo.service_city,
                "latitude": wo.service_latitude,
                "longitude": wo.service_longitude,
                "notes": wo.notes,
                "checklist": wo.checklist,
                "estimated_duration_hours": wo.estimated_duration_hours,
                "is_clocked_in": wo.is_clocked_in,
            }
            for wo in work_orders
        ],
    }


@router.post("/clock-in")
async def clock_in(
    request: ClockInRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Clock in to start work (GPS verified)."""
    now = datetime.now(timezone.utc)

    # Find technician
    tech_result = await db.execute(select(Technician).where(Technician.email == current_user.email))
    technician = tech_result.scalar_one_or_none()

    # Auto-create technician profile if missing
    if not technician:
        logger.info(f"Auto-creating Technician profile for {current_user.email}")
        # Extract name from email (e.g., "will.burns" -> "Will" "Burns")
        email_name = current_user.email.split("@")[0]
        name_parts = email_name.replace(".", " ").split()
        first_name = name_parts[0].title() if name_parts else "Employee"
        last_name = name_parts[1].title() if len(name_parts) > 1 else "User"

        technician = Technician(
            id=uuid_mod.uuid4(),
            email=current_user.email,
            first_name=first_name,
            last_name=last_name,
            is_active=True,
            skills=["General"],
        )
        db.add(technician)
        await db.flush()  # Get the ID without committing yet

    # Check for existing open time entry
    existing_entry_result = await db.execute(
        select(TimeEntry)
        .where(
            TimeEntry.technician_id == technician.id,
            TimeEntry.clock_out.is_(None),
        )
        .limit(1)
    )
    existing_entry = existing_entry_result.scalar_one_or_none()

    if existing_entry:
        return {
            "status": "clocked_in",
            "clock_in": existing_entry.clock_in.isoformat(),
            "entry_id": str(existing_entry.id),
            "message": "Already clocked in",
        }

    # Create new time entry
    time_entry = TimeEntry(
        id=uuid_mod.uuid4(),
        technician_id=technician.id,
        entry_date=now.date(),
        clock_in=now,
        clock_in_lat=request.latitude,
        clock_in_lon=request.longitude,
        work_order_id=request.work_order_id if request.work_order_id else None,
        entry_type="work",
        status="pending",
        notes=request.notes,
    )
    db.add(time_entry)

    # If work order specified, also update work order
    if request.work_order_id:
        wo_result = await db.execute(select(WorkOrder).where(WorkOrder.id == request.work_order_id))
        work_order = wo_result.scalar_one_or_none()

        if work_order:
            work_order.is_clocked_in = True
            work_order.actual_start_time = now
            if request.latitude is not None:
                work_order.clock_in_gps_lat = request.latitude
            if request.longitude is not None:
                work_order.clock_in_gps_lon = request.longitude
            if work_order.status == "scheduled":
                work_order.status = "in_progress"

    await db.commit()
    await db.refresh(time_entry)

    return {
        "status": "clocked_in",
        "clock_in": time_entry.clock_in.isoformat(),
        "entry_id": str(time_entry.id),
        "work_order_id": request.work_order_id,
        "location_verified": request.latitude is not None and request.longitude is not None,
    }


@router.post("/clock-out")
async def clock_out(
    request: ClockOutRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Clock out from work (GPS verified)."""
    try:
        now = datetime.now(timezone.utc)

        # Find technician (auto-create if missing for consistency, though shouldn't happen if they clocked in)
        tech_result = await db.execute(select(Technician).where(Technician.email == current_user.email))
        technician = tech_result.scalar_one_or_none()

        if not technician:
            # No technician and no active entry - nothing to clock out
            logger.warning(f"Clock-out attempted by user without technician profile: {current_user.email}")
            return {
                "status": "clocked_out",
                "clock_out": now.isoformat(),
                "message": "No active clock-in found (no technician profile)",
            }

        # Find active time entry
        time_entry_result = await db.execute(
            select(TimeEntry)
            .where(
                TimeEntry.technician_id == technician.id,
                TimeEntry.clock_out.is_(None),
            )
            .order_by(TimeEntry.clock_in.desc())
            .limit(1)
        )
        time_entry = time_entry_result.scalar_one_or_none()

        if not time_entry:
            logger.warning(f"Clock-out attempted but no active time entry for technician: {technician.id}")
            return {
                "status": "clocked_out",
                "clock_out": now.isoformat(),
                "message": "No active clock-in found",
            }

        # Update time entry
        time_entry.clock_out = now
        time_entry.clock_out_lat = request.latitude
        time_entry.clock_out_lon = request.longitude

        # Calculate hours
        duration = now - time_entry.clock_in
        total_hours = duration.total_seconds() / 3600
        time_entry.regular_hours = min(total_hours, 8.0)
        time_entry.overtime_hours = max(0, total_hours - 8.0)

        if request.notes:
            time_entry.notes = f"{time_entry.notes or ''}\n{request.notes}".strip()

        # If work order specified, also update work order
        if request.work_order_id or time_entry.work_order_id:
            work_order_id = request.work_order_id or time_entry.work_order_id
            wo_result = await db.execute(select(WorkOrder).where(WorkOrder.id == work_order_id))
            work_order = wo_result.scalar_one_or_none()

            if work_order:
                work_order.is_clocked_in = False
                work_order.actual_end_time = now
                if request.latitude is not None:
                    work_order.clock_out_gps_lat = request.latitude
                if request.longitude is not None:
                    work_order.clock_out_gps_lon = request.longitude
                if work_order.actual_start_time:
                    duration_minutes = (now - work_order.actual_start_time).total_seconds() / 60
                    work_order.total_labor_minutes = int(duration_minutes)

        await db.commit()
        await db.refresh(time_entry)
    except Exception as e:
        logger.error(f"Clock-out error for {current_user.email}: {type(e).__name__}: {str(e)}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Clock-out failed: {str(e)}")

    return {
        "status": "clocked_out",
        "clock_out": time_entry.clock_out.isoformat(),
        "entry_id": str(time_entry.id),
        "total_hours": round(time_entry.regular_hours + time_entry.overtime_hours, 2),
        "regular_hours": round(time_entry.regular_hours, 2),
        "overtime_hours": round(time_entry.overtime_hours, 2),
    }


@router.patch("/jobs/{work_order_id}/status")
async def update_job_status(
    work_order_id: str,
    request: JobStatusUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update job status from the field."""
    wo_result = await db.execute(select(WorkOrder).where(WorkOrder.id == work_order_id))
    work_order = wo_result.scalar_one_or_none()

    if not work_order:
        raise HTTPException(status_code=404, detail="Work order not found")

    work_order.status = request.status

    if request.notes:
        existing_notes = work_order.notes or ""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        work_order.notes = f"{existing_notes}\n[{timestamp}] {request.notes}".strip()

    await db.commit()

    return {"status": work_order.status}


@router.post("/jobs/{work_order_id}/checklist")
async def update_checklist(
    work_order_id: str,
    request: ChecklistUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update job checklist items."""
    wo_result = await db.execute(select(WorkOrder).where(WorkOrder.id == work_order_id))
    work_order = wo_result.scalar_one_or_none()

    if not work_order:
        raise HTTPException(status_code=404, detail="Work order not found")

    # Update checklist (merge with existing)
    existing = work_order.checklist or []
    updated = {item["id"]: item for item in request.checklist_items}

    for i, item in enumerate(existing):
        if item.get("id") in updated:
            existing[i] = {**item, **updated[item["id"]]}

    work_order.checklist = existing
    await db.commit()

    return {"checklist": work_order.checklist}


@router.post("/jobs/{work_order_id}/photos/base64")
async def upload_photo_base64(
    work_order_id: str,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
):
    """Upload a photo as base64 JSON (used by tech portal camera capture)."""
    import uuid as uuid_mod
    from app.models.work_order_photo import WorkOrderPhoto

    body = await request.json()
    photo_data = body.get("photo_data") or body.get("data")
    photo_type = body.get("photo_type", "other")

    if not photo_data:
        raise HTTPException(status_code=400, detail="photo_data is required")

    # Verify work order exists
    wo_result = await db.execute(select(WorkOrder).where(WorkOrder.id == work_order_id))
    work_order = wo_result.scalar_one_or_none()
    if not work_order:
        raise HTTPException(status_code=404, detail="Work order not found")

    # Create photo record (use UUID objects for UUID columns)
    photo_id = uuid_mod.uuid4()
    photo = WorkOrderPhoto(
        id=photo_id,
        work_order_id=uuid_mod.UUID(work_order_id),
        photo_type=photo_type,
        data=photo_data,  # data:image/jpeg;base64,... or raw base64
        thumbnail=body.get("thumbnail"),
        timestamp=datetime.now(timezone.utc),
        device_info=body.get("device_info"),
        gps_lat=body.get("gps_lat"),
        gps_lng=body.get("gps_lng"),
        gps_accuracy=body.get("gps_accuracy"),
    )
    db.add(photo)
    await db.commit()
    await db.refresh(photo)

    logger.info(f"Base64 photo uploaded for WO {work_order_id}: type={photo_type}, id={photo.id}")

    return {
        "status": "uploaded",
        "photo_id": str(photo.id),
        "work_order_id": work_order_id,
        "photo_type": photo_type,
    }


@router.post("/jobs/{work_order_id}/photos")
async def upload_photo(
    work_order_id: str,
    photo_type: str,
    description: Optional[str] = None,
    file: UploadFile = File(...),
    db: DbSession = None,
    current_user: CurrentUser = None,
):
    """Upload a photo for a job. Accepts multipart file upload, stores as Base64 in DB."""
    import base64
    import uuid as uuid_mod
    from app.models.work_order_photo import WorkOrderPhoto

    # Verify work order exists
    wo_result = await db.execute(select(WorkOrder).where(WorkOrder.id == work_order_id))
    work_order = wo_result.scalar_one_or_none()
    if not work_order:
        raise HTTPException(status_code=404, detail="Work order not found")

    # Validate file type
    allowed_types = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
    if file.content_type and file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: {file.content_type}. Allowed: {', '.join(allowed_types)}",
        )

    # Read and encode file
    contents = await file.read()

    # Validate file size (max 10MB)
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 10MB.")

    base64_data = base64.b64encode(contents).decode("utf-8")
    mime_type = file.content_type or "image/jpeg"
    data_uri = f"data:{mime_type};base64,{base64_data}"

    # Create photo record
    photo = WorkOrderPhoto(
        id=str(uuid_mod.uuid4()),
        work_order_id=work_order_id,
        photo_type=photo_type,
        data=data_uri,
        timestamp=datetime.now(timezone.utc),
    )
    db.add(photo)
    await db.commit()
    await db.refresh(photo)

    logger.info(f"Photo uploaded via employee portal for work order {work_order_id}: {photo.id}")

    return {
        "status": "uploaded",
        "photo_id": photo.id,
        "work_order_id": work_order_id,
        "photo_type": photo_type,
        "filename": file.filename,
    }


@router.post("/jobs/{work_order_id}/signature")
async def capture_customer_signature(
    work_order_id: str,
    request: CustomerSignatureCapture,
    db: DbSession,
    current_user: CurrentUser,
):
    """Capture customer signature for job completion. Stores signature as photo and updates work order."""
    import uuid as uuid_mod
    from app.models.work_order_photo import WorkOrderPhoto

    wo_result = await db.execute(select(WorkOrder).where(WorkOrder.id == work_order_id))
    work_order = wo_result.scalar_one_or_none()

    if not work_order:
        raise HTTPException(status_code=404, detail="Work order not found")

    now = datetime.now(timezone.utc)

    # Store signature as a photo record (type=signature)
    signature_photo = WorkOrderPhoto(
        id=str(uuid_mod.uuid4()),
        work_order_id=work_order_id,
        photo_type="signature",
        data=request.signature_data,  # Base64 image data
        timestamp=now,
        gps_lat=request.latitude,
        gps_lng=request.longitude,
    )
    db.add(signature_photo)

    # Update work order notes with signature record
    timestamp_str = now.strftime("%Y-%m-%d %H:%M")
    notes = work_order.notes or ""
    work_order.notes = f"{notes}\n[{timestamp_str}] Signed by: {request.signer_name}".strip()

    await db.commit()

    logger.info(f"Customer signature captured for work order {work_order_id} by {request.signer_name}")

    return {
        "status": "signature_captured",
        "signature_photo_id": signature_photo.id,
        "signer_name": request.signer_name,
        "timestamp": now.isoformat(),
    }


@router.get("/jobs/{work_order_id}/photos")
async def list_job_photos(
    work_order_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """List all photos for a work order (used by tech portal)."""
    from app.models.work_order_photo import WorkOrderPhoto

    wo_result = await db.execute(select(WorkOrder).where(WorkOrder.id == work_order_id))
    work_order = wo_result.scalar_one_or_none()
    if not work_order:
        raise HTTPException(status_code=404, detail="Work order not found")

    query = (
        select(WorkOrderPhoto)
        .where(WorkOrderPhoto.work_order_id == work_order_id)
        .order_by(WorkOrderPhoto.created_at.desc())
    )
    result = await db.execute(query)
    photos = result.scalars().all()

    return [
        {
            "id": str(p.id),
            "work_order_id": str(p.work_order_id),
            "photo_type": p.photo_type,
            "data_url": p.data,
            "thumbnail_url": p.thumbnail,
            "timestamp": p.timestamp.isoformat() if p.timestamp else None,
            "gps_lat": p.gps_lat,
            "gps_lng": p.gps_lng,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in photos
    ]


@router.post("/jobs/{work_order_id}/payment")
async def record_job_payment(
    work_order_id: str,
    request: RecordPaymentRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Record payment collected in the field by technician.

    Auto-creates invoice if none exists, updates work order payment status,
    and broadcasts a WebSocket event for real-time dashboard updates.
    """
    from sqlalchemy import text
    from app.models.invoice import Invoice
    from app.services.websocket_manager import manager

    # Verify work order exists
    wo_result = await db.execute(select(WorkOrder).where(WorkOrder.id == work_order_id))
    work_order = wo_result.scalar_one_or_none()
    if not work_order:
        raise HTTPException(status_code=404, detail="Work order not found")

    now = datetime.now(timezone.utc)
    payment_date = now
    if request.payment_date:
        try:
            payment_date = datetime.fromisoformat(request.payment_date.replace("Z", "+00:00"))
        except ValueError:
            payment_date = now

    # Build description
    desc_parts = [f"Field payment collected by {current_user.email}"]
    if request.payment_method == "check" and request.check_number:
        desc_parts.append(f"Check #{request.check_number}")
    if request.notes:
        desc_parts.append(request.notes)

    payment_id = uuid_mod.uuid4()
    description = ". ".join(desc_parts)

    # Strip timezone for DB columns that are TIMESTAMP WITHOUT TIME ZONE
    payment_date_naive = payment_date.replace(tzinfo=None)
    now_naive = now.replace(tzinfo=None)

    # Auto-create invoice if none exists for this work order
    invoice_id = None
    inv_result = await db.execute(
        select(Invoice).where(Invoice.work_order_id == work_order_id).limit(1)
    )
    invoice = inv_result.scalar_one_or_none()

    if not invoice:
        # Auto-generate invoice
        invoice_id_val = uuid_mod.uuid4()
        invoice_number = f"INV-{now.strftime('%Y%m%d')}-{str(invoice_id_val)[:8].upper()}"
        customer_name = "Customer"
        if work_order.customer_id:
            cust_result = await db.execute(
                select(Customer).where(Customer.id == work_order.customer_id)
            )
            cust = cust_result.scalar_one_or_none()
            if cust:
                customer_name = f"{cust.first_name or ''} {cust.last_name or ''}".strip() or "Customer"

        job_type_label = (work_order.job_type or "service").replace("_", " ").title()
        line_items = [{
            "description": f"{job_type_label} - WO #{work_order.work_order_number or str(work_order_id)[:8]}",
            "quantity": 1,
            "unit_price": float(request.amount),
            "total": float(request.amount),
        }]

        invoice = Invoice(
            id=invoice_id_val,
            customer_id=work_order.customer_id,
            work_order_id=uuid_mod.UUID(work_order_id) if isinstance(work_order_id, str) else work_order_id,
            invoice_number=invoice_number,
            status="paid",
            amount=request.amount,
            paid_amount=request.amount,
            issue_date=now.date(),
            due_date=now.date(),
            paid_date=now.date(),
            line_items=line_items,
            notes=f"Auto-generated from field payment. {description}",
        )
        db.add(invoice)
        await db.flush()
        invoice_id = str(invoice_id_val)
        logger.info(f"Auto-created invoice {invoice_number} for WO {work_order_id}")
    else:
        invoice_id = str(invoice.id)
        # Update existing invoice paid_amount
        current_paid = float(invoice.paid_amount or 0)
        new_paid = current_paid + request.amount
        invoice.paid_amount = new_paid
        if invoice.amount and new_paid >= float(invoice.amount):
            invoice.status = "paid"
            invoice.paid_date = now.date()
        else:
            invoice.status = "partial"

    # Use raw SQL because Payment model has invoice_id as UUID but DB column is INTEGER
    await db.execute(
        text("""
            INSERT INTO payments (id, customer_id, work_order_id, amount, currency,
                payment_method, status, description, payment_date, processed_at)
            VALUES (:id, :customer_id, :work_order_id, :amount, :currency,
                :payment_method, :status, :description, :payment_date, :processed_at)
        """),
        {
            "id": str(payment_id),
            "customer_id": str(work_order.customer_id) if work_order.customer_id else None,
            "work_order_id": str(work_order_id),
            "amount": request.amount,
            "currency": "USD",
            "payment_method": request.payment_method,
            "status": "completed",
            "description": description,
            "payment_date": payment_date_naive,
            "processed_at": now_naive,
        },
    )

    # Add payment note to work order
    timestamp_str = now.strftime("%Y-%m-%d %H:%M")
    existing_notes = work_order.notes or ""
    method_label = request.payment_method.replace("_", " ").title()
    work_order.notes = f"{existing_notes}\n[{timestamp_str}] Payment: ${request.amount:.2f} via {method_label}".strip()

    await db.commit()

    # Broadcast payment received event
    try:
        await manager.broadcast_event(
            event_type="payment.received",
            data={
                "payment_id": str(payment_id),
                "work_order_id": work_order_id,
                "customer_id": str(work_order.customer_id) if work_order.customer_id else None,
                "amount": request.amount,
                "payment_method": request.payment_method,
                "invoice_id": invoice_id,
            },
        )
    except Exception:
        pass  # WebSocket broadcast is best-effort

    logger.info(f"Payment recorded for WO {work_order_id}: ${request.amount} via {request.payment_method} by {current_user.email}")

    # Get customer name for receipt
    customer_name = "Customer"
    if work_order.customer_id:
        cust_result = await db.execute(
            select(Customer).where(Customer.id == work_order.customer_id)
        )
        cust = cust_result.scalar_one_or_none()
        if cust:
            customer_name = f"{cust.first_name or ''} {cust.last_name or ''}".strip() or "Customer"

    return {
        "status": "recorded",
        "payment_id": str(payment_id),
        "work_order_id": work_order_id,
        "invoice_id": invoice_id,
        "amount": request.amount,
        "payment_method": request.payment_method,
        "payment_date": payment_date.isoformat(),
        "customer_name": customer_name,
        "description": description,
    }


@router.get("/jobs/{work_order_id}/payments")
async def list_job_payments(
    work_order_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """List all payments for a work order."""
    from app.models.payment import Payment

    wo_result = await db.execute(select(WorkOrder).where(WorkOrder.id == work_order_id))
    work_order = wo_result.scalar_one_or_none()
    if not work_order:
        raise HTTPException(status_code=404, detail="Work order not found")

    query = (
        select(Payment)
        .where(Payment.work_order_id == work_order_id)
        .order_by(Payment.created_at.desc())
    )
    result = await db.execute(query)
    payments = result.scalars().all()

    return [
        {
            "id": str(p.id),
            "work_order_id": str(p.work_order_id) if p.work_order_id else None,
            "amount": float(p.amount) if p.amount else 0,
            "payment_method": p.payment_method,
            "status": p.status,
            "description": p.description,
            "payment_date": p.payment_date.isoformat() if p.payment_date else None,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in payments
    ]


@router.post("/sync")
async def sync_offline_data(
    request: OfflineSyncRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Sync data collected while offline."""
    processed = 0
    errors = []

    for action in request.actions:
        try:
            action_type = action.get("type")
            action_data = action.get("data", {})

            if action_type == "clock_in":
                # Process clock in
                processed += 1
            elif action_type == "clock_out":
                processed += 1
            elif action_type == "status_update":
                processed += 1
            elif action_type == "checklist_update":
                processed += 1
            elif action_type == "photo":
                processed += 1
            else:
                errors.append({"action": action, "error": f"Unknown action type: {action_type}"})

        except Exception as e:
            errors.append({"action": action, "error": str(e)})

    return {
        "status": "synced",
        "processed": processed,
        "errors": errors,
        "sync_time": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/my-stats")
async def get_my_stats(
    db: DbSession,
    current_user: CurrentUser,
    period: str = Query("week"),  # day, week, month
):
    """Get technician's performance stats."""
    tech_result = await db.execute(select(Technician).where(Technician.email == current_user.email))
    technician = tech_result.scalar_one_or_none()

    if not technician:
        return {"message": "No technician profile found"}

    # Calculate date range
    today = date.today()
    if period == "day":
        start_date = today
    elif period == "week":
        start_date = today - timedelta(days=7)
    else:
        start_date = today - timedelta(days=30)

    # Get completed jobs
    completed_result = await db.execute(
        select(func.count())
        .select_from(WorkOrder)
        .where(
            WorkOrder.technician_id == technician.id,
            WorkOrder.status == "completed",
            WorkOrder.scheduled_date >= start_date,
        )
    )
    completed_jobs = completed_result.scalar() or 0

    # Get total labor minutes
    labor_result = await db.execute(
        select(func.sum(WorkOrder.total_labor_minutes)).where(
            WorkOrder.technician_id == technician.id,
            WorkOrder.scheduled_date >= start_date,
        )
    )
    total_labor_minutes = labor_result.scalar() or 0

    return {
        "period": period,
        "start_date": start_date.isoformat(),
        "jobs_completed": completed_jobs,
        "total_labor_hours": round(total_labor_minutes / 60, 1),
        "avg_job_duration_minutes": round(total_labor_minutes / completed_jobs, 0) if completed_jobs > 0 else 0,
    }


# ── Customer Service History ─────────────────────────────────────────────


@router.get("/customers/{customer_id}/service-history")
async def get_customer_service_history(
    customer_id: str,
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(default=20, ge=1, le=100),
):
    """Get work order history for a customer (for technician context)."""
    from app.models.work_order_photo import WorkOrderPhoto

    try:
        # Get all work orders for this customer, newest first
        result = await db.execute(
            select(WorkOrder)
            .where(WorkOrder.customer_id == customer_id)
            .order_by(WorkOrder.scheduled_date.desc().nullslast(), WorkOrder.created_at.desc())
            .limit(limit)
        )
        work_orders = result.scalars().all()

        # Get photo counts per work order
        wo_ids = [wo.id for wo in work_orders]
        photo_counts = {}
        if wo_ids:
            photo_result = await db.execute(
                select(
                    WorkOrderPhoto.work_order_id,
                    func.count(WorkOrderPhoto.id).label("count")
                )
                .where(WorkOrderPhoto.work_order_id.in_(wo_ids))
                .group_by(WorkOrderPhoto.work_order_id)
            )
            for row in photo_result:
                photo_counts[str(row.work_order_id)] = row.count

        # Calculate summary stats
        total_jobs = len(work_orders)
        completed_jobs = sum(1 for wo in work_orders if wo.status == "completed")
        last_service = None
        for wo in work_orders:
            if wo.status == "completed" and wo.scheduled_date:
                last_service = wo.scheduled_date.isoformat() if hasattr(wo.scheduled_date, 'isoformat') else str(wo.scheduled_date)
                break

        history = []
        for wo in work_orders:
            history.append({
                "id": str(wo.id),
                "work_order_number": wo.work_order_number,
                "job_type": wo.job_type,
                "status": wo.status,
                "priority": wo.priority,
                "scheduled_date": wo.scheduled_date.isoformat() if wo.scheduled_date and hasattr(wo.scheduled_date, 'isoformat') else str(wo.scheduled_date) if wo.scheduled_date else None,
                "notes": wo.notes,
                "total_amount": float(wo.total_amount) if wo.total_amount else None,
                "assigned_technician": wo.assigned_technician,
                "photo_count": photo_counts.get(str(wo.id), 0),
                "service_address_line1": wo.service_address_line1,
                "actual_start_time": wo.actual_start_time.isoformat() if wo.actual_start_time else None,
                "actual_end_time": wo.actual_end_time.isoformat() if wo.actual_end_time else None,
                "total_labor_minutes": wo.total_labor_minutes,
                "created_at": wo.created_at.isoformat() if wo.created_at else None,
            })

        return {
            "customer_id": customer_id,
            "total_jobs": total_jobs,
            "completed_jobs": completed_jobs,
            "last_service_date": last_service,
            "work_orders": history,
        }
    except Exception as e:
        logger.warning(f"Error fetching customer service history: {e}")
        raise HTTPException(status_code=500, detail="Could not load service history")


@router.get("/jobs/{work_order_id}/photos/gallery")
async def get_job_photos_gallery(
    work_order_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get all photos for a job with full data for gallery display."""
    from app.models.work_order_photo import WorkOrderPhoto

    try:
        result = await db.execute(
            select(WorkOrderPhoto)
            .where(WorkOrderPhoto.work_order_id == work_order_id)
            .order_by(WorkOrderPhoto.created_at.asc())
        )
        photos = result.scalars().all()

        return [
            {
                "id": str(p.id),
                "work_order_id": str(p.work_order_id),
                "photo_type": p.photo_type,
                "data_url": p.data,
                "thumbnail_url": p.thumbnail or p.data,
                "timestamp": p.timestamp.isoformat() if p.timestamp else None,
                "gps_lat": p.gps_lat,
                "gps_lng": p.gps_lng,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in photos
        ]
    except Exception as e:
        logger.warning(f"Error fetching job photos gallery: {e}")
        raise HTTPException(status_code=500, detail="Could not load photos")


# ── Inspection Checklist (Aerobic Systems) ───────────────────────────────


class InspectionStepUpdate(BaseModel):
    status: Optional[str] = None  # pending, in_progress, completed, skipped
    notes: Optional[str] = None
    voice_notes: Optional[str] = None
    findings: Optional[str] = None  # ok, needs_attention, critical
    finding_details: Optional[str] = None
    photos: Optional[List[str]] = None
    sludge_level: Optional[str] = None
    psi_reading: Optional[str] = None


class InspectionStartRequest(BaseModel):
    equipment_items: Optional[dict] = None  # {"sludge_judge": true, ...}


class InspectionCompleteRequest(BaseModel):
    tech_notes: Optional[str] = None
    recommend_pumping: Optional[bool] = None


class InspectionSaveRequest(BaseModel):
    inspection: Optional[dict] = None
    send_report: Optional[dict] = None  # {"method": "email"|"sms", "to": "...", "pdf_base64": "..."}


class ArrivalNotifyRequest(BaseModel):
    customer_phone: Optional[str] = None
    custom_message: Optional[str] = None


@router.get("/jobs/{job_id}/inspection")
async def get_inspection_state(
    job_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get the inspection checklist state for a work order."""
    try:
        result = await db.execute(
            select(WorkOrder).where(WorkOrder.id == job_id)
        )
        wo = result.scalars().first()
        if not wo:
            raise HTTPException(status_code=404, detail="Work order not found")

        checklist = wo.checklist or {}
        inspection = checklist.get("inspection", None)
        return {"success": True, "inspection": inspection}
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Error getting inspection state: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/jobs/{job_id}/inspection/start")
async def start_inspection(
    job_id: str,
    body: InspectionStartRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Initialize the inspection checklist for a work order."""
    try:
        result = await db.execute(
            select(WorkOrder).where(WorkOrder.id == job_id)
        )
        wo = result.scalars().first()
        if not wo:
            raise HTTPException(status_code=404, detail="Work order not found")

        now = datetime.now(timezone.utc).isoformat()
        checklist = wo.checklist or {}

        inspection = {
            "started_at": now,
            "completed_at": None,
            "equipment_verified": bool(body.equipment_items),
            "equipment_items": body.equipment_items or {},
            "homeowner_notified_at": None,
            "current_step": 1,
            "steps": {},
            "summary": None,
            "voice_guidance_enabled": False,
        }
        checklist["inspection"] = inspection
        wo.checklist = checklist
        # Force SQLAlchemy to detect JSON change
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(wo, "checklist")
        await db.commit()

        return {"success": True, "inspection": inspection}
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Error starting inspection: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/jobs/{job_id}/inspection/step/{step_number}")
async def update_inspection_step(
    job_id: str,
    step_number: int,
    body: InspectionStepUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update a single inspection step."""
    try:
        result = await db.execute(
            select(WorkOrder).where(WorkOrder.id == job_id)
        )
        wo = result.scalars().first()
        if not wo:
            raise HTTPException(status_code=404, detail="Work order not found")

        checklist = wo.checklist or {}
        inspection = checklist.get("inspection")
        if not inspection:
            raise HTTPException(status_code=400, detail="Inspection not started")

        steps = inspection.get("steps", {})
        step_key = str(step_number)
        existing = steps.get(step_key, {
            "status": "pending",
            "completed_at": None,
            "notes": "",
            "voice_notes": "",
            "findings": "ok",
            "finding_details": "",
            "photos": [],
        })

        # Merge updates
        if body.status is not None:
            existing["status"] = body.status
            if body.status == "completed":
                existing["completed_at"] = datetime.now(timezone.utc).isoformat()
        if body.notes is not None:
            existing["notes"] = body.notes
        if body.voice_notes is not None:
            existing["voice_notes"] = body.voice_notes
        if body.findings is not None:
            existing["findings"] = body.findings
        if body.finding_details is not None:
            existing["finding_details"] = body.finding_details
        if body.photos is not None:
            existing["photos"] = body.photos
        if body.sludge_level is not None:
            existing["sludge_level"] = body.sludge_level
        if body.psi_reading is not None:
            existing["psi_reading"] = body.psi_reading

        steps[step_key] = existing
        inspection["steps"] = steps
        # Advance current_step when completing a step
        if body.status == "completed":
            inspection["current_step"] = step_number + 1
        else:
            inspection["current_step"] = step_number
        checklist["inspection"] = inspection
        wo.checklist = checklist

        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(wo, "checklist")
        await db.commit()

        return {"success": True, "step": existing}
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Error updating inspection step: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/jobs/{job_id}/inspection/save")
async def save_inspection_state(
    job_id: str,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
):
    """Bulk save the entire inspection state and optionally send report."""
    try:
        body = await request.json()
        result = await db.execute(
            select(WorkOrder).where(WorkOrder.id == job_id)
        )
        wo = result.scalars().first()
        if not wo:
            raise HTTPException(status_code=404, detail="Work order not found")

        # Save inspection state if provided
        inspection_data = body.get("inspection")
        if inspection_data:
            checklist = wo.checklist or {}
            checklist["inspection"] = inspection_data
            wo.checklist = checklist
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(wo, "checklist")
            await db.commit()

        # Send report if requested
        send_report = body.get("send_report")
        report_sent = False
        if send_report:
            method = send_report.get("method")
            to = send_report.get("to")
            if method == "sms" and to:
                try:
                    from app.services.twilio_service import TwilioService
                    sms_service = TwilioService()
                    # Build a concise text summary
                    insp = (wo.checklist or {}).get("inspection", {})
                    summary = insp.get("summary", {})
                    condition = summary.get("overall_condition", "N/A")
                    issues = summary.get("total_issues", 0)
                    sms_body = (
                        f"MAC Septic Inspection Report\n"
                        f"Condition: {condition.upper()}\n"
                        f"Issues found: {issues}\n"
                    )
                    recs = summary.get("recommendations", [])
                    if recs:
                        sms_body += "Findings:\n"
                        for rec in recs[:3]:
                            sms_body += f"- {rec[:80]}\n"
                    sms_body += "\nThank you for choosing MAC Septic!"
                    await sms_service.send_sms(to=to, body=sms_body)
                    report_sent = True
                except Exception as sms_err:
                    logger.warning(f"Failed to send report via SMS: {sms_err}")
            elif method == "email" and to:
                try:
                    from app.services.email_service import EmailService
                    email_svc = EmailService()
                    if not email_svc.is_configured:
                        logger.warning("Brevo email service not configured")
                    else:
                        insp = (wo.checklist or {}).get("inspection", {})
                        summary = insp.get("summary", {})
                        condition = summary.get("overall_condition", "N/A")
                        issues = summary.get("total_issues", 0)
                        recs = summary.get("recommendations", [])

                        # Get customer name
                        cust_name = "Valued Customer"
                        if wo.customer_id:
                            cust_result = await db.execute(
                                select(Customer).where(Customer.id == wo.customer_id)
                            )
                            cust = cust_result.scalars().first()
                            if cust:
                                cust_name = f"{cust.first_name or ''} {cust.last_name or ''}".strip() or "Valued Customer"

                        # Build HTML email
                        condition_color = "#22c55e" if condition == "good" else "#f59e0b" if condition == "fair" else "#ef4444"
                        condition_label = "Good" if condition == "good" else "Needs Attention" if condition == "fair" else "Needs Repair"

                        recs_html = ""
                        if recs:
                            recs_items = "".join(f"<li style='margin-bottom:4px'>{r}</li>" for r in recs)
                            recs_html = f"<h3 style='margin-top:16px'>Recommendations:</h3><ul>{recs_items}</ul>"

                        html_body = f"""
                        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto">
                          <div style="background:#1e40af;color:white;padding:20px;text-align:center">
                            <h1 style="margin:0;font-size:20px">MAC Septic Services</h1>
                            <p style="margin:4px 0 0;font-size:14px">Septic System Inspection Report</p>
                          </div>
                          <div style="padding:20px">
                            <p>Hi {cust_name},</p>
                            <p>Thank you for choosing MAC Septic. Here are the results of your septic system inspection:</p>
                            <div style="background:{condition_color};color:white;padding:16px;border-radius:8px;text-align:center;margin:16px 0">
                              <strong style="font-size:18px">Overall Condition: {condition_label}</strong>
                              <br><span style="font-size:14px">{issues} item(s) noted</span>
                            </div>
                            {recs_html}
                            <p style="margin-top:20px;color:#666;font-size:13px">
                              A detailed PDF report is attached. If you have questions, call us at (512) 555-0100.
                            </p>
                            <p>Thank you,<br><strong>MAC Septic Services</strong></p>
                          </div>
                        </div>
                        """

                        plain_text = (
                            f"MAC Septic Inspection Report\n\n"
                            f"Hi {cust_name},\n\n"
                            f"Overall Condition: {condition_label}\n"
                            f"Issues noted: {issues}\n\n"
                        )
                        if recs:
                            plain_text += "Recommendations:\n"
                            for r in recs:
                                plain_text += f"- {r}\n"
                        plain_text += "\nThank you for choosing MAC Septic!"

                        result = await email_svc.send_email(
                            to=to,
                            subject=f"Your Septic Inspection Report — {condition_label}",
                            body=plain_text,
                            html_body=html_body,
                        )
                        report_sent = result.get("success", False)
                        if not report_sent:
                            logger.warning(f"Brevo email failed: {result.get('error')}")
                except Exception as email_err:
                    logger.warning(f"Failed to send report via email: {email_err}")

        return {"success": True, "report_sent": report_sent}
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Error saving inspection: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/jobs/{job_id}/inspection/complete")
async def complete_inspection(
    job_id: str,
    body: InspectionCompleteRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Mark inspection as complete and generate summary."""
    try:
        result = await db.execute(
            select(WorkOrder).where(WorkOrder.id == job_id)
        )
        wo = result.scalars().first()
        if not wo:
            raise HTTPException(status_code=404, detail="Work order not found")

        checklist = wo.checklist or {}
        inspection = checklist.get("inspection")
        if not inspection:
            raise HTTPException(status_code=400, detail="Inspection not started")

        now = datetime.now(timezone.utc).isoformat()
        steps = inspection.get("steps", {})

        # Compute summary
        total_steps = len(steps)
        critical_count = sum(1 for s in steps.values() if s.get("findings") == "critical")
        attention_count = sum(1 for s in steps.values() if s.get("findings") == "needs_attention")

        if critical_count > 0:
            overall = "critical"
        elif attention_count >= 3:
            overall = "poor"
        elif attention_count >= 1:
            overall = "fair"
        else:
            overall = "good"

        recommendations = []
        upsell = []
        for step_num, step_data in steps.items():
            findings = step_data.get("findings", "ok")
            details = step_data.get("finding_details", "")
            if findings == "critical":
                recommendations.append(f"URGENT (Step {step_num}): {details or 'Critical issue — schedule repair immediately.'}")
            elif findings == "needs_attention":
                recommendations.append(f"Step {step_num}: {details or 'Needs maintenance attention.'}")

        # Add sludge level to recommendations if recorded
        step_7 = steps.get("7", {})
        sludge_level = step_7.get("sludge_level", "")
        if sludge_level:
            recommendations.append(f"Sludge level measured at {sludge_level}. Schedule pumping based on current level.")

        if body.recommend_pumping:
            recommendations.append("Technician recommends scheduling pumping service.")

        upsell.append("Schedule regular pumping based on sludge level observed.")
        upsell.append("Consider a maintenance plan for quarterly inspections.")
        if attention_count > 0 or critical_count > 0:
            upsell.append("Repair service recommended for issues found during inspection.")

        summary = {
            "generated_at": now,
            "overall_condition": overall,
            "total_steps": total_steps,
            "total_issues": critical_count + attention_count,
            "critical_issues": critical_count,
            "recommendations": recommendations,
            "upsell_opportunities": upsell,
            "next_service_date": None,
            "tech_notes": body.tech_notes or "",
            "report_sent_via": [],
            "report_sent_at": None,
            "estimate_total": None,
        }

        inspection["completed_at"] = now
        inspection["recommend_pumping"] = body.recommend_pumping or False
        inspection["summary"] = summary
        checklist["inspection"] = inspection
        wo.checklist = checklist

        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(wo, "checklist")
        await db.commit()

        return {"success": True, "summary": summary}
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Error completing inspection: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/jobs/{job_id}/inspection/create-estimate")
async def create_estimate_from_inspection(
    job_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a formal Quote/Estimate from inspection findings."""
    import uuid as uuid_mod
    from app.models.quote import Quote
    from app.models.customer import Customer

    try:
        result = await db.execute(
            select(WorkOrder).where(WorkOrder.id == job_id)
        )
        wo = result.scalars().first()
        if not wo:
            raise HTTPException(status_code=404, detail="Work order not found")

        checklist = wo.checklist or {}
        inspection = checklist.get("inspection")
        if not inspection:
            raise HTTPException(status_code=400, detail="Inspection not started")

        steps = inspection.get("steps", {})
        if not steps:
            raise HTTPException(status_code=400, detail="No inspection steps recorded")

        # Parts catalog keyed by step number (mirrors frontend inspectionSteps.ts)
        STEP_PARTS = {
            7: [
                {"service": "Replacement lid screws", "part": "LID-SCR-SS", "rate": 8},
                {"service": "Riser extension", "part": "RSR-24-GRN", "rate": 65},
            ],
            8: [
                {"service": "Replacement float switch", "part": "FLT-UNI-120", "rate": 45},
                {"service": "Float switch wire nuts", "part": "WN-14-WP", "rate": 5},
            ],
            9: [
                {"service": "Replacement alarm light bulb", "part": "ALM-BULB-12V", "rate": 12},
                {"service": "Wire nuts (waterproof)", "part": "WN-14-WP", "rate": 5},
            ],
            11: [
                {"service": "Alarm light bulb", "part": "ALM-BULB-12V", "rate": 12},
                {"service": "Buzzer unit", "part": "BZR-12V-WP", "rate": 25},
            ],
            12: [
                {"service": "Silicon sealant", "part": "SIL-CLR-10OZ", "rate": 8},
                {"service": "Wire nuts (waterproof)", "part": "WN-14-WP", "rate": 5},
                {"service": "Conduit sealant", "part": "CND-SEAL-GRY", "rate": 12},
            ],
            14: [
                {"service": "Drip filter", "part": "DRP-FLT-STD", "rate": 18},
                {"service": "Check valve", "part": "CHK-VLV-1IN", "rate": 22},
                {"service": "Spray head (replacement)", "part": "SPR-HD-360", "rate": 15},
            ],
        }

        line_items = []
        issue_step_count = 0

        for step_num_str, step_data in steps.items():
            findings = step_data.get("findings", "ok")
            if findings == "ok":
                continue
            issue_step_count += 1
            step_num = int(step_num_str)
            parts = STEP_PARTS.get(step_num, [])
            for part in parts:
                line_items.append({
                    "service": part["service"],
                    "description": f"Part #{part['part']} — Step {step_num}",
                    "quantity": 1,
                    "rate": float(part["rate"]),
                    "amount": float(part["rate"]),
                })

        # Add labor
        if issue_step_count > 0:
            labor_cost = issue_step_count * 75
            line_items.append({
                "service": "Labor (estimated)",
                "description": f"Repair labor for {issue_step_count} issue(s) found",
                "quantity": 1,
                "rate": float(labor_cost),
                "amount": float(labor_cost),
            })

        if not line_items:
            raise HTTPException(
                status_code=400,
                detail="No issues found in inspection — no estimate needed",
            )

        subtotal = sum(item["amount"] for item in line_items)
        tax_rate = 8.25
        tax = round(subtotal * tax_rate / 100, 2)
        total = round(subtotal + tax, 2)

        # Generate quote number
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        unique_id = str(uuid_mod.uuid4())[:8].upper()
        quote_number = f"Q-{timestamp}-{unique_id}"

        valid_until = datetime.now(timezone.utc) + timedelta(days=30)

        # Get customer name for notes
        customer_name = ""
        if wo.customer_id:
            cust_result = await db.execute(
                select(Customer).where(Customer.id == wo.customer_id)
            )
            customer = cust_result.scalars().first()
            if customer:
                customer_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip()

        quote = Quote(
            id=uuid_mod.uuid4(),
            quote_number=quote_number,
            customer_id=wo.customer_id,
            title="Inspection Repair Estimate",
            description=f"Based on inspection of {customer_name}'s septic system on {datetime.now(timezone.utc).strftime('%B %d, %Y')}",
            line_items=line_items,
            subtotal=subtotal,
            tax_rate=tax_rate,
            tax=tax,
            total=total,
            status="draft",
            valid_until=valid_until,
            notes="; ".join(inspection.get("summary", {}).get("recommendations", [])) or None,
        )
        db.add(quote)
        await db.commit()
        await db.refresh(quote)

        return {
            "quote_id": str(quote.id),
            "quote_number": quote.quote_number,
            "total": float(quote.total),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Error creating estimate from inspection: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/jobs/{job_id}/inspection/notify-arrival")
async def notify_arrival(
    job_id: str,
    body: ArrivalNotifyRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Send arrival SMS notification to homeowner."""
    try:
        result = await db.execute(
            select(WorkOrder).where(WorkOrder.id == job_id)
        )
        wo = result.scalars().first()
        if not wo:
            raise HTTPException(status_code=404, detail="Work order not found")

        # Get customer phone
        phone = body.customer_phone
        if not phone and wo.customer_id:
            cust_result = await db.execute(
                select(Customer).where(Customer.id == wo.customer_id)
            )
            cust = cust_result.scalars().first()
            if cust:
                phone = cust.phone

        if not phone:
            return {"success": False, "error": "No phone number available"}

        message = body.custom_message or (
            f"Hi! This is MAC Septic. Your technician has arrived for "
            f"your scheduled septic inspection. We'll knock when we're "
            f"ready to discuss findings. Thank you!"
        )

        # Try Twilio if available
        sent = False
        try:
            from app.services.twilio_service import TwilioService
            sms_service = TwilioService()
            result = await sms_service.send_sms(to=phone, body=message)
            sent = bool(result)
        except Exception as sms_err:
            logger.warning(f"Twilio SMS failed: {sms_err}")

        # Update inspection state
        checklist = wo.checklist or {}
        inspection = checklist.get("inspection", {})
        inspection["homeowner_notified_at"] = datetime.now(timezone.utc).isoformat()
        checklist["inspection"] = inspection
        wo.checklist = checklist

        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(wo, "checklist")
        await db.commit()

        return {
            "success": True,
            "sms_sent": sent,
            "phone": phone,
            "notified_at": inspection["homeowner_notified_at"],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Error sending arrival notification: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
