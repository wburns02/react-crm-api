"""Technician Dashboard API — single aggregated endpoint for field techs.

Returns everything a technician needs in ONE API call:
today's jobs, clock status, pay summary, performance stats.

Designed for non-tech-savvy users on mobile with spotty signal.
One request = one render = no loading spinners.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter
from sqlalchemy import select, func, and_, or_, cast, String

from app.services.cache_service import cache_service, TTL

from app.api.deps import DbSession, CurrentUser
from app.models.work_order import WorkOrder
from app.models.customer import Customer
from app.models.technician import Technician
from app.models.payroll import TimeEntry, Commission, PayrollPeriod

logger = logging.getLogger(__name__)
router = APIRouter()

# Plain English status labels + colors for the frontend
STATUS_LABELS = {
    "draft": ("Not Ready", "gray"),
    "scheduled": ("Ready to Go", "blue"),
    "en_route": ("On My Way", "yellow"),
    "in_progress": ("Working On It", "orange"),
    "completed": ("All Done", "green"),
    "cancelled": ("Cancelled", "red"),
    "on_hold": ("On Hold", "gray"),
}

JOB_TYPE_LABELS = {
    "pumping": "Pumping",
    "pump_out": "Pump Out",
    "inspection": "Inspection",
    "repair": "Repair",
    "installation": "Installation",
    "maintenance": "Maintenance",
    "grease_trap": "Grease Trap",
    "emergency": "Emergency",
    "other": "Service",
}


def _format_time(t) -> Optional[str]:
    """Format a time object to human-readable 12h string."""
    if t is None:
        return None
    try:
        if hasattr(t, "strftime"):
            return t.strftime("%-I:%M %p")
        return str(t)
    except Exception:
        return str(t)


def _format_date_plain(d) -> Optional[str]:
    """Format date as plain English: 'Feb 21'."""
    if d is None:
        return None
    try:
        if hasattr(d, "strftime"):
            return d.strftime("%b %-d")
        return str(d)
    except Exception:
        return str(d)


@router.get("/my-summary")
async def get_my_summary(
    db: DbSession,
    current_user: CurrentUser,
):
    """Get everything a technician needs for their dashboard in one call.

    Returns: technician info, clock status, today's jobs with plain English
    labels, stats, pay summary, and performance metrics.
    """
    cache_key = f"tech_dashboard:{current_user.email}"
    cached = await cache_service.get(cache_key)
    if cached:
        return cached

    # Safe default response — returned if anything goes wrong
    empty_response = {
        "technician": {
            "first_name": current_user.first_name or current_user.email.split("@")[0],
            "last_name": current_user.last_name or "",
            "id": "",
        },
        "clock_status": {
            "is_clocked_in": False,
            "clock_in_time": None,
            "active_entry_id": None,
        },
        "todays_jobs": [],
        "today_stats": {
            "total_jobs": 0,
            "completed_jobs": 0,
            "hours_worked": 0.0,
            "remaining_jobs": 0,
        },
        "pay_this_period": {
            "period_label": None,
            "next_payday": None,
            "commissions_earned": 0.0,
            "jobs_completed_period": 0,
            "backboard_threshold": 2307.69,
            "on_track": False,
        },
        "performance": {
            "jobs_this_week": 0,
            "jobs_last_week": 0,
            "avg_job_duration_minutes": 0,
        },
    }

    try:
        # 1. Find the technician record (same pattern as employee_portal.py)
        tech_result = await db.execute(
            select(Technician).where(Technician.email == current_user.email)
        )
        technician = tech_result.scalar_one_or_none()

        if not technician:
            logger.info(f"No technician record for {current_user.email}")
            return empty_response

        tech_id = technician.id
        tech_id_str = str(tech_id)
        tech_full_name = f"{technician.first_name or ''} {technician.last_name or ''}".strip()
        today = date.today()
        now = datetime.now(timezone.utc)

        # Match work orders by EITHER technician_id (UUID FK) OR assigned_technician (name string).
        # The schedule UI only sets assigned_technician (string), not technician_id (UUID FK),
        # so we must check both to find all jobs assigned to this technician.
        def _tech_filter():
            """OR filter: matches by UUID FK or by name string."""
            conditions = [WorkOrder.technician_id == tech_id]
            if tech_full_name:
                conditions.append(WorkOrder.assigned_technician == tech_full_name)
            return or_(*conditions)

        # Update response with technician info
        response = dict(empty_response)
        response["technician"] = {
            "first_name": technician.first_name or "",
            "last_name": technician.last_name or "",
            "id": tech_id_str,
        }

        # 2. Clock status — check for open TimeEntry (no clock_out)
        clock_result = await db.execute(
            select(TimeEntry)
            .where(
                TimeEntry.technician_id == tech_id,
                TimeEntry.clock_out.is_(None),
            )
            .order_by(TimeEntry.clock_in.desc())
            .limit(1)
        )
        active_entry = clock_result.scalar_one_or_none()

        response["clock_status"] = {
            "is_clocked_in": active_entry is not None,
            "clock_in_time": active_entry.clock_in.isoformat() if active_entry and active_entry.clock_in else None,
            "active_entry_id": str(active_entry.id) if active_entry else None,
        }

        # 3. Today's jobs — join with Customer table for real customer names
        jobs_result = await db.execute(
            select(WorkOrder, Customer)
            .outerjoin(Customer, WorkOrder.customer_id == Customer.id)
            .where(
                _tech_filter(),
                WorkOrder.scheduled_date == today,
            )
            .order_by(WorkOrder.time_window_start)
        )
        job_rows = jobs_result.all()
        work_orders = [row[0] for row in job_rows]
        # Build customer name lookup from joined data
        customer_names = {}
        for wo, cust in job_rows:
            if cust:
                customer_names[wo.id] = f"{cust.first_name or ''} {cust.last_name or ''}".strip() or "Customer"
            else:
                customer_names[wo.id] = "Customer"

        # Sort: in_progress first, then en_route, then scheduled, then completed
        status_priority = {"in_progress": 0, "en_route": 1, "scheduled": 2, "draft": 3, "completed": 4, "cancelled": 5}
        sorted_jobs = sorted(work_orders, key=lambda wo: status_priority.get(wo.status, 3))

        todays_jobs = []
        completed_count = 0
        for wo in sorted_jobs:
            status_raw = wo.status or "scheduled"
            label, color = STATUS_LABELS.get(status_raw, ("Unknown", "gray"))
            job_type_raw = wo.job_type or "other"
            job_type_label = JOB_TYPE_LABELS.get(job_type_raw, job_type_raw.replace("_", " ").title())

            if status_raw == "completed":
                completed_count += 1

            # Build time window string
            time_window = None
            tw_start = _format_time(wo.time_window_start)
            tw_end = _format_time(wo.time_window_end)
            if tw_start and tw_end:
                time_window = f"{tw_start} - {tw_end}"
            elif tw_start:
                time_window = tw_start

            # Build address string
            addr_parts = [wo.service_address_line1]
            if wo.service_city:
                addr_parts.append(wo.service_city)
            address = ", ".join(p for p in addr_parts if p) or None

            todays_jobs.append({
                "id": str(wo.id),
                "customer_id": str(wo.customer_id) if wo.customer_id else None,
                "customer_name": customer_names.get(wo.id, "Customer"),
                "job_type": job_type_raw,
                "job_type_label": job_type_label,
                "status": status_raw,
                "status_label": label,
                "status_color": color,
                "priority": wo.priority or "normal",
                "time_window": time_window,
                "address": address,
                "city": wo.service_city,
                "latitude": wo.service_latitude,
                "longitude": wo.service_longitude,
                "notes": wo.notes,
                "estimated_duration_hours": wo.estimated_duration_hours,
                "total_amount": float(wo.total_amount) if wo.total_amount else None,
            })

        response["todays_jobs"] = todays_jobs

        # 4. Today's stats
        total_jobs = len(work_orders)
        hours_result = await db.execute(
            select(func.sum(WorkOrder.total_labor_minutes)).where(
                _tech_filter(),
                WorkOrder.scheduled_date == today,
            )
        )
        minutes_today = hours_result.scalar() or 0
        hours_worked = round(minutes_today / 60, 1) if minutes_today else 0.0

        response["today_stats"] = {
            "total_jobs": total_jobs,
            "completed_jobs": completed_count,
            "hours_worked": hours_worked,
            "remaining_jobs": total_jobs - completed_count,
        }

        # 5. Pay this period — find current payroll period and sum commissions
        period_result = await db.execute(
            select(PayrollPeriod)
            .where(
                PayrollPeriod.start_date <= today,
                PayrollPeriod.end_date >= today,
            )
            .order_by(PayrollPeriod.start_date.desc())
            .limit(1)
        )
        current_period = period_result.scalar_one_or_none()

        if current_period:
            # Sum commissions for this tech in this period
            comm_result = await db.execute(
                select(func.coalesce(func.sum(Commission.commission_amount), 0.0))
                .where(
                    Commission.technician_id == tech_id,
                    Commission.earned_date >= current_period.start_date,
                    Commission.earned_date <= current_period.end_date,
                )
            )
            commissions_earned = float(comm_result.scalar() or 0.0)

            # Count jobs completed in period
            period_jobs_result = await db.execute(
                select(func.count())
                .select_from(WorkOrder)
                .where(
                    _tech_filter(),
                    WorkOrder.scheduled_date >= current_period.start_date,
                    WorkOrder.scheduled_date <= current_period.end_date,
                    cast(WorkOrder.status, String) == "completed",
                )
            )
            jobs_completed_period = period_jobs_result.scalar() or 0

            # Backboard threshold (default $60K/26 = $2,307.69)
            backboard_threshold = 2307.69

            # Estimate next payday (end_date + 5 business days)
            next_payday = current_period.end_date + timedelta(days=5)

            response["pay_this_period"] = {
                "period_label": f"{_format_date_plain(current_period.start_date)} - {_format_date_plain(current_period.end_date)}",
                "next_payday": _format_date_plain(next_payday),
                "commissions_earned": round(commissions_earned, 2),
                "jobs_completed_period": jobs_completed_period,
                "backboard_threshold": backboard_threshold,
                "on_track": commissions_earned >= backboard_threshold,
            }

        # 6. Performance — this week vs last week
        # This week = Monday to today
        week_start = today - timedelta(days=today.weekday())  # Monday
        last_week_start = week_start - timedelta(days=7)
        last_week_end = week_start - timedelta(days=1)

        this_week_result = await db.execute(
            select(func.count())
            .select_from(WorkOrder)
            .where(
                _tech_filter(),
                WorkOrder.scheduled_date >= week_start,
                WorkOrder.scheduled_date <= today,
                cast(WorkOrder.status, String) == "completed",
            )
        )
        jobs_this_week = this_week_result.scalar() or 0

        last_week_result = await db.execute(
            select(func.count())
            .select_from(WorkOrder)
            .where(
                _tech_filter(),
                WorkOrder.scheduled_date >= last_week_start,
                WorkOrder.scheduled_date <= last_week_end,
                cast(WorkOrder.status, String) == "completed",
            )
        )
        jobs_last_week = last_week_result.scalar() or 0

        # Average job duration this month
        avg_result = await db.execute(
            select(func.avg(WorkOrder.total_labor_minutes))
            .where(
                _tech_filter(),
                WorkOrder.scheduled_date >= today.replace(day=1),
                WorkOrder.total_labor_minutes.isnot(None),
                WorkOrder.total_labor_minutes > 0,
                cast(WorkOrder.status, String) == "completed",
            )
        )
        avg_minutes = avg_result.scalar()
        avg_job_duration = round(float(avg_minutes)) if avg_minutes else 0

        response["performance"] = {
            "jobs_this_week": jobs_this_week,
            "jobs_last_week": jobs_last_week,
            "avg_job_duration_minutes": avg_job_duration,
        }

        await cache_service.set(cache_key, response, TTL.SHORT)
        return response

    except Exception as e:
        logger.error(f"Technician dashboard error for {current_user.email}: {type(e).__name__}: {str(e)}")
        return empty_response
