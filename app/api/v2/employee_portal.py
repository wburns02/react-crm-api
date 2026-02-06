"""Employee Portal API - Mobile-first field service features.

Features:
- GPS-verified time clock
- Job checklists
- Photo capture
- Customer signatures
- Offline sync support
"""

from fastapi import APIRouter, HTTPException, status, Query, UploadFile, File
from sqlalchemy import select, func, and_
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, date, timedelta, timezone
import logging

from app.api.deps import DbSession, CurrentUser
from app.models.work_order import WorkOrder
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
        "first_name": technician.name.split()[0] if technician.name else "",
        "last_name": " ".join(technician.name.split()[1:])
        if technician.name and len(technician.name.split()) > 1
        else "",
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
):
    """Get jobs assigned to current technician (frontend-compatible)."""
    tech_result = await db.execute(select(Technician).where(Technician.email == current_user.email))
    technician = tech_result.scalar_one_or_none()

    if not technician:
        return {"jobs": []}

    query = select(WorkOrder).where(WorkOrder.technician_id == technician.id)

    if date_filter:
        query = query.where(WorkOrder.scheduled_date == date.fromisoformat(date_filter))
    else:
        query = query.where(WorkOrder.scheduled_date == date.today())

    query = query.order_by(WorkOrder.time_window_start)
    result = await db.execute(query)
    work_orders = result.scalars().all()

    return {
        "jobs": [
            {
                "id": str(wo.id),
                "customer_id": str(wo.customer_id),
                "customer_name": wo.customer_name,
                "job_type": wo.job_type,
                "status": wo.status,
                "priority": wo.priority,
                "scheduled_date": wo.scheduled_date.isoformat() if wo.scheduled_date else None,
                "time_window_start": str(wo.time_window_start) if wo.time_window_start else None,
                "time_window_end": str(wo.time_window_end) if wo.time_window_end else None,
                "address": wo.service_address_line1,
                "city": wo.service_city,
                "state": wo.service_state,
                "zip": wo.service_zip,
                "latitude": wo.service_latitude,
                "longitude": wo.service_longitude,
                "notes": wo.notes,
                "checklist": wo.checklist,
                "estimated_duration_hours": wo.estimated_duration_hours,
                "is_clocked_in": wo.is_clocked_in,
            }
            for wo in work_orders
        ]
    }


@router.get("/jobs/{job_id}")
async def get_employee_job(
    job_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a single job."""
    wo_result = await db.execute(select(WorkOrder).where(WorkOrder.id == job_id))
    work_order = wo_result.scalar_one_or_none()

    if not work_order:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "id": str(work_order.id),
        "customer_id": str(work_order.customer_id),
        "customer_name": work_order.customer_name,
        "job_type": work_order.job_type,
        "status": work_order.status,
        "priority": work_order.priority,
        "scheduled_date": work_order.scheduled_date.isoformat() if work_order.scheduled_date else None,
        "time_window_start": str(work_order.time_window_start) if work_order.time_window_start else None,
        "time_window_end": str(work_order.time_window_end) if work_order.time_window_end else None,
        "address": work_order.service_address_line1,
        "city": work_order.service_city,
        "state": work_order.service_state,
        "zip": work_order.service_zip,
        "latitude": work_order.service_latitude,
        "longitude": work_order.service_longitude,
        "notes": work_order.notes,
        "checklist": work_order.checklist,
        "estimated_duration_hours": work_order.estimated_duration_hours,
        "is_clocked_in": work_order.is_clocked_in,
        "actual_start_time": work_order.actual_start_time.isoformat() if work_order.actual_start_time else None,
        "actual_end_time": work_order.actual_end_time.isoformat() if work_order.actual_end_time else None,
        "total_labor_minutes": work_order.total_labor_minutes,
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
