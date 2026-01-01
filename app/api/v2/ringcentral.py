"""RingCentral API - VoIP integration for phone calls.

Features:
- Click-to-call from CRM
- Call log synchronization
- Recording management
- AI transcription of calls
- Presence/availability status
"""
from fastapi import APIRouter, HTTPException, status, Query, BackgroundTasks
from sqlalchemy import select, func, or_
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
import logging

from app.api.deps import DbSession, CurrentUser
from app.services.ringcentral_service import ringcentral_service
from app.services.ai_gateway import ai_gateway
from app.models.call_log import CallLog
from app.models.customer import Customer
from app.models.activity import Activity

logger = logging.getLogger(__name__)
router = APIRouter()


# Request/Response Models

class MakeCallRequest(BaseModel):
    to_number: str = Field(..., description="Phone number to call")
    from_number: Optional[str] = Field(None, description="Extension or number to call from")
    customer_id: Optional[str] = Field(None, description="Customer ID to link call to")


class CallLogResponse(BaseModel):
    id: str
    rc_call_id: Optional[str] = None
    from_number: str
    to_number: str
    direction: str
    status: str
    start_time: str
    duration_seconds: Optional[int] = None
    has_recording: bool = False
    transcription: Optional[str] = None
    ai_summary: Optional[str] = None
    sentiment: Optional[str] = None
    customer_id: Optional[str] = None
    notes: Optional[str] = None
    disposition: Optional[str] = None


class UpdateCallLogRequest(BaseModel):
    notes: Optional[str] = None
    disposition: Optional[str] = None
    customer_id: Optional[str] = None


class SyncCallsRequest(BaseModel):
    hours_back: int = Field(24, ge=1, le=168, description="Hours of history to sync")


# Helper functions

def call_log_to_response(call: CallLog) -> dict:
    """Convert CallLog model to response dict."""
    return {
        "id": str(call.id),
        "rc_call_id": call.rc_call_id,  # property -> ringcentral_call_id
        "from_number": call.from_number,  # property -> caller_number
        "to_number": call.to_number,  # property -> called_number
        "from_name": None,  # Not in DB
        "to_name": None,  # Not in DB
        "direction": call.direction,
        "status": call.status,  # property -> call_disposition
        "start_time": call.start_time.isoformat() if call.start_time else None,  # property
        "end_time": None,  # Not in DB
        "duration_seconds": call.duration_seconds,
        "has_recording": call.has_recording,  # property
        "recording_url": call.recording_url,
        "transcription": None,  # Not in DB
        "ai_summary": None,  # Not in DB
        "sentiment": None,  # Not in DB
        "sentiment_score": None,  # Not in DB
        "customer_id": str(call.customer_id) if call.customer_id else None,
        "contact_name": call.contact_name,  # property -> answered_by
        "notes": call.notes,
        "disposition": call.disposition,  # property -> call_disposition
        "created_at": call.created_at.isoformat() if call.created_at else None,
    }


async def find_customer_by_phone(db: DbSession, phone: str) -> Optional[Customer]:
    """Look up customer by phone number."""
    # Normalize phone number (remove non-digits)
    normalized = ''.join(c for c in phone if c.isdigit())
    if len(normalized) == 11 and normalized.startswith('1'):
        normalized = normalized[1:]  # Remove leading 1

    # Search customers
    result = await db.execute(
        select(Customer).where(
            or_(
                Customer.phone.contains(normalized[-10:]),
                Customer.mobile_phone.contains(normalized[-10:]) if hasattr(Customer, 'mobile_phone') else False,
            )
        ).limit(1)
    )
    return result.scalar_one_or_none()


async def create_activity_from_call(
    db: DbSession,
    call: CallLog,
    user_email: str,
) -> Optional[str]:
    """Create an activity record from a call log."""
    if not call.customer_id:
        return None

    description = f"{call.direction.capitalize()} call"
    if call.duration_seconds:
        minutes = call.duration_seconds // 60
        seconds = call.duration_seconds % 60
        description += f" ({minutes}m {seconds}s)"
    if call.disposition:
        description += f" - {call.disposition}"
    if call.ai_summary:
        description += f"\n\nSummary: {call.ai_summary}"

    activity = Activity(
        customer_id=call.customer_id,
        activity_type="call",
        description=description,
        created_by=user_email,
        activity_date=call.start_time,
    )
    db.add(activity)
    await db.flush()

    call.activity_id = str(activity.id)
    return str(activity.id)


# Endpoints

@router.get("/status")
async def get_ringcentral_status():
    """Get RingCentral connection status."""
    result = await ringcentral_service.get_status()
    return result


@router.get("/debug-db")
async def debug_database(db: DbSession):
    """DEBUG: Check call_logs table schema."""
    from sqlalchemy import text
    try:
        result = await db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'call_logs' ORDER BY ordinal_position"))
        columns = [row[0] for row in result.fetchall()]
        return {"table_exists": len(columns) > 0, "columns": columns}
    except Exception as e:
        return {"error": str(e)}


@router.get("/debug-config")
async def get_debug_config():
    """DEBUG: Check RingCentral configuration values."""
    try:
        from app.config import settings
        return {
            "client_id_set": bool(settings.RINGCENTRAL_CLIENT_ID),
            "client_id_len": len(settings.RINGCENTRAL_CLIENT_ID or ""),
            "client_id_preview": (settings.RINGCENTRAL_CLIENT_ID or "")[:4] + "..." if settings.RINGCENTRAL_CLIENT_ID else None,
            "client_secret_set": bool(settings.RINGCENTRAL_CLIENT_SECRET),
            "client_secret_len": len(settings.RINGCENTRAL_CLIENT_SECRET or ""),
            "server_url": settings.RINGCENTRAL_SERVER_URL,
            "jwt_token_set": bool(settings.RINGCENTRAL_JWT_TOKEN),
            "jwt_token_len": len(settings.RINGCENTRAL_JWT_TOKEN or ""),
            "jwt_token_preview": (settings.RINGCENTRAL_JWT_TOKEN or "")[:20] + "..." if settings.RINGCENTRAL_JWT_TOKEN else None,
            "service_configured": ringcentral_service.is_configured,
            "service_client_id_len": len(ringcentral_service.config.client_id or ""),
            "service_client_id_preview": (ringcentral_service.config.client_id or "")[:4] + "..." if ringcentral_service.config.client_id else None,
            "service_jwt_token_len": len(ringcentral_service.config.jwt_token or ""),
            "service_jwt_token_preview": (ringcentral_service.config.jwt_token or "")[:20] + "..." if ringcentral_service.config.jwt_token else None,
        }
    except Exception as e:
        return {"error": str(e), "type": type(e).__name__}


@router.post("/call")
async def make_call(
    request: MakeCallRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Initiate an outbound call (click-to-call)."""
    if not ringcentral_service.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RingCentral not configured",
        )

    # Default from number to user's extension
    from_number = request.from_number or getattr(current_user, 'phone_extension', None)
    if not from_number:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No from_number specified and user has no extension configured",
        )

    # Make the call via RingCentral
    result = await ringcentral_service.make_call(
        from_number=from_number,
        to_number=request.to_number,
    )

    if result.get("error"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result["error"],
        )

    # Create initial call log entry (using actual DB column names)
    now = datetime.utcnow()
    call_log = CallLog(
        ringcentral_call_id=result.get("id"),
        ringcentral_session_id=result.get("sessionId"),
        caller_number=from_number,
        called_number=request.to_number,
        direction="outbound",
        call_disposition="ringing",
        call_date=now.date(),
        call_time=now.time(),
        assigned_to=str(current_user.id),
        customer_id=int(request.customer_id) if request.customer_id else None,
    )

    # Try to find customer if not provided
    if not call_log.customer_id:
        customer = await find_customer_by_phone(db, request.to_number)
        if customer:
            call_log.customer_id = customer.id
            call_log.answered_by = f"{customer.first_name} {customer.last_name}".strip()

    db.add(call_log)
    await db.commit()
    await db.refresh(call_log)

    return {
        "status": "initiated",
        "call_log_id": str(call_log.id),
        "ringcentral_response": result,
    }


@router.get("/calls")
async def list_calls(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    direction: Optional[str] = None,
    customer_id: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
):
    """List call logs with filtering and pagination."""
    try:
        query = select(CallLog)

        if direction:
            query = query.where(CallLog.direction == direction)
        if customer_id:
            query = query.where(CallLog.customer_id == int(customer_id))
        if status_filter:
            # Use actual column name: call_disposition
            query = query.where(CallLog.call_disposition == status_filter)
        if date_from:
            # Use call_date for date filtering
            query = query.where(CallLog.call_date >= date_from.date())
        if date_to:
            query = query.where(CallLog.call_date <= date_to.date())

        # Count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Paginate - order by created_at since call_date/time may be null
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(CallLog.created_at.desc())

        result = await db.execute(query)
        calls = result.scalars().all()

        return {
            "items": [call_log_to_response(c) for c in calls],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    except Exception as e:
        logger.error(f"Error listing calls: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/calls/{call_id}")
async def get_call(
    call_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a specific call log."""
    result = await db.execute(select(CallLog).where(CallLog.id == call_id))
    call = result.scalar_one_or_none()

    if not call:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Call not found",
        )

    return call_log_to_response(call)


@router.patch("/calls/{call_id}")
async def update_call(
    call_id: str,
    request: UpdateCallLogRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update call log (notes, disposition, customer link)."""
    result = await db.execute(select(CallLog).where(CallLog.id == call_id))
    call = result.scalar_one_or_none()

    if not call:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Call not found",
        )

    update_data = request.model_dump(exclude_unset=True)
    if "customer_id" in update_data and update_data["customer_id"]:
        update_data["customer_id"] = int(update_data["customer_id"])

    for field, value in update_data.items():
        setattr(call, field, value)

    await db.commit()
    await db.refresh(call)

    return call_log_to_response(call)


@router.post("/calls/{call_id}/transcribe")
async def transcribe_call(
    call_id: str,
    background_tasks: BackgroundTasks,
    db: DbSession,
    current_user: CurrentUser,
):
    """Transcribe a call recording using AI."""
    result = await db.execute(select(CallLog).where(CallLog.id == call_id))
    call = result.scalar_one_or_none()

    if not call:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Call not found",
        )

    if not call.recording_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Call has no recording",
        )

    # Mark as pending
    call.transcription_status = "pending"
    await db.commit()

    # Queue transcription in background
    async def do_transcription():
        try:
            result = await ai_gateway.transcribe_audio(call.recording_url)
            if result.get("text"):
                call.transcription = result["text"]
                call.transcription_status = "completed"

                # Also generate summary and sentiment
                if len(result["text"]) > 50:
                    summary_result = await ai_gateway.summarize_text(
                        result["text"],
                        max_length=100,
                        style="concise",
                    )
                    call.ai_summary = summary_result.get("summary")

                    sentiment_result = await ai_gateway.analyze_sentiment(result["text"])
                    call.sentiment = sentiment_result.get("sentiment")
                    call.sentiment_score = sentiment_result.get("score")
            else:
                call.transcription_status = "failed"

            await db.commit()
        except Exception as e:
            logger.error(f"Transcription failed for call {call_id}: {e}")
            call.transcription_status = "failed"
            await db.commit()

    background_tasks.add_task(do_transcription)

    return {"status": "transcription_queued", "call_id": call_id}


@router.post("/sync")
async def sync_call_logs(
    request: SyncCallsRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Sync call logs from RingCentral."""
    if not ringcentral_service.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RingCentral not configured",
        )

    date_from = datetime.utcnow() - timedelta(hours=request.hours_back)

    rc_logs = await ringcentral_service.get_call_log(
        date_from=date_from,
        per_page=250,
    )

    if rc_logs.get("error"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=rc_logs["error"],
        )

    records = rc_logs.get("records", [])
    synced = 0
    skipped = 0

    for record in records:
        rc_call_id = record.get("id")

        # Check if already exists (using actual DB column name)
        existing = await db.execute(
            select(CallLog).where(CallLog.ringcentral_call_id == rc_call_id)
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue

        # Create new call log (using actual DB column names)
        from_info = record.get("from", {})
        to_info = record.get("to", {})

        # Parse start time
        start_dt = datetime.utcnow()
        if record.get("startTime"):
            start_dt = datetime.fromisoformat(record["startTime"].replace("Z", "+00:00"))

        call_log = CallLog(
            ringcentral_call_id=rc_call_id,
            ringcentral_session_id=record.get("sessionId"),
            caller_number=from_info.get("phoneNumber", ""),
            called_number=to_info.get("phoneNumber", ""),
            direction=record.get("direction", "").lower(),
            call_disposition=record.get("result", "unknown").lower(),
            call_type=record.get("type", "voice").lower(),
            call_date=start_dt.date(),
            call_time=start_dt.time(),
            duration_seconds=record.get("duration"),
        )

        # Check for recording
        recording = record.get("recording")
        if recording:
            call_log.recording_url = recording.get("contentUri")

        # Try to match customer
        search_number = call_log.called_number if call_log.direction == "outbound" else call_log.caller_number
        customer = await find_customer_by_phone(db, search_number)
        if customer:
            call_log.customer_id = customer.id
            call_log.answered_by = f"{customer.first_name} {customer.last_name}".strip()

        db.add(call_log)
        synced += 1

    await db.commit()

    return {
        "synced": synced,
        "skipped": skipped,
        "total_records": len(records),
    }


@router.get("/extensions")
async def list_extensions(
    current_user: CurrentUser,
):
    """List RingCentral extensions (users)."""
    if not ringcentral_service.is_configured:
        return {"items": [], "configured": False}

    result = await ringcentral_service.get_extensions()

    if result.get("error"):
        return {"items": [], "error": result["error"]}

    extensions = result.get("records", [])
    return {
        "items": [
            {
                "id": ext.get("id"),
                "extension_number": ext.get("extensionNumber"),
                "name": ext.get("name"),
                "email": ext.get("contact", {}).get("email"),
                "status": ext.get("status"),
            }
            for ext in extensions
        ],
    }


@router.get("/presence/{extension_id}")
async def get_presence(
    extension_id: str,
    current_user: CurrentUser,
):
    """Get user presence/availability status."""
    if not ringcentral_service.is_configured:
        return {"configured": False}

    result = await ringcentral_service.get_presence(extension_id)
    return result


@router.post("/presence/{extension_id}")
async def set_presence(
    extension_id: str,
    status: str = Query(..., description="Available, Busy, DoNotDisturb, Offline"),
    current_user: CurrentUser = None,
):
    """Set user presence status."""
    if not ringcentral_service.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RingCentral not configured",
        )

    result = await ringcentral_service.set_presence(status, extension_id)

    if result.get("error"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result["error"],
        )

    return result
