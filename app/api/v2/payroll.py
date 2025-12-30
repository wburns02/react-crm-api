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

@router.get("")
async def list_payroll_periods(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
):
    """List payroll periods."""
    query = select(PayrollPeriod)

    if status_filter:
        query = query.where(PayrollPeriod.status == status_filter)

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Paginate
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(PayrollPeriod.start_date.desc())

    result = await db.execute(query)
    periods = result.scalars().all()

    return {
        "items": [
            {
                "id": str(p.id),
                "start_date": p.start_date.isoformat(),
                "end_date": p.end_date.isoformat(),
                "period_type": p.period_type,
                "status": p.status,
                "total_regular_hours": p.total_regular_hours,
                "total_overtime_hours": p.total_overtime_hours,
                "total_gross_pay": p.total_gross_pay,
                "total_commissions": p.total_commissions,
                "technician_count": p.technician_count,
            }
            for p in periods
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/current")
async def get_current_period(
    db: DbSession,
    current_user: CurrentUser,
):
    """Get current open payroll period."""
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
        # Create new period if none exists
        # Default to biweekly
        start = today - timedelta(days=today.weekday())  # Start of week
        end = start + timedelta(days=13)  # Two weeks

        period = PayrollPeriod(
            start_date=start,
            end_date=end,
            period_type="biweekly",
            status="open",
        )
        db.add(period)
        await db.commit()
        await db.refresh(period)

    return {
        "id": str(period.id),
        "start_date": period.start_date.isoformat(),
        "end_date": period.end_date.isoformat(),
        "status": period.status,
        "total_regular_hours": period.total_regular_hours,
        "total_overtime_hours": period.total_overtime_hours,
        "total_gross_pay": period.total_gross_pay,
    }


@router.get("/{period_id}")
async def get_payroll_period(
    period_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get payroll period with detail."""
    result = await db.execute(
        select(PayrollPeriod).where(PayrollPeriod.id == period_id)
    )
    period = result.scalar_one_or_none()

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


@router.post("/{period_id}/approve")
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

    return {"status": "approved"}


@router.post("/{period_id}/export")
async def export_payroll(
    period_id: str,
    format: str = Query("csv", pattern="^(csv|nacha|pdf)$"),
    db: DbSession = None,
    current_user: CurrentUser = None,
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

    return {
        "items": [
            {
                "id": str(e.id),
                "technician_id": e.technician_id,
                "entry_date": e.entry_date.isoformat(),
                "clock_in": e.clock_in.isoformat() if e.clock_in else None,
                "clock_out": e.clock_out.isoformat() if e.clock_out else None,
                "regular_hours": e.regular_hours,
                "overtime_hours": e.overtime_hours,
                "break_minutes": e.break_minutes,
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


# Stats

@router.get("/stats")
async def get_payroll_stats(
    db: DbSession,
    current_user: CurrentUser,
):
    """Get payroll statistics."""
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

    return {
        "current_period": {
            "hours": current_period.total_regular_hours + current_period.total_overtime_hours if current_period else 0,
            "amount": current_period.total_gross_pay if current_period else 0,
        } if current_period else None,
        "ytd_gross_pay": ytd_gross or 0,
        "ytd_commissions": ytd_commissions or 0,
        "pending_approvals": pending_count,
    }
