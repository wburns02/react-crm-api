"""Payroll API - Time tracking, commissions, and payroll processing.

Features:
- Time entry management
- Commission tracking
- Payroll period management
- Overtime calculations
- Export for payroll systems (NACHA, CSV)
"""
from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, func, and_
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, date, timedelta
import logging

from app.api.deps import DbSession, CurrentUser
from app.models.payroll import PayrollPeriod, TimeEntry, Commission, TechnicianPayRate
from app.models.technician import Technician
from app.models.work_order import WorkOrder

logger = logging.getLogger(__name__)
router = APIRouter()


# Request Models

class TimeEntryCreate(BaseModel):
    technician_id: str
    entry_date: date
    clock_in: datetime
    clock_out: Optional[datetime] = None
    work_order_id: Optional[str] = None
    entry_type: str = "work"
    break_minutes: int = 0
    notes: Optional[str] = None


class PayRateUpdate(BaseModel):
    hourly_rate: float
    overtime_multiplier: float = 1.5
    job_commission_rate: float = 0.0
    upsell_commission_rate: float = 0.0
    weekly_overtime_threshold: float = 40.0


# Helper functions

def calculate_hours(clock_in: datetime, clock_out: datetime, break_minutes: int = 0) -> dict:
    """Calculate regular and overtime hours."""
    if not clock_out:
        return {"regular": 0, "overtime": 0}

    duration = clock_out - clock_in
    total_minutes = duration.total_seconds() / 60 - break_minutes
    total_hours = max(0, total_minutes / 60)

    # Note: Daily overtime logic - adjust based on requirements
    if total_hours > 8:
        return {"regular": 8, "overtime": total_hours - 8}
    return {"regular": total_hours, "overtime": 0}


# Payroll Period Endpoints

def _format_period(p: PayrollPeriod) -> dict:
    """Format a payroll period for the frontend."""
    regular = p.total_regular_hours or 0.0
    overtime = p.total_overtime_hours or 0.0
    gross = p.total_gross_pay or 0.0
    commissions = p.total_commissions or 0.0
    # Map backend status to frontend status
    status_map = {"open": "draft", "closed": "approved"}
    status = status_map.get(p.status, p.status) or "draft"
    return {
        "id": str(p.id),
        "start_date": p.start_date.isoformat(),
        "end_date": p.end_date.isoformat(),
        "period_type": p.period_type or "biweekly",
        "status": status,
        "total_hours": regular + overtime,
        "total_regular_hours": regular,
        "total_overtime_hours": overtime,
        "total_gross_pay": gross,
        "total_commissions": commissions,
        "total_deductions": 0.0,
        "total_net_pay": gross + commissions,
        "technician_count": p.technician_count or 0,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "approved_at": p.approved_at.isoformat() if p.approved_at else None,
        "approved_by": p.approved_by,
    }


@router.get("/periods")
async def list_payroll_periods(
    db: DbSession,
    current_user: CurrentUser,
    status: Optional[str] = Query(None),
    year: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List payroll periods."""
    try:
        query = select(PayrollPeriod)

        if status:
            # Map frontend status back to backend if needed
            reverse_map = {"draft": "open", "approved": "closed"}
            db_status = reverse_map.get(status, status)
            query = query.where(PayrollPeriod.status == db_status)
        if year:
            query = query.where(PayrollPeriod.start_date >= date(year, 1, 1))
            query = query.where(PayrollPeriod.end_date <= date(year, 12, 31))

        query = query.order_by(PayrollPeriod.start_date.desc())
        result = await db.execute(query)
        periods = result.scalars().all()
    except Exception as e:
        logger.error(f"Error fetching payroll periods: {type(e).__name__}: {str(e)}")
        # Return empty list instead of 500 - table may not exist yet
        return {"periods": []}

    return {
        "periods": [_format_period(p) for p in periods],
    }


@router.get("/current")
async def get_current_period(
    db: DbSession,
    current_user: CurrentUser,
):
    """Get current open payroll period."""
    try:
        today = date.today()

        result = await db.execute(
            select(PayrollPeriod).where(
                PayrollPeriod.start_date <= today,
                PayrollPeriod.end_date >= today,
                PayrollPeriod.status == "open",
            ).limit(1)
        )
        period = result.scalar_one_or_none()

        if not period:
            return {"message": "No current payroll period"}

        return _format_period(period)
    except Exception as e:
        logger.error(f"Error fetching current period: {type(e).__name__}: {str(e)}")
        return {"message": "No current payroll period"}


@router.post("/{period_id}/calculate")
async def calculate_payroll(
    period_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Calculate payroll for a period."""
    result = await db.execute(
        select(PayrollPeriod).where(PayrollPeriod.id == period_id)
    )
    period = result.scalar_one_or_none()

    if not period:
        raise HTTPException(status_code=404, detail="Payroll period not found")

    # Get all time entries
    entries_result = await db.execute(
        select(TimeEntry).where(
            TimeEntry.entry_date >= period.start_date,
            TimeEntry.entry_date <= period.end_date,
        )
    )
    entries = entries_result.scalars().all()

    # Get commissions
    comm_result = await db.execute(
        select(Commission).where(
            Commission.earned_date >= period.start_date,
            Commission.earned_date <= period.end_date,
        )
    )
    commissions = comm_result.scalars().all()

    # Calculate totals
    total_regular = sum(e.regular_hours or 0 for e in entries)
    total_overtime = sum(e.overtime_hours or 0 for e in entries)
    total_commissions = sum(c.commission_amount or 0 for c in commissions)

    # Get pay rates and calculate gross pay
    technician_ids = set(e.technician_id for e in entries)
    total_gross = 0.0

    for tech_id in technician_ids:
        rate_result = await db.execute(
            select(TechnicianPayRate).where(
                TechnicianPayRate.technician_id == tech_id,
                TechnicianPayRate.is_active == True,
            )
        )
        rate = rate_result.scalar_one_or_none()

        tech_regular = sum(e.regular_hours or 0 for e in entries if e.technician_id == tech_id)
        tech_overtime = sum(e.overtime_hours or 0 for e in entries if e.technician_id == tech_id)

        if rate:
            total_gross += tech_regular * rate.hourly_rate
            total_gross += tech_overtime * rate.hourly_rate * rate.overtime_multiplier

    # Update period totals
    period.total_regular_hours = total_regular
    period.total_overtime_hours = total_overtime
    period.total_gross_pay = total_gross
    period.total_commissions = total_commissions
    period.technician_count = len(technician_ids)

    # Link entries and commissions to period
    for entry in entries:
        entry.payroll_period_id = period.id
    for comm in commissions:
        comm.payroll_period_id = period.id

    await db.commit()

    return {
        "status": "calculated",
        "totals": {
            "regular_hours": total_regular,
            "overtime_hours": total_overtime,
            "gross_pay": total_gross,
            "commissions": total_commissions,
            "technicians": len(technician_ids),
        },
    }


@router.post("/periods/{period_id}/approve")
async def approve_payroll(
    period_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Approve payroll period for processing."""
    result = await db.execute(
        select(PayrollPeriod).where(PayrollPeriod.id == period_id)
    )
    period = result.scalar_one_or_none()

    if not period:
        raise HTTPException(status_code=404, detail="Payroll period not found")

    if period.status != "open":
        raise HTTPException(status_code=400, detail=f"Cannot approve period in '{period.status}' status")

    period.status = "approved"
    period.approved_by = current_user.email
    period.approved_at = datetime.utcnow()

    await db.commit()
    await db.refresh(period)

    return _format_period(period)


@router.post("/{period_id}/export")
async def export_payroll(
    period_id: str,
    db: DbSession,
    current_user: CurrentUser,
    format: str = Query("csv", pattern="^(csv|nacha|pdf)$"),
):
    """Export payroll data for payroll systems."""
    result = await db.execute(
        select(PayrollPeriod).where(PayrollPeriod.id == period_id)
    )
    period = result.scalar_one_or_none()

    if not period:
        raise HTTPException(status_code=404, detail="Payroll period not found")

    # TODO: Generate actual export files
    # For now, return data that could be exported

    return {
        "format": format,
        "period_id": period_id,
        "status": "export_ready",
        "message": f"Export to {format.upper()} format - implementation pending",
        "data": {
            "period": {
                "start": period.start_date.isoformat(),
                "end": period.end_date.isoformat(),
            },
            "totals": {
                "gross_pay": period.total_gross_pay,
                "commissions": period.total_commissions,
            },
        },
    }


# Time Entry Endpoints

@router.get("/time-entries")
async def list_time_entries(
    db: DbSession,
    current_user: CurrentUser,
    technician_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """List time entries."""
    try:
        query = select(TimeEntry)

        if technician_id:
            query = query.where(TimeEntry.technician_id == technician_id)
        if start_date:
            query = query.where(TimeEntry.entry_date >= start_date)
        if end_date:
            query = query.where(TimeEntry.entry_date <= end_date)
        if status_filter:
            query = query.where(TimeEntry.status == status_filter)

        # Count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Paginate
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(TimeEntry.entry_date.desc())

        result = await db.execute(query)
        entries = result.scalars().all()
    except Exception as e:
        logger.error(f"Error fetching time entries: {type(e).__name__}: {str(e)}")
        return {"entries": [], "total": 0, "page": 1, "page_size": page_size}

    return {
        "entries": [
            {
                "id": str(e.id),
                "technician_id": e.technician_id,
                "date": e.entry_date.isoformat(),
                "entry_date": e.entry_date.isoformat(),
                "clock_in": e.clock_in.isoformat() if e.clock_in else None,
                "clock_out": e.clock_out.isoformat() if e.clock_out else None,
                "regular_hours": e.regular_hours or 0,
                "overtime_hours": e.overtime_hours or 0,
                "break_minutes": e.break_minutes or 0,
                "entry_type": e.entry_type,
                "status": e.status,
                "work_order_id": e.work_order_id,
                "notes": e.notes,
            }
            for e in entries
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/time-entries")
async def create_time_entry(
    request: TimeEntryCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a time entry."""
    hours = calculate_hours(request.clock_in, request.clock_out, request.break_minutes)

    entry = TimeEntry(
        technician_id=request.technician_id,
        entry_date=request.entry_date,
        clock_in=request.clock_in,
        clock_out=request.clock_out,
        regular_hours=hours["regular"],
        overtime_hours=hours["overtime"],
        break_minutes=request.break_minutes,
        entry_type=request.entry_type,
        work_order_id=request.work_order_id,
        notes=request.notes,
    )

    db.add(entry)
    await db.commit()
    await db.refresh(entry)

    return {"id": str(entry.id), "hours": hours}


@router.patch("/time-entries/{entry_id}/approve")
async def approve_time_entry(
    entry_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Approve a time entry."""
    result = await db.execute(
        select(TimeEntry).where(TimeEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()

    if not entry:
        raise HTTPException(status_code=404, detail="Time entry not found")

    entry.status = "approved"
    entry.approved_by = current_user.email
    entry.approved_at = datetime.utcnow()

    await db.commit()

    return {"status": "approved"}


# Pay Rate Endpoints

@router.get("/pay-rates/{technician_id}")
async def get_pay_rate(
    technician_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get pay rate for a technician."""
    result = await db.execute(
        select(TechnicianPayRate).where(
            TechnicianPayRate.technician_id == technician_id,
            TechnicianPayRate.is_active == True,
        )
    )
    rate = result.scalar_one_or_none()

    if not rate:
        return {
            "technician_id": technician_id,
            "hourly_rate": None,
            "message": "No pay rate configured",
        }

    return {
        "technician_id": technician_id,
        "hourly_rate": rate.hourly_rate,
        "overtime_multiplier": rate.overtime_multiplier,
        "job_commission_rate": rate.job_commission_rate,
        "upsell_commission_rate": rate.upsell_commission_rate,
        "weekly_overtime_threshold": rate.weekly_overtime_threshold,
        "effective_date": rate.effective_date.isoformat(),
    }


@router.post("/pay-rates/{technician_id}")
async def set_pay_rate(
    technician_id: str,
    request: PayRateUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Set or update pay rate for a technician."""
    # Deactivate existing rate
    existing_result = await db.execute(
        select(TechnicianPayRate).where(
            TechnicianPayRate.technician_id == technician_id,
            TechnicianPayRate.is_active == True,
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        existing.is_active = False
        existing.end_date = date.today()

    # Create new rate
    rate = TechnicianPayRate(
        technician_id=technician_id,
        hourly_rate=request.hourly_rate,
        overtime_multiplier=request.overtime_multiplier,
        job_commission_rate=request.job_commission_rate,
        upsell_commission_rate=request.upsell_commission_rate,
        weekly_overtime_threshold=request.weekly_overtime_threshold,
        effective_date=date.today(),
        is_active=True,
    )

    db.add(rate)
    await db.commit()

    return {"status": "updated", "effective_date": rate.effective_date.isoformat()}


class CreatePeriodRequest(BaseModel):
    """Request to create a new payroll period."""
    start_date: date
    end_date: date
    period_type: str = "biweekly"


class UpdatePeriodRequest(BaseModel):
    """Request to update a payroll period."""
    start_date: Optional[date] = None
    end_date: Optional[date] = None


@router.post("/periods")
async def create_payroll_period(
    request: CreatePeriodRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new payroll period."""
    # Validate dates
    if request.end_date <= request.start_date:
        raise HTTPException(
            status_code=400,
            detail="End date must be after start date"
        )

    try:
        # Check for overlapping periods
        overlap_result = await db.execute(
            select(PayrollPeriod).where(
                and_(
                    PayrollPeriod.start_date <= request.end_date,
                    PayrollPeriod.end_date >= request.start_date,
                )
            )
        )
        if overlap_result.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail="Period overlaps with existing period"
            )

        # Create the period
        period = PayrollPeriod(
            start_date=request.start_date,
            end_date=request.end_date,
            period_type=request.period_type,
            status="open",
        )

        db.add(period)
        await db.commit()
        await db.refresh(period)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating payroll period: {type(e).__name__}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create payroll period: {type(e).__name__}"
        )

    return _format_period(period)


@router.patch("/periods/{period_id}")
async def update_payroll_period(
    period_id: str,
    request: UpdatePeriodRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update a payroll period (only while in draft/open status)."""
    result = await db.execute(
        select(PayrollPeriod).where(PayrollPeriod.id == period_id)
    )
    period = result.scalar_one_or_none()

    if not period:
        raise HTTPException(status_code=404, detail="Payroll period not found")

    if period.status != "open":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot edit period in '{period.status}' status"
        )

    new_start = request.start_date or period.start_date
    new_end = request.end_date or period.end_date

    if new_end <= new_start:
        raise HTTPException(status_code=400, detail="End date must be after start date")

    # Check for overlaps (excluding current period)
    overlap_result = await db.execute(
        select(PayrollPeriod).where(
            and_(
                PayrollPeriod.id != period_id,
                PayrollPeriod.start_date <= new_end,
                PayrollPeriod.end_date >= new_start,
            )
        )
    )
    if overlap_result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Period overlaps with existing period")

    if request.start_date is not None:
        period.start_date = request.start_date
    if request.end_date is not None:
        period.end_date = request.end_date

    await db.commit()
    await db.refresh(period)
    return _format_period(period)


@router.get("/periods/{period_id}/summary")
async def get_period_summary(
    period_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get payroll summary by technician for a period."""
    result = await db.execute(
        select(PayrollPeriod).where(PayrollPeriod.id == period_id)
    )
    period = result.scalar_one_or_none()

    if not period:
        raise HTTPException(status_code=404, detail="Payroll period not found")

    # Get time entries grouped by technician
    entries_result = await db.execute(
        select(TimeEntry).where(TimeEntry.payroll_period_id == period_id)
    )
    entries = entries_result.scalars().all()

    # Get commissions
    comm_result = await db.execute(
        select(Commission).where(Commission.payroll_period_id == period_id)
    )
    commissions = comm_result.scalars().all()

    # Group by technician
    by_technician = {}
    for entry in entries:
        tech_id = entry.technician_id
        if tech_id not in by_technician:
            by_technician[tech_id] = {
                "technician_id": tech_id,
                "regular_hours": 0,
                "overtime_hours": 0,
                "gross_pay": 0,
                "commissions": 0,
            }
        by_technician[tech_id]["regular_hours"] += entry.regular_hours or 0
        by_technician[tech_id]["overtime_hours"] += entry.overtime_hours or 0

    for comm in commissions:
        tech_id = comm.technician_id
        if tech_id not in by_technician:
            by_technician[tech_id] = {
                "technician_id": tech_id,
                "regular_hours": 0,
                "overtime_hours": 0,
                "gross_pay": 0,
                "commissions": 0,
            }
        by_technician[tech_id]["commissions"] += comm.commission_amount or 0

    return {"summaries": list(by_technician.values())}


@router.get("/commissions")
async def list_commissions(
    db: DbSession,
    current_user: CurrentUser,
    technician_id: Optional[str] = None,
    payroll_period_id: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """List commissions."""
    try:
        query = select(Commission)

        if technician_id:
            query = query.where(Commission.technician_id == technician_id)
        if payroll_period_id:
            query = query.where(Commission.payroll_period_id == payroll_period_id)
        if status_filter:
            query = query.where(Commission.status == status_filter)

        # Count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Paginate
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(Commission.earned_date.desc())

        result = await db.execute(query)
        commissions = result.scalars().all()
    except Exception as e:
        logger.error(f"Error fetching commissions: {type(e).__name__}: {str(e)}")
        return {"commissions": [], "total": 0, "page": 1, "page_size": page_size}

    return {
        "commissions": [
            {
                "id": str(c.id),
                "technician_id": c.technician_id,
                "work_order_id": c.work_order_id,
                "invoice_id": c.invoice_id,
                "payroll_period_id": str(c.payroll_period_id) if c.payroll_period_id else None,
                "commission_type": c.commission_type,
                "base_amount": c.base_amount,
                "rate": c.rate,
                "rate_type": c.rate_type,
                "commission_amount": c.commission_amount,
                "status": c.status,
                "description": c.description,
                "earned_date": c.earned_date.isoformat(),
            }
            for c in commissions
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


class BulkApproveTimeEntriesRequest(BaseModel):
    entry_ids: List[str]


class BulkApproveCommissionsRequest(BaseModel):
    commission_ids: List[str]


@router.post("/time-entries/bulk-approve")
async def bulk_approve_time_entries(
    request: BulkApproveTimeEntriesRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Bulk approve time entries."""
    approved = 0
    for entry_id in request.entry_ids:
        result = await db.execute(
            select(TimeEntry).where(TimeEntry.id == entry_id)
        )
        entry = result.scalar_one_or_none()
        if entry and entry.status == "pending":
            entry.status = "approved"
            entry.approved_by = current_user.email
            entry.approved_at = datetime.utcnow()
            approved += 1

    await db.commit()
    return {"approved": approved}


@router.post("/commissions/bulk-approve")
async def bulk_approve_commissions(
    request: BulkApproveCommissionsRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Bulk approve commissions."""
    approved = 0
    for comm_id in request.commission_ids:
        result = await db.execute(
            select(Commission).where(Commission.id == comm_id)
        )
        comm = result.scalar_one_or_none()
        if comm and comm.status == "pending":
            comm.status = "approved"
            approved += 1

    await db.commit()
    return {"approved": approved}


@router.get("/pay-rates")
async def list_pay_rates(
    db: DbSession,
    current_user: CurrentUser,
    technician_id: Optional[str] = None,
    is_active: Optional[bool] = None,
):
    """List all pay rates."""
    try:
        query = select(TechnicianPayRate)

        if technician_id:
            query = query.where(TechnicianPayRate.technician_id == technician_id)
        if is_active is not None:
            query = query.where(TechnicianPayRate.is_active == is_active)

        result = await db.execute(query)
        rates = result.scalars().all()
    except Exception as e:
        logger.error(f"Error fetching pay rates: {type(e).__name__}: {str(e)}")
        return {"rates": []}

    return {
        "rates": [
            {
                "id": str(r.id),
                "technician_id": r.technician_id,
                "hourly_rate": r.hourly_rate,
                "overtime_rate": r.hourly_rate * (r.overtime_multiplier or 1.5),
                "overtime_multiplier": r.overtime_multiplier,
                "commission_rate": r.job_commission_rate or 0,
                "job_commission_rate": r.job_commission_rate,
                "upsell_commission_rate": r.upsell_commission_rate,
                "weekly_overtime_threshold": r.weekly_overtime_threshold,
                "effective_date": r.effective_date.isoformat(),
                "end_date": r.end_date.isoformat() if r.end_date else None,
                "is_active": r.is_active,
            }
            for r in rates
        ]
    }


# Stats

@router.get("/stats")
async def get_payroll_stats(
    db: DbSession,
    current_user: CurrentUser,
):
    """Get payroll statistics."""
    try:
        today = date.today()
        year_start = today.replace(month=1, day=1)

        # Current period stats
        current_result = await db.execute(
            select(PayrollPeriod).where(
                PayrollPeriod.start_date <= today,
                PayrollPeriod.end_date >= today,
            ).limit(1)
        )
        current_period = current_result.scalar_one_or_none()

        # YTD totals
        ytd_result = await db.execute(
            select(
                func.sum(PayrollPeriod.total_gross_pay),
                func.sum(PayrollPeriod.total_commissions),
            ).where(
                PayrollPeriod.start_date >= year_start,
                PayrollPeriod.status.in_(["approved", "processed"]),
            )
        )
        ytd_gross, ytd_commissions = ytd_result.first() or (0, 0)

        # Pending approvals
        pending_result = await db.execute(
            select(func.count()).select_from(TimeEntry).where(
                TimeEntry.status == "pending"
            )
        )
        pending_count = pending_result.scalar() or 0
    except Exception as e:
        logger.error(f"Error fetching payroll stats: {type(e).__name__}: {str(e)}")
        return {
            "current_period": None,
            "ytd_gross_pay": 0,
            "ytd_commissions": 0,
            "pending_approvals": 0,
        }

    return {
        "current_period": {
            "hours": (current_period.total_regular_hours or 0) + (current_period.total_overtime_hours or 0),
            "amount": current_period.total_gross_pay or 0,
        } if current_period else None,
        "ytd_gross_pay": ytd_gross or 0,
        "ytd_commissions": ytd_commissions or 0,
        "pending_approvals": pending_count,
    }


# Period detail - MUST be after all fixed-path GET routes to avoid catching
# /time-entries, /commissions, /pay-rates, /stats as period_id

@router.get("/{period_id}")
async def get_payroll_period(
    period_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get payroll period with detail."""
    try:
        result = await db.execute(
            select(PayrollPeriod).where(PayrollPeriod.id == period_id)
        )
        period = result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Error fetching period {period_id}: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=404, detail="Payroll period not found")

    if not period:
        raise HTTPException(status_code=404, detail="Payroll period not found")

    # Get time entries for period
    entries_result = await db.execute(
        select(TimeEntry).where(TimeEntry.payroll_period_id == period_id)
    )
    entries = entries_result.scalars().all()

    # Get commissions for period
    comm_result = await db.execute(
        select(Commission).where(Commission.payroll_period_id == period_id)
    )
    commissions = comm_result.scalars().all()

    # Group by technician
    by_technician = {}
    for entry in entries:
        tech_id = entry.technician_id
        if tech_id not in by_technician:
            by_technician[tech_id] = {
                "regular_hours": 0,
                "overtime_hours": 0,
                "entries": [],
            }
        by_technician[tech_id]["regular_hours"] += entry.regular_hours or 0
        by_technician[tech_id]["overtime_hours"] += entry.overtime_hours or 0
        by_technician[tech_id]["entries"].append({
            "id": str(entry.id),
            "date": entry.entry_date.isoformat(),
            "regular_hours": entry.regular_hours,
            "overtime_hours": entry.overtime_hours,
            "status": entry.status,
        })

    return {
        "id": str(period.id),
        "start_date": period.start_date.isoformat(),
        "end_date": period.end_date.isoformat(),
        "status": period.status,
        "totals": {
            "regular_hours": period.total_regular_hours,
            "overtime_hours": period.total_overtime_hours,
            "gross_pay": period.total_gross_pay,
            "commissions": period.total_commissions,
        },
        "by_technician": by_technician,
    }


# Commission Dashboard Endpoints

@router.get("/commissions/stats")
async def get_commission_stats(
    db: DbSession,
    current_user: CurrentUser,
    period_id: Optional[str] = None,
):
    """Get commission statistics for dashboard KPI cards."""
    try:
        today = date.today()
        # Default to current month if no period specified
        month_start = today.replace(day=1)
        month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)

        # Base query for current period
        query = select(Commission)
        if period_id:
            query = query.where(Commission.payroll_period_id == period_id)
        else:
            query = query.where(
                Commission.earned_date >= month_start,
                Commission.earned_date <= month_end,
            )

        result = await db.execute(query)
        commissions = result.scalars().all()

        # Calculate stats
        total = sum(c.commission_amount or 0 for c in commissions)
        pending = [c for c in commissions if c.status == "pending"]
        approved = [c for c in commissions if c.status == "approved"]
        paid = [c for c in commissions if c.status == "paid"]

        pending_amount = sum(c.commission_amount or 0 for c in pending)
        approved_amount = sum(c.commission_amount or 0 for c in approved)
        paid_amount = sum(c.commission_amount or 0 for c in paid)

        total_jobs = len(commissions)
        avg_per_job = total / total_jobs if total_jobs > 0 else 0

        # Previous period comparison (last month)
        prev_start = (month_start - timedelta(days=1)).replace(day=1)
        prev_end = month_start - timedelta(days=1)
        prev_result = await db.execute(
            select(Commission).where(
                Commission.earned_date >= prev_start,
                Commission.earned_date <= prev_end,
            )
        )
        prev_commissions = prev_result.scalars().all()
        prev_total = sum(c.commission_amount or 0 for c in prev_commissions)
        prev_jobs = len(prev_commissions)
        prev_avg = prev_total / prev_jobs if prev_jobs > 0 else 0

        total_change = ((total - prev_total) / prev_total * 100) if prev_total > 0 else 0
        avg_change = ((avg_per_job - prev_avg) / prev_avg * 100) if prev_avg > 0 else 0

        return {
            "total_commissions": total,
            "pending_count": len(pending),
            "pending_amount": pending_amount,
            "approved_count": len(approved),
            "approved_amount": approved_amount,
            "paid_count": len(paid),
            "paid_amount": paid_amount,
            "average_per_job": round(avg_per_job, 2),
            "total_jobs": total_jobs,
            "comparison_to_last_period": {
                "total_change_pct": round(total_change, 1),
                "average_change_pct": round(avg_change, 1),
            },
        }
    except Exception as e:
        logger.error(f"Error fetching commission stats: {type(e).__name__}: {str(e)}")
        return {
            "total_commissions": 0,
            "pending_count": 0,
            "pending_amount": 0,
            "approved_count": 0,
            "approved_amount": 0,
            "paid_count": 0,
            "paid_amount": 0,
            "average_per_job": 0,
            "total_jobs": 0,
            "comparison_to_last_period": {"total_change_pct": 0, "average_change_pct": 0},
        }


@router.get("/commissions/leaderboard")
async def get_commission_leaderboard(
    db: DbSession,
    current_user: CurrentUser,
    period_id: Optional[str] = None,
):
    """Get commission leaderboard - top earners ranked by total commission."""
    try:
        today = date.today()
        month_start = today.replace(day=1)
        month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)

        # Get commissions for current period
        query = select(Commission)
        if period_id:
            query = query.where(Commission.payroll_period_id == period_id)
        else:
            query = query.where(
                Commission.earned_date >= month_start,
                Commission.earned_date <= month_end,
            )

        result = await db.execute(query)
        commissions = result.scalars().all()

        # Previous period for trend comparison
        prev_start = (month_start - timedelta(days=1)).replace(day=1)
        prev_end = month_start - timedelta(days=1)
        prev_result = await db.execute(
            select(Commission).where(
                Commission.earned_date >= prev_start,
                Commission.earned_date <= prev_end,
            )
        )
        prev_commissions = prev_result.scalars().all()

        # Group by technician
        by_tech = {}
        for c in commissions:
            tech_id = c.technician_id
            if tech_id not in by_tech:
                by_tech[tech_id] = {
                    "total_earned": 0,
                    "jobs_completed": 0,
                    "rates": [],
                }
            by_tech[tech_id]["total_earned"] += c.commission_amount or 0
            by_tech[tech_id]["jobs_completed"] += 1
            if c.rate:
                by_tech[tech_id]["rates"].append(c.rate)

        # Previous period by tech
        prev_by_tech = {}
        for c in prev_commissions:
            tech_id = c.technician_id
            if tech_id not in prev_by_tech:
                prev_by_tech[tech_id] = {"total_earned": 0}
            prev_by_tech[tech_id]["total_earned"] += c.commission_amount or 0

        # Get technician names
        tech_ids = list(by_tech.keys())
        if tech_ids:
            tech_result = await db.execute(
                select(Technician).where(Technician.id.in_(tech_ids))
            )
            technicians = {str(t.id): t for t in tech_result.scalars().all()}
        else:
            technicians = {}

        # Build leaderboard entries
        entries = []
        for tech_id, data in by_tech.items():
            tech = technicians.get(tech_id)
            avg_rate = sum(data["rates"]) / len(data["rates"]) if data["rates"] else 0
            avg_commission = data["total_earned"] / data["jobs_completed"] if data["jobs_completed"] > 0 else 0

            prev_total = prev_by_tech.get(tech_id, {}).get("total_earned", 0)
            trend_pct = ((data["total_earned"] - prev_total) / prev_total * 100) if prev_total > 0 else 0
            trend = "up" if trend_pct > 5 else ("down" if trend_pct < -5 else "neutral")

            entries.append({
                "technician_id": tech_id,
                "technician_name": f"{tech.first_name} {tech.last_name}" if tech else f"Tech #{tech_id}",
                "total_earned": round(data["total_earned"], 2),
                "jobs_completed": data["jobs_completed"],
                "average_commission": round(avg_commission, 2),
                "commission_rate": round(avg_rate, 4),
                "trend": trend,
                "trend_percentage": round(abs(trend_pct), 1),
                "rank_change": 0,  # Would need historical data to calculate
            })

        # Sort by total earned and assign ranks
        entries.sort(key=lambda x: x["total_earned"], reverse=True)
        for i, entry in enumerate(entries):
            entry["rank"] = i + 1

        return {"entries": entries[:10]}  # Top 10
    except Exception as e:
        logger.error(f"Error fetching leaderboard: {type(e).__name__}: {str(e)}")
        return {"entries": []}


@router.get("/commissions/insights")
async def get_commission_insights(
    db: DbSession,
    current_user: CurrentUser,
):
    """Get AI-generated commission insights."""
    try:
        today = date.today()
        month_start = today.replace(day=1)

        # Get current month commissions
        result = await db.execute(
            select(Commission).where(
                Commission.earned_date >= month_start,
                Commission.earned_date <= today,
            )
        )
        commissions = result.scalars().all()

        pending = [c for c in commissions if c.status == "pending"]
        total = sum(c.commission_amount or 0 for c in commissions)

        insights = []

        # Insight 1: Pending commissions alert
        if len(pending) > 0:
            pending_amount = sum(c.commission_amount or 0 for c in pending)
            old_pending = [c for c in pending if (today - c.earned_date).days > 5]
            if len(old_pending) > 0:
                insights.append({
                    "id": "pending_old",
                    "type": "alert",
                    "severity": "warning",
                    "title": f"{len(old_pending)} commissions pending > 5 days",
                    "description": f"${sum(c.commission_amount or 0 for c in old_pending):,.2f} in commissions may need management review",
                    "action": {"label": "Review Now", "callback_type": "view_pending"},
                })
            else:
                insights.append({
                    "id": "pending_normal",
                    "type": "info",
                    "severity": "info",
                    "title": f"{len(pending)} commissions awaiting approval",
                    "description": f"${pending_amount:,.2f} total pending",
                    "metric": {"label": "Pending", "value": f"${pending_amount:,.0f}"},
                })

        # Insight 2: Top performer
        by_tech = {}
        for c in commissions:
            tech_id = c.technician_id
            if tech_id not in by_tech:
                by_tech[tech_id] = 0
            by_tech[tech_id] += c.commission_amount or 0

        if by_tech:
            top_tech = max(by_tech.items(), key=lambda x: x[1])
            tech_result = await db.execute(
                select(Technician).where(Technician.id == top_tech[0])
            )
            tech = tech_result.scalar_one_or_none()
            tech_name = f"{tech.first_name} {tech.last_name}" if tech else f"Tech #{top_tech[0]}"

            insights.append({
                "id": "top_performer",
                "type": "trend",
                "severity": "success",
                "title": f"{tech_name} is leading this month",
                "description": "Top earner for current period",
                "metric": {"label": "Total Earned", "value": f"${top_tech[1]:,.0f}"},
            })

        # Insight 3: Month progress
        days_passed = (today - month_start).days + 1
        days_in_month = ((month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1) - month_start).days + 1
        progress_pct = round(days_passed / days_in_month * 100)

        if total > 0:
            projected = total / days_passed * days_in_month
            insights.append({
                "id": "projection",
                "type": "opportunity",
                "severity": "info",
                "title": f"On track for ${projected:,.0f} this month",
                "description": f"{progress_pct}% of month complete",
                "metric": {"label": "Projected", "value": f"${projected:,.0f}", "change": f"{progress_pct}% complete"},
            })

        return {"insights": insights}
    except Exception as e:
        logger.error(f"Error generating insights: {type(e).__name__}: {str(e)}")
        return {"insights": []}


class BulkMarkPaidRequest(BaseModel):
    commission_ids: List[str]


@router.post("/commissions/bulk-mark-paid")
async def bulk_mark_paid_commissions(
    request: BulkMarkPaidRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Bulk mark commissions as paid."""
    paid = 0
    for comm_id in request.commission_ids:
        result = await db.execute(
            select(Commission).where(Commission.id == comm_id)
        )
        comm = result.scalar_one_or_none()
        if comm and comm.status == "approved":
            comm.status = "paid"
            paid += 1

    await db.commit()
    return {"paid": paid}


@router.get("/commissions/export")
async def export_commissions(
    db: DbSession,
    current_user: CurrentUser,
    status_filter: Optional[str] = Query(None, alias="status"),
    technician_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """Export commissions to CSV."""
    from fastapi.responses import StreamingResponse
    import csv
    import io

    try:
        query = select(Commission)

        if status_filter and status_filter != "all":
            query = query.where(Commission.status == status_filter)
        if technician_id:
            query = query.where(Commission.technician_id == technician_id)
        if date_from:
            query = query.where(Commission.earned_date >= date.fromisoformat(date_from))
        if date_to:
            query = query.where(Commission.earned_date <= date.fromisoformat(date_to))

        query = query.order_by(Commission.earned_date.desc())
        result = await db.execute(query)
        commissions = result.scalars().all()

        # Get technician names
        tech_ids = list(set(c.technician_id for c in commissions))
        if tech_ids:
            tech_result = await db.execute(
                select(Technician).where(Technician.id.in_(tech_ids))
            )
            technicians = {str(t.id): f"{t.first_name} {t.last_name}" for t in tech_result.scalars().all()}
        else:
            technicians = {}

        # Build CSV
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Date", "Technician", "Work Order", "Type", "Job Total",
            "Rate", "Commission Amount", "Status"
        ])

        for c in commissions:
            writer.writerow([
                c.earned_date.isoformat(),
                technicians.get(c.technician_id, c.technician_id),
                c.work_order_id or "",
                c.commission_type or "job_completion",
                f"${c.base_amount:.2f}" if c.base_amount else "",
                f"{(c.rate or 0) * 100:.0f}%",
                f"${c.commission_amount:.2f}" if c.commission_amount else "",
                c.status,
            ])

        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=commissions-{date.today().isoformat()}.csv"},
        )
    except Exception as e:
        logger.error(f"Error exporting commissions: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to export commissions")
