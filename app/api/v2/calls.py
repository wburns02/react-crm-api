"""Calls API - Unified call center endpoints.

Features:
- List and filter calls with pagination
- Call details with customer linking
- Call dispositions management
- Call analytics (volume, missed calls, avg duration)
"""

from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, func, extract, case
from sqlalchemy.orm import selectinload
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, timedelta, date
import logging

from app.api.deps import DbSession, CurrentUser
from app.models.call_log import CallLog
from app.models.call_disposition import CallDisposition
from app.models.customer import Customer

logger = logging.getLogger(__name__)
router = APIRouter()


# Request/Response Models


class CallResponse(BaseModel):
    id: int
    ringcentral_call_id: Optional[str] = None
    caller_number: Optional[str] = None
    called_number: Optional[str] = None
    direction: Optional[str] = None
    call_disposition: Optional[str] = None
    call_type: Optional[str] = None
    call_date: Optional[date] = None
    call_time: Optional[str] = None
    duration_seconds: Optional[int] = None
    ring_duration: Optional[int] = None
    recording_url: Optional[str] = None
    notes: Optional[str] = None
    customer_id: Optional[str] = None
    answered_by: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CallListResponse(BaseModel):
    items: List[CallResponse]
    total: int
    page: int
    page_size: int


class CallDispositionResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    color: str
    is_active: bool
    is_default: bool
    display_order: int

    class Config:
        from_attributes = True


class SetDispositionRequest(BaseModel):
    disposition: str = Field(..., description="The disposition to set")
    notes: Optional[str] = Field(None, description="Optional notes about the call")


class CallAnalyticsResponse(BaseModel):
    call_volume_by_hour: dict
    missed_calls: int
    answered_calls: int
    total_calls: int
    avg_duration_seconds: float
    total_duration_seconds: int
    calls_by_direction: dict
    calls_by_disposition: dict


# Helper functions


def call_to_response(call: CallLog) -> dict:
    """Convert CallLog model to response dict."""
    return {
        "id": call.id,
        "ringcentral_call_id": call.ringcentral_call_id,
        "caller_number": call.caller_number,
        "called_number": call.called_number,
        "direction": call.direction,
        "call_disposition": call.call_disposition,
        "call_type": call.call_type,
        "call_date": call.call_date,
        "call_time": str(call.call_time) if call.call_time else None,
        "duration_seconds": call.duration_seconds,
        "ring_duration": call.ring_duration,
        "recording_url": call.recording_url,
        "notes": call.notes,
        "customer_id": call.customer_id,
        "answered_by": call.answered_by,
        "created_at": call.created_at,
    }


# Endpoints


@router.get("", response_model=CallListResponse)
async def list_calls(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    direction: Optional[str] = Query(None, description="Filter by direction: inbound, outbound"),
    disposition: Optional[str] = Query(None, description="Filter by disposition"),
    customer_id: Optional[str] = Query(None, description="Filter by customer"),
    date_from: Optional[date] = Query(None, description="Filter calls from this date"),
    date_to: Optional[date] = Query(None, description="Filter calls to this date"),
    search: Optional[str] = Query(None, description="Search by phone number"),
):
    """List call logs with filtering and pagination."""
    try:
        query = select(CallLog)

        # Apply filters
        if direction:
            query = query.where(CallLog.direction == direction)
        if disposition:
            query = query.where(CallLog.call_disposition == disposition)
        if customer_id:
            query = query.where(CallLog.customer_id == customer_id)
        if date_from:
            query = query.where(CallLog.call_date >= date_from)
        if date_to:
            query = query.where(CallLog.call_date <= date_to)
        if search:
            search_pattern = f"%{search}%"
            query = query.where(
                (CallLog.caller_number.ilike(search_pattern)) | (CallLog.called_number.ilike(search_pattern))
            )

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Paginate and order
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(CallLog.created_at.desc())

        result = await db.execute(query)
        calls = result.scalars().all()

        return {
            "items": [call_to_response(c) for c in calls],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    except Exception as e:
        logger.error(f"Error listing calls: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics", response_model=CallAnalyticsResponse)
async def get_call_analytics(
    db: DbSession,
    current_user: CurrentUser,
    date_from: Optional[date] = Query(None, description="Analytics from this date"),
    date_to: Optional[date] = Query(None, description="Analytics to this date"),
):
    """Get call analytics - call volume by hour, missed calls, avg duration."""
    try:
        # Default to last 7 days if no date range specified
        if not date_from:
            date_from = date.today() - timedelta(days=7)
        if not date_to:
            date_to = date.today()

        # Base query with date filter
        base_query = select(CallLog).where(CallLog.call_date >= date_from, CallLog.call_date <= date_to)

        # Get all calls in range
        result = await db.execute(base_query)
        calls = result.scalars().all()

        # Calculate metrics
        total_calls = len(calls)
        missed_calls = sum(1 for c in calls if c.call_disposition in ("no_answer", "busy", "missed"))
        answered_calls = sum(1 for c in calls if c.call_disposition in ("answered", "completed", "connected"))

        durations = [c.duration_seconds for c in calls if c.duration_seconds]
        total_duration = sum(durations)
        avg_duration = total_duration / len(durations) if durations else 0

        # Call volume by hour
        volume_by_hour = {}
        for c in calls:
            if c.call_time:
                hour = c.call_time.hour
                volume_by_hour[hour] = volume_by_hour.get(hour, 0) + 1

        # Calls by direction
        calls_by_direction = {}
        for c in calls:
            direction = c.direction or "unknown"
            calls_by_direction[direction] = calls_by_direction.get(direction, 0) + 1

        # Calls by disposition
        calls_by_disposition = {}
        for c in calls:
            disposition = c.call_disposition or "unknown"
            calls_by_disposition[disposition] = calls_by_disposition.get(disposition, 0) + 1

        return {
            "call_volume_by_hour": volume_by_hour,
            "missed_calls": missed_calls,
            "answered_calls": answered_calls,
            "total_calls": total_calls,
            "avg_duration_seconds": round(avg_duration, 2),
            "total_duration_seconds": total_duration,
            "calls_by_direction": calls_by_direction,
            "calls_by_disposition": calls_by_disposition,
        }
    except Exception as e:
        logger.error(f"Error getting call analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dispositions", response_model=List[CallDispositionResponse])
async def list_call_dispositions(
    db: DbSession,
    current_user: CurrentUser,
    active_only: bool = Query(True, description="Only return active dispositions"),
):
    """List all call dispositions."""
    try:
        query = select(CallDisposition)

        if active_only:
            query = query.where(CallDisposition.is_active == True)

        query = query.order_by(CallDisposition.display_order)

        result = await db.execute(query)
        dispositions = result.scalars().all()

        return [
            {
                "id": d.id,
                "name": d.name,
                "description": d.description,
                "color": d.color or "#6B7280",
                "is_active": d.is_active,
                "is_default": d.is_default,
                "display_order": d.display_order,
            }
            for d in dispositions
        ]
    except Exception as e:
        logger.error(f"Error listing call dispositions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dispositions/analytics")
async def get_disposition_analytics(
    db: DbSession,
    current_user: CurrentUser,
    date_from: Optional[date] = Query(None, description="Analytics from this date"),
    date_to: Optional[date] = Query(None, description="Analytics to this date"),
):
    """Get call disposition analytics."""
    try:
        # Default to last 30 days if no date range specified
        if not date_from:
            date_from = date.today() - timedelta(days=30)
        if not date_to:
            date_to = date.today()

        # Get all calls with dispositions in date range
        result = await db.execute(
            select(CallLog).where(
                CallLog.call_date >= date_from, CallLog.call_date <= date_to, CallLog.call_disposition.isnot(None)
            )
        )
        calls = result.scalars().all()

        # Count calls by disposition
        disposition_counts = {}
        total_calls = len(calls)

        for call in calls:
            disp = call.call_disposition or "unknown"
            disposition_counts[disp] = disposition_counts.get(disp, 0) + 1

        # Calculate percentages and format response
        disposition_stats = []
        for disposition, count in disposition_counts.items():
            percentage = (count / total_calls) * 100 if total_calls > 0 else 0
            disposition_stats.append(
                {
                    "disposition": disposition,
                    "count": count,
                    "percentage": round(percentage, 1),
                    "color": "#6B7280",  # Default color, could be customized
                }
            )

        # Sort by count descending
        disposition_stats.sort(key=lambda x: x["count"], reverse=True)

        return {
            "stats": disposition_stats,
            "total_calls": total_calls,
            "date_range": {"from": date_from.isoformat(), "to": date_to.isoformat()},
            "top_disposition": disposition_stats[0]["disposition"] if disposition_stats else None,
            "updated_at": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error getting disposition analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{call_id}", response_model=CallResponse)
async def get_call(
    call_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a specific call by ID."""
    try:
        result = await db.execute(select(CallLog).where(CallLog.id == call_id))
        call = result.scalar_one_or_none()

        if not call:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Call not found",
            )

        return call_to_response(call)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting call {call_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{call_id}/disposition")
async def set_call_disposition(
    call_id: int,
    request: SetDispositionRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Set the disposition for a call."""
    try:
        result = await db.execute(select(CallLog).where(CallLog.id == call_id))
        call = result.scalar_one_or_none()

        if not call:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Call not found",
            )

        # Validate disposition exists
        disp_result = await db.execute(
            select(CallDisposition).where(
                CallDisposition.name == request.disposition, CallDisposition.is_active == True
            )
        )
        disposition = disp_result.scalar_one_or_none()

        if not disposition:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid disposition: {request.disposition}",
            )

        # Update call
        call.call_disposition = request.disposition
        if request.notes:
            call.notes = request.notes

        await db.commit()
        await db.refresh(call)

        return {
            "status": "success",
            "call_id": call.id,
            "disposition": call.call_disposition,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting disposition for call {call_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
