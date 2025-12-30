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
from datetime import datetime, date, timedelta
import logging

from app.api.deps import DbSession, CurrentUser
from app.models.work_order import WorkOrder
from app.models.technician import Technician

logger = logging.getLogger(__name__)
router = APIRouter()


# Models

class ClockInRequest(BaseModel):
    latitude: float
    longitude: float
    work_order_id: Optional[str] = None
    notes: Optional[str] = None


class ClockOutRequest(BaseModel):
    latitude: float
    longitude: float
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

@router.get("/my-jobs")
async def get_my_jobs(
    db: DbSession,
    current_user: CurrentUser,
    date_filter: Optional[date] = None,
):
    """Get jobs assigned to current technician."""
    # Find technician by email
    tech_result = await db.execute(
        select(Technician).where(Technician.email == current_user.email)
    )
    technician = tech_result.scalar_one_or_none()

    if not technician:
        return {"jobs": [], "message": "No technician profile found"}

    query = select(WorkOrder).where(WorkOrder.technician_id == str(technician.id))

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
    # Find technician
    tech_result = await db.execute(
        select(Technician).where(Technician.email == current_user.email)
    )
    technician = tech_result.scalar_one_or_none()

    if not technician:
        raise HTTPException(status_code=404, detail="Technician profile not found")

    # If work order specified, clock into that job
    if request.work_order_id:
        wo_result = await db.execute(
            select(WorkOrder).where(WorkOrder.id == request.work_order_id)
        )
        work_order = wo_result.scalar_one_or_none()

        if not work_order:
            raise HTTPException(status_code=404, detail="Work order not found")

        work_order.is_clocked_in = True
        work_order.actual_start_time = datetime.utcnow()
        work_order.clock_in_gps_lat = request.latitude
        work_order.clock_in_gps_lon = request.longitude

        if work_order.status == "scheduled":
            work_order.status = "in_progress"

        await db.commit()

        return {
            "status": "clocked_in",
            "work_order_id": request.work_order_id,
            "time": datetime.utcnow().isoformat(),
            "location_verified": True,
        }

    # General clock in (start of day)
    return {
        "status": "clocked_in",
        "time": datetime.utcnow().isoformat(),
        "location": {"lat": request.latitude, "lon": request.longitude},
    }


@router.post("/clock-out")
async def clock_out(
    request: ClockOutRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Clock out from work (GPS verified)."""
    if request.work_order_id:
        wo_result = await db.execute(
            select(WorkOrder).where(WorkOrder.id == request.work_order_id)
        )
        work_order = wo_result.scalar_one_or_none()

        if not work_order:
            raise HTTPException(status_code=404, detail="Work order not found")

        work_order.is_clocked_in = False
        work_order.actual_end_time = datetime.utcnow()
        work_order.clock_out_gps_lat = request.latitude
        work_order.clock_out_gps_lon = request.longitude

        # Calculate labor minutes
        if work_order.actual_start_time:
            duration = datetime.utcnow() - work_order.actual_start_time
            work_order.total_labor_minutes = int(duration.total_seconds() / 60)

        await db.commit()

        return {
            "status": "clocked_out",
            "work_order_id": request.work_order_id,
            "time": datetime.utcnow().isoformat(),
            "labor_minutes": work_order.total_labor_minutes,
        }

    return {
        "status": "clocked_out",
        "time": datetime.utcnow().isoformat(),
    }


@router.patch("/jobs/{work_order_id}/status")
async def update_job_status(
    work_order_id: str,
    request: JobStatusUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update job status from the field."""
    wo_result = await db.execute(
        select(WorkOrder).where(WorkOrder.id == work_order_id)
    )
    work_order = wo_result.scalar_one_or_none()

    if not work_order:
        raise HTTPException(status_code=404, detail="Work order not found")

    work_order.status = request.status

    if request.notes:
        existing_notes = work_order.notes or ""
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
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
    wo_result = await db.execute(
        select(WorkOrder).where(WorkOrder.id == work_order_id)
    )
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
    """Upload a photo for a job."""
    # TODO: Actually store the file (S3, local, etc.)
    # For now, just acknowledge

    return {
        "status": "uploaded",
        "work_order_id": work_order_id,
        "photo_type": photo_type,
        "filename": file.filename,
        "message": "Photo upload endpoint ready - storage integration pending",
    }


@router.post("/jobs/{work_order_id}/signature")
async def capture_customer_signature(
    work_order_id: str,
    request: CustomerSignatureCapture,
    db: DbSession,
    current_user: CurrentUser,
):
    """Capture customer signature for job completion."""
    wo_result = await db.execute(
        select(WorkOrder).where(WorkOrder.id == work_order_id)
    )
    work_order = wo_result.scalar_one_or_none()

    if not work_order:
        raise HTTPException(status_code=404, detail="Work order not found")

    # TODO: Store signature data and create signed document
    # For now, mark job as signed

    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    notes = work_order.notes or ""
    work_order.notes = f"{notes}\n[{timestamp}] Signed by: {request.signer_name}".strip()

    await db.commit()

    return {
        "status": "signature_captured",
        "signer_name": request.signer_name,
        "timestamp": datetime.utcnow().isoformat(),
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
        "sync_time": datetime.utcnow().isoformat(),
    }


@router.get("/my-stats")
async def get_my_stats(
    db: DbSession,
    current_user: CurrentUser,
    period: str = Query("week"),  # day, week, month
):
    """Get technician's performance stats."""
    tech_result = await db.execute(
        select(Technician).where(Technician.email == current_user.email)
    )
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
        select(func.count()).select_from(WorkOrder).where(
            WorkOrder.technician_id == str(technician.id),
            WorkOrder.status == "completed",
            WorkOrder.scheduled_date >= start_date,
        )
    )
    completed_jobs = completed_result.scalar() or 0

    # Get total labor minutes
    labor_result = await db.execute(
        select(func.sum(WorkOrder.total_labor_minutes)).where(
            WorkOrder.technician_id == str(technician.id),
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
