"""
Availability API endpoints for public lead form scheduling.

Provides available time slots based on current work order schedule.
This is a PUBLIC endpoint - no authentication required.
"""
from fastapi import APIRouter, Query, HTTPException
from sqlalchemy import select, func, and_
from typing import Optional, List
from datetime import datetime, date, timedelta
from pydantic import BaseModel, Field

from app.api.deps import DbSession
from app.models.work_order import WorkOrder

router = APIRouter()

# Business configuration
BUSINESS_START = "08:00"
BUSINESS_END = "17:00"
MAX_CONCURRENT_JOBS = 3  # Adjust based on team size

# Standard time windows
STANDARD_WINDOWS = [
    {"start": "08:00", "end": "12:00", "name": "morning"},
    {"start": "12:00", "end": "17:00", "name": "afternoon"},
]


class TimeWindow(BaseModel):
    """A time window with availability status."""
    start: str = Field(..., description="Start time in HH:MM format")
    end: str = Field(..., description="End time in HH:MM format")
    available: bool = Field(..., description="Whether this time window is available")
    slots_remaining: int = Field(default=1, description="Number of available slots")


class DayAvailability(BaseModel):
    """Availability for a single day."""
    date: str = Field(..., description="Date in YYYY-MM-DD format")
    day_name: str = Field(..., description="Day of the week")
    is_weekend: bool = Field(default=False)
    available: bool = Field(..., description="Whether any slots are available")
    time_windows: List[TimeWindow] = Field(default_factory=list)


class AvailabilityResponse(BaseModel):
    """Response containing availability slots."""
    slots: List[DayAvailability] = Field(default_factory=list)
    start_date: str
    end_date: str
    total_available_days: int = 0


def windows_overlap(start1: str, end1: str, start2: str, end2: str) -> bool:
    """Check if two time windows overlap."""
    def to_minutes(time_str: str) -> int:
        if not time_str:
            return 0
        try:
            h, m = map(int, time_str.split(":"))
            return h * 60 + m
        except:
            return 0

    s1, e1 = to_minutes(start1), to_minutes(end1)
    s2, e2 = to_minutes(start2), to_minutes(end2)
    return s1 < e2 and s2 < e1


@router.get("/slots", response_model=AvailabilityResponse)
async def get_availability_slots(
    db: DbSession,
    start_date: Optional[str] = Query(None, description="Start date YYYY-MM-DD (default: today)"),
    end_date: Optional[str] = Query(None, description="End date YYYY-MM-DD (default: start + 7 days)"),
    service_type: Optional[str] = Query(None, description="Filter by service type"),
) -> AvailabilityResponse:
    """
    Get available scheduling slots for the lead capture form.

    Returns available days and time windows (Morning 8am-12pm, Afternoon 12pm-5pm).
    This is a PUBLIC endpoint - no authentication required.
    """
    # Parse dates
    if start_date:
        try:
            parsed_start = datetime.strptime(start_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format")
    else:
        parsed_start = date.today()

    if end_date:
        try:
            parsed_end = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format")
    else:
        parsed_end = parsed_start + timedelta(days=7)

    # Validate
    if parsed_end < parsed_start:
        raise HTTPException(status_code=400, detail="end_date must be after start_date")

    if parsed_start < date.today():
        parsed_start = date.today()

    # Limit to 30 days
    max_end = parsed_start + timedelta(days=30)
    if parsed_end > max_end:
        parsed_end = max_end

    # Get scheduled work orders in date range
    active_statuses = ["scheduled", "confirmed", "enroute", "on_site", "in_progress"]

    query = select(WorkOrder).where(
        and_(
            func.date(WorkOrder.scheduled_date) >= parsed_start,
            func.date(WorkOrder.scheduled_date) <= parsed_end,
            WorkOrder.status.in_(active_statuses)
        )
    )

    if service_type:
        query = query.where(WorkOrder.job_type == service_type)

    result = await db.execute(query)
    work_orders = result.scalars().all()

    # Group work orders by date
    busy_by_date: dict[str, list] = {}
    for wo in work_orders:
        if wo.scheduled_date:
            date_str = wo.scheduled_date.isoformat() if hasattr(wo.scheduled_date, 'isoformat') else str(wo.scheduled_date)[:10]
            if date_str not in busy_by_date:
                busy_by_date[date_str] = []
            busy_by_date[date_str].append({
                "start": str(wo.time_window_start) if wo.time_window_start else BUSINESS_START,
                "end": str(wo.time_window_end) if wo.time_window_end else BUSINESS_END,
            })

    # Calculate availability for each day
    slots: List[DayAvailability] = []
    total_available = 0
    current = parsed_start

    while current <= parsed_end:
        day_str = current.isoformat()
        day_name = current.strftime("%A")
        is_weekend = current.weekday() >= 5

        if is_weekend:
            # Weekends not available (unless emergency)
            slots.append(DayAvailability(
                date=day_str,
                day_name=day_name,
                is_weekend=True,
                available=False,
                time_windows=[]
            ))
        else:
            # Calculate time window availability
            day_busy = busy_by_date.get(day_str, [])
            time_windows: List[TimeWindow] = []
            any_available = False

            for window in STANDARD_WINDOWS:
                overlapping = sum(
                    1 for busy in day_busy
                    if windows_overlap(window["start"], window["end"], busy["start"], busy["end"])
                )
                slots_remaining = max(0, MAX_CONCURRENT_JOBS - overlapping)
                is_available = slots_remaining > 0

                if is_available:
                    any_available = True

                time_windows.append(TimeWindow(
                    start=window["start"],
                    end=window["end"],
                    available=is_available,
                    slots_remaining=slots_remaining
                ))

            if any_available:
                total_available += 1

            slots.append(DayAvailability(
                date=day_str,
                day_name=day_name,
                is_weekend=False,
                available=any_available,
                time_windows=time_windows
            ))

        current += timedelta(days=1)

    return AvailabilityResponse(
        slots=slots,
        start_date=parsed_start.isoformat(),
        end_date=parsed_end.isoformat(),
        total_available_days=total_available
    )


@router.get("/next-available", response_model=AvailabilityResponse)
async def get_next_available(
    db: DbSession,
    service_type: Optional[str] = Query(None),
) -> AvailabilityResponse:
    """Get the next available slots (up to 5 available days)."""
    # Get availability for next 14 days
    result = await get_availability_slots(
        db=db,
        start_date=date.today().isoformat(),
        end_date=(date.today() + timedelta(days=14)).isoformat(),
        service_type=service_type
    )

    # Filter to only available days
    available_slots = [s for s in result.slots if s.available][:5]

    return AvailabilityResponse(
        slots=available_slots,
        start_date=result.start_date,
        end_date=result.end_date,
        total_available_days=len(available_slots)
    )
