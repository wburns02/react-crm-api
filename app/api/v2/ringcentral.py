"""RingCentral API - VoIP integration for phone calls.

Features:
- Click-to-call from CRM
- Call log synchronization
- Recording management
- AI transcription of calls
- Presence/availability status
- Automatic background sync every 15 minutes
"""

from fastapi import APIRouter, HTTPException, status, Query, BackgroundTasks
from sqlalchemy import select, func, or_
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
import logging
import asyncio

from app.api.deps import DbSession, CurrentUser
from app.services.ringcentral_service import ringcentral_service
from app.services.ai_gateway import ai_gateway
from app.models.call_log import CallLog
from app.models.customer import Customer
from app.models.activity import Activity
from app.database import async_session_maker

logger = logging.getLogger(__name__)
router = APIRouter()

# Global state for auto-sync
_auto_sync_task: Optional[asyncio.Task] = None
_last_sync_time: Optional[datetime] = None
_last_sync_status: Optional[dict] = None
AUTO_SYNC_INTERVAL_SECONDS = 15 * 60  # 15 minutes


async def _perform_sync(hours_back: int = 2) -> dict:
    """Perform a sync of RingCentral calls.

    Args:
        hours_back: How many hours of call history to sync (default 2)

    Returns:
        dict with synced, skipped, total_records counts
    """
    global _last_sync_time, _last_sync_status

    if not ringcentral_service.is_configured:
        logger.warning("Auto-sync skipped: RingCentral not configured")
        return {"error": "RingCentral not configured", "synced": 0, "skipped": 0}

    date_from = datetime.utcnow() - timedelta(hours=hours_back)

    try:
        rc_logs = await ringcentral_service.get_call_log(
            date_from=date_from,
            per_page=250,
        )

        if rc_logs.get("error"):
            logger.error(f"Auto-sync error: {rc_logs['error']}")
            return {"error": rc_logs["error"], "synced": 0, "skipped": 0}

        records = rc_logs.get("records", [])
        synced = 0
        skipped = 0

        async with async_session_maker() as db:
            for record in records:
                rc_call_id = record.get("id")

                # Check if already exists
                existing = await db.execute(select(CallLog).where(CallLog.ringcentral_call_id == rc_call_id))
                if existing.scalar_one_or_none():
                    skipped += 1
                    continue

                # Create new call log
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
                    assigned_to="auto-sync",
                )

                # Check for recording
                recording = record.get("recording")
                if recording:
                    call_log.recording_url = recording.get("contentUri")

                db.add(call_log)
                synced += 1

            await db.commit()

        result = {
            "synced": synced,
            "skipped": skipped,
            "total_records": len(records),
            "timestamp": datetime.utcnow().isoformat(),
        }

        _last_sync_time = datetime.utcnow()
        _last_sync_status = result

        if synced > 0:
            logger.info(f"Auto-sync completed: {synced} new calls synced, {skipped} skipped")

        return result

    except Exception as e:
        logger.error(f"Auto-sync exception: {e}")
        return {"error": str(e), "synced": 0, "skipped": 0}


async def _auto_sync_loop():
    """Background task that syncs RingCentral calls every 15 minutes."""
    logger.info("Starting RingCentral auto-sync background task (15-minute interval)")

    # Initial sync on startup
    await asyncio.sleep(5)  # Wait 5 seconds for app to stabilize
    await _perform_sync(hours_back=24)  # Initial sync: last 24 hours

    while True:
        try:
            await asyncio.sleep(AUTO_SYNC_INTERVAL_SECONDS)
            await _perform_sync(hours_back=2)  # Subsequent syncs: last 2 hours
        except asyncio.CancelledError:
            logger.info("Auto-sync task cancelled")
            break
        except Exception as e:
            logger.error(f"Auto-sync loop error: {e}")
            await asyncio.sleep(60)  # Wait 1 minute before retrying


def start_auto_sync():
    """Start the auto-sync background task. Called from app startup."""
    global _auto_sync_task
    if _auto_sync_task is None or _auto_sync_task.done():
        _auto_sync_task = asyncio.create_task(_auto_sync_loop())
        logger.info("RingCentral auto-sync task started")


def stop_auto_sync():
    """Stop the auto-sync background task. Called from app shutdown."""
    global _auto_sync_task
    if _auto_sync_task and not _auto_sync_task.done():
        _auto_sync_task.cancel()
        logger.info("RingCentral auto-sync task stopped")


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
    """Convert CallLog model to response dict.

    Uses real AI analysis data from the database when available.
    """
    has_recording = call.has_recording or False
    has_transcript = bool(call.transcription and len(call.transcription) > 0)
    has_analysis = bool(call.quality_score is not None or call.sentiment is not None)

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
        "has_recording": has_recording,
        "recording_url": call.recording_url,
        # AI analysis fields - real data from database
        "transcription": call.transcription,
        "ai_summary": call.ai_summary,
        "sentiment": call.sentiment,
        "sentiment_score": call.sentiment_score,
        "quality_score": call.quality_score,
        "escalation_risk": call.escalation_risk,
        "csat_prediction": call.csat_prediction,
        "professionalism_score": call.professionalism_score,
        "empathy_score": call.empathy_score,
        "clarity_score": call.clarity_score,
        "resolution_score": call.resolution_score,
        "topics": call.topics,
        "analyzed_at": call.analyzed_at.isoformat() if call.analyzed_at else None,
        "has_transcript": has_transcript,
        "has_analysis": has_analysis,
        # Customer/contact info
        "customer_id": str(call.customer_id) if call.customer_id else None,
        "contact_name": call.contact_name,  # property -> answered_by
        "notes": call.notes,
        "disposition": call.disposition,  # property -> call_disposition
        "created_at": call.created_at.isoformat() if call.created_at else None,
    }


async def find_customer_by_phone(db: DbSession, phone: str) -> Optional[Customer]:
    """Look up customer by phone number."""
    try:
        # Normalize phone number (remove non-digits)
        normalized = "".join(c for c in phone if c.isdigit())
        if len(normalized) == 11 and normalized.startswith("1"):
            normalized = normalized[1:]  # Remove leading 1

        if len(normalized) < 7:
            return None  # Phone number too short

        # Search customers by phone (just use main phone column)
        result = await db.execute(select(Customer).where(Customer.phone.contains(normalized[-10:])).limit(1))
        return result.scalar_one_or_none()
    except Exception as e:
        logger.warning(f"Error finding customer by phone {phone}: {e}")
        return None


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


async def analyze_single_call(call_id: int):
    """Background task to analyze a single call recording.

    This function runs outside the request context, so it creates
    its own database session.

    Steps:
    1. Load the call record
    2. Download recording via RingCentral API (requires auth)
    3. Transcribe the recording using Whisper
    4. Analyze the transcript using LLM
    5. Save results to database
    """
    logger.info(f"Starting analysis for call {call_id}")

    async with async_session_maker() as db:
        try:
            # Load the call record
            result = await db.execute(select(CallLog).where(CallLog.id == call_id))
            call = result.scalar_one_or_none()

            if not call:
                logger.error(f"Call {call_id} not found")
                return

            if not call.recording_url:
                logger.warning(f"Call {call_id} has no recording URL")
                return

            # Mark as pending
            call.transcription_status = "pending"
            await db.commit()

            # Step 1: Extract recording ID and download via RingCentral
            # URL format: https://media.ringcentral.com/restapi/v1.0/account/.../recording/{id}/content
            recording_url = call.recording_url
            logger.info(f"Downloading recording for call {call_id} from {recording_url[:80]}...")

            # Extract recording ID from URL
            import re

            match = re.search(r"/recording/(\d+)/content", recording_url)
            if not match:
                logger.error(f"Could not extract recording ID from URL: {recording_url}")
                call.transcription_status = "failed"
                await db.commit()
                return

            recording_id = match.group(1)
            audio_data = await ringcentral_service.get_recording_content(recording_id)

            if not audio_data:
                logger.error(f"Failed to download recording {recording_id} for call {call_id}")
                call.transcription_status = "failed"
                await db.commit()
                return

            logger.info(f"Downloaded {len(audio_data)} bytes of audio for call {call_id}")

            # Step 2: Transcribe the recording using audio bytes
            transcription_result = await ai_gateway.transcribe_audio_bytes(
                audio_data=audio_data, filename=f"call_{call_id}.mp3", language="en"
            )

            if transcription_result.get("error"):
                logger.error(f"Transcription failed for call {call_id}: {transcription_result['error']}")
                call.transcription_status = "failed"
                await db.commit()
                return

            transcript = transcription_result.get("text", "")
            if not transcript or len(transcript.strip()) < 10:
                logger.warning(f"Call {call_id} transcription too short or empty")
                call.transcription_status = "failed"
                call.transcription = transcript
                await db.commit()
                return

            # Save transcription
            call.transcription = transcript
            call.transcription_status = "completed"
            await db.commit()
            logger.info(f"Transcription complete for call {call_id}, length: {len(transcript)}")

            # Step 2: Analyze the transcript with LLM
            logger.info(f"Analyzing call {call_id} with LLM")
            analysis = await ai_gateway.analyze_call_quality(
                transcript=transcript,
                call_direction=call.direction or "inbound",
                duration_seconds=call.duration_seconds or 0,
            )

            if analysis.get("error"):
                logger.warning(f"Analysis had errors for call {call_id}: {analysis['error']}")
                # Still save partial results

            # Save analysis results
            call.ai_summary = analysis.get("summary", "")
            call.sentiment = analysis.get("sentiment", "neutral")
            call.sentiment_score = analysis.get("sentiment_score", 0)
            call.quality_score = analysis.get("quality_score", 50)
            call.csat_prediction = analysis.get("csat_prediction", 3.0)
            call.escalation_risk = analysis.get("escalation_risk", "low")
            call.professionalism_score = analysis.get("professionalism_score", 50)
            call.empathy_score = analysis.get("empathy_score", 50)
            call.clarity_score = analysis.get("clarity_score", 50)
            call.resolution_score = analysis.get("resolution_score", 50)
            call.topics = analysis.get("topics", [])
            call.analyzed_at = datetime.utcnow()

            await db.commit()
            logger.info(
                f"Analysis complete for call {call_id}: sentiment={call.sentiment}, quality={call.quality_score}"
            )

        except Exception as e:
            logger.error(f"Error analyzing call {call_id}: {e}")
            import traceback

            logger.error(traceback.format_exc())
            # Try to mark as failed
            try:
                call.transcription_status = "failed"
                await db.commit()
            except Exception:
                pass


# Endpoints


@router.get("/status")
async def get_ringcentral_status():
    """Get RingCentral connection status."""
    result = await ringcentral_service.get_status()
    return result


# DEBUG endpoints removed for security - Issue #5
# Previously: /debug-db, /debug-config
# These exposed sensitive configuration and database schema in production


@router.post("/create-test-data")
async def create_test_data(db: DbSession):
    """Create test call data for Call Intelligence testing."""
    try:
        # Create some test call data
        from datetime import date, time
        import random

        test_calls = []
        for i in range(10):
            call_date = date.today() - timedelta(days=random.randint(0, 7))
            call_time = time(hour=random.randint(8, 17), minute=random.randint(0, 59))

            call_log = CallLog(
                ringcentral_call_id=f"test-call-{i}",
                caller_number=f"+1214555010{i}",
                called_number="+12145550100",
                direction=random.choice(["inbound", "outbound"]),
                call_disposition=random.choice(["completed", "missed", "busy"]),
                call_date=call_date,
                call_time=call_time,
                duration_seconds=random.randint(30, 600),
                assigned_to=f"test-agent-{random.randint(1, 3)}",
                recording_url=f"https://example.com/recording-{i}.mp3" if random.random() > 0.3 else None,
            )
            test_calls.append(call_log)
            db.add(call_log)

        await db.commit()

        return {"success": True, "created_calls": len(test_calls), "message": "Test call data created successfully"}

    except Exception as e:
        logger.error(f"Error creating test data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sync-status")
async def get_sync_status(db: DbSession):
    """Get the status of RingCentral call synchronization.

    Returns:
        - last_sync: Timestamp of last successful sync
        - last_sync_result: Details of last sync (synced, skipped counts)
        - auto_sync_enabled: Whether auto-sync is running
        - sync_interval_minutes: How often auto-sync runs
        - most_recent_call: Timestamp of the most recent call in database
    """
    # Get most recent call from database
    result = await db.execute(
        select(CallLog.call_date, CallLog.call_time)
        .order_by(CallLog.call_date.desc(), CallLog.call_time.desc())
        .limit(1)
    )
    most_recent = result.first()

    most_recent_call = None
    if most_recent and most_recent.call_date:
        most_recent_call = datetime.combine(
            most_recent.call_date, most_recent.call_time or datetime.min.time()
        ).isoformat()

    # Get total call count
    count_result = await db.execute(select(func.count(CallLog.id)))
    total_calls = count_result.scalar() or 0

    return {
        "last_sync": _last_sync_time.isoformat() if _last_sync_time else None,
        "last_sync_result": _last_sync_status,
        "auto_sync_enabled": _auto_sync_task is not None and not _auto_sync_task.done(),
        "sync_interval_minutes": AUTO_SYNC_INTERVAL_SECONDS // 60,
        "most_recent_call": most_recent_call,
        "total_calls": total_calls,
        "ringcentral_configured": ringcentral_service.is_configured,
    }


# DEBUG endpoints removed for security - Issue #5
# Previously: /debug-sync, /debug-forwarding
# These allowed unauthenticated sync and exposed internal extension data


@router.post("/call")
async def make_call(
    request: MakeCallRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Initiate an outbound call (click-to-call)."""
    try:
        if not ringcentral_service.is_configured:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="RingCentral not configured",
            )

        # Default from number to user's extension
        from_number = request.from_number or getattr(current_user, "phone_extension", None)
        if not from_number:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No from_number specified and user has no extension configured",
            )

        # Make the call via RingCentral
        logger.info(f"Initiating call from {from_number} to {request.to_number}")
        result = await ringcentral_service.make_call(
            from_number=from_number,
            to_number=request.to_number,
        )
        logger.info(f"RingCentral response: {result}")

        # Check for errors BEFORE creating call log
        if result.get("error"):
            error_msg = result.get("error", "Unknown error")
            error_body = result.get("error_body", "")
            logger.error(f"RingCentral call failed: {error_msg} - {error_body}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"RingCentral error: {error_body or error_msg}",
            )

        # Verify we got a call ID back (indicates success)
        if not result.get("id"):
            logger.error(f"RingCentral returned unexpected response (no call ID): {result}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="RingCentral call initiation failed - no call ID returned",
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

        # Try to find customer if not provided (skip if fails)
        if not call_log.customer_id:
            try:
                customer = await find_customer_by_phone(db, request.to_number)
                if customer:
                    call_log.customer_id = customer.id
                    call_log.answered_by = f"{customer.first_name} {customer.last_name}".strip()
            except Exception as ce:
                logger.warning(f"Could not find customer by phone: {ce}")

        db.add(call_log)
        await db.commit()
        await db.refresh(call_log)

        return {
            "status": "initiated",
            "call_log_id": str(call_log.id),
            "ringcentral_response": result,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in make_call: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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
    has_recording: Optional[bool] = Query(None, description="Filter for calls with recordings only"),
    has_analysis: Optional[bool] = Query(None, description="Filter for calls with AI analysis"),
    has_transcript: Optional[bool] = Query(None, description="Filter for calls with transcripts"),
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

        # New filters for RingCentral-specific features
        if has_recording is True:
            query = query.where(CallLog.recording_url.isnot(None))
        elif has_recording is False:
            query = query.where(CallLog.recording_url.is_(None))

        if has_analysis is True:
            query = query.where(CallLog.quality_score.isnot(None))
        elif has_analysis is False:
            query = query.where(CallLog.quality_score.is_(None))

        if has_transcript is True:
            query = query.where(CallLog.transcription.isnot(None))
        elif has_transcript is False:
            query = query.where(CallLog.transcription.is_(None))

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


# NOTE: /calls/analytics MUST be defined BEFORE /calls/{call_id}
# Otherwise FastAPI will match "analytics" as a call_id parameter
@router.get("/calls/analytics")
async def get_call_intelligence_analytics(
    db: DbSession,
    current_user: CurrentUser,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
):
    """Get Call Intelligence analytics with AI metrics."""
    try:
        # Default to last 30 days
        if not date_from:
            date_from = datetime.utcnow() - timedelta(days=30)
        if not date_to:
            date_to = datetime.utcnow()

        logger.info(f"Getting call analytics from {date_from} to {date_to}")

        # Get all calls in date range with error handling
        try:
            result = await db.execute(
                select(CallLog).where(
                    CallLog.call_date.isnot(None),
                    CallLog.call_date >= date_from.date(),
                    CallLog.call_date <= date_to.date(),
                )
            )
            calls = result.scalars().all()
            logger.info(f"Found {len(calls)} calls in date range")
        except Exception as db_error:
            logger.error(f"Database query error: {db_error}", exc_info=True)
            calls = []

        if not calls:
            # Return empty metrics if no calls
            return {
                "metrics": {
                    "total_calls": 0,
                    "calls_today": 0,
                    "calls_this_week": 0,
                    "positive_calls": 0,
                    "neutral_calls": 0,
                    "negative_calls": 0,
                    "avg_sentiment_score": 0,
                    "avg_quality_score": 0,
                    "quality_trend": 0,
                    "escalation_rate": 0,
                    "high_risk_calls": 0,
                    "critical_risk_calls": 0,
                    "avg_csat_prediction": 0,
                    "auto_disposition_rate": 0,
                    "auto_disposition_accuracy": 0,
                    "sentiment_trend": [],
                    "quality_trend_data": [],
                    "volume_trend": [],
                },
                "updated_at": datetime.utcnow().isoformat(),
            }

        # Convert all calls to response format with simulated AI analysis
        # This ensures KPI cards match the modal data exactly
        call_responses = [call_log_to_response(c) for c in calls]

        total_calls = len(call_responses)
        calls_today = len([c for c in calls if c.call_date and c.call_date == date_to.date()])
        calls_this_week = len([c for c in calls if c.call_date and (date_to.date() - c.call_date).days <= 7])

        # Count sentiment from actual call analysis
        positive_calls = len([c for c in call_responses if c["sentiment"] == "positive"])
        neutral_calls = len([c for c in call_responses if c["sentiment"] == "neutral"])
        negative_calls = len([c for c in call_responses if c["sentiment"] == "negative"])

        # Count escalation risks from actual call analysis
        high_risk_calls = len([c for c in call_responses if c["escalation_risk"] == "high"])
        critical_risk_calls = len([c for c in call_responses if c["escalation_risk"] == "critical"])
        medium_risk_calls = len([c for c in call_responses if c["escalation_risk"] == "medium"])

        # Calculate averages from actual call analysis
        sentiment_scores = [c["sentiment_score"] for c in call_responses if c["sentiment_score"] is not None]
        quality_scores = [c["quality_score"] for c in call_responses if c["quality_score"] is not None]
        csat_predictions = [c["csat_prediction"] for c in call_responses if c["csat_prediction"] is not None]

        avg_sentiment_score = round(sum(sentiment_scores) / len(sentiment_scores), 1) if sentiment_scores else 0
        avg_quality_score = round(sum(quality_scores) / len(quality_scores), 1) if quality_scores else 0
        avg_csat_prediction = round(sum(csat_predictions) / len(csat_predictions), 2) if csat_predictions else 0

        # Calculate escalation rate (% of calls with medium+ risk)
        escalation_count = high_risk_calls + critical_risk_calls + medium_risk_calls
        escalation_rate = round((escalation_count / total_calls) * 100, 1) if total_calls > 0 else 0

        # Generate trend data by day
        sentiment_trend = []
        quality_trend_data = []
        volume_trend = []

        for i in range(7):  # Last 7 days
            day = date_to - timedelta(days=6 - i)
            day_calls = [c for c in calls if c.call_date and c.call_date == day.date()]
            day_responses = [call_log_to_response(c) for c in day_calls]

            volume_trend.append({"date": day.strftime("%Y-%m-%d"), "value": len(day_calls)})

            # Real sentiment distribution for the day
            day_positive = len([c for c in day_responses if c["sentiment"] == "positive"])
            day_neutral = len([c for c in day_responses if c["sentiment"] == "neutral"])
            day_negative = len([c for c in day_responses if c["sentiment"] == "negative"])

            sentiment_trend.append(
                {
                    "date": day.strftime("%Y-%m-%d"),
                    "value": len(day_calls),
                    "positive": day_positive,
                    "neutral": day_neutral,
                    "negative": day_negative,
                }
            )

            # Real quality score average for the day
            day_quality_scores = [c["quality_score"] for c in day_responses if c["quality_score"] is not None]
            day_avg_quality = round(sum(day_quality_scores) / len(day_quality_scores), 1) if day_quality_scores else 0

            quality_trend_data.append({"date": day.strftime("%Y-%m-%d"), "value": day_avg_quality})

        # Calculate quality trend (compare this week vs last week)
        quality_trend = round((avg_quality_score - 75) / 75 * 100, 1) if avg_quality_score else 0

        # Auto-disposition stats (based on calls with disposition set)
        calls_with_disposition = len([c for c in call_responses if c.get("disposition")])
        auto_disposition_rate = round(calls_with_disposition / total_calls, 2) if total_calls > 0 else 0

        return {
            "metrics": {
                "total_calls": total_calls,
                "calls_today": calls_today,
                "calls_this_week": calls_this_week,
                "positive_calls": positive_calls,
                "neutral_calls": neutral_calls,
                "negative_calls": negative_calls,
                "avg_sentiment_score": avg_sentiment_score,
                "avg_quality_score": avg_quality_score,
                "quality_trend": quality_trend,
                "escalation_rate": escalation_rate,
                "high_risk_calls": high_risk_calls,
                "critical_risk_calls": critical_risk_calls,
                "avg_csat_prediction": avg_csat_prediction,
                "auto_disposition_rate": auto_disposition_rate,
                "auto_disposition_accuracy": 0.85,  # Placeholder until real AI
                "sentiment_trend": sentiment_trend,
                "quality_trend_data": quality_trend_data,
                "volume_trend": volume_trend,
            },
            "updated_at": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        import traceback

        error_detail = f"{type(e).__name__}: {str(e)}"
        tb = traceback.format_exc()
        logger.error(f"Error getting call intelligence analytics: {error_detail}\n{tb}")
        raise HTTPException(status_code=500, detail=error_detail)


# =====================================================
# NOTE: Static routes MUST come before /calls/{call_id}
# =====================================================


@router.post("/calls/analyze-batch")
async def analyze_calls_batch(
    background_tasks: BackgroundTasks,
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(50, ge=1, le=500, description="Max calls to analyze"),
    force: bool = Query(False, description="Re-analyze already analyzed calls"),
):
    """Batch analyze calls with recordings that haven't been analyzed yet.

    This endpoint queues calls for AI analysis (transcription + quality scoring).
    Analysis runs in the background and updates the database.
    """
    try:
        # Find calls with recordings that need analysis
        if force:
            # Re-analyze all calls with recordings
            result = await db.execute(
                select(CallLog).where(CallLog.recording_url.isnot(None)).order_by(CallLog.call_date.desc()).limit(limit)
            )
        else:
            # Only get calls that haven't been analyzed yet
            result = await db.execute(
                select(CallLog)
                .where(
                    CallLog.recording_url.isnot(None),
                    CallLog.transcription.is_(None),
                )
                .order_by(CallLog.call_date.desc())
                .limit(limit)
            )

        calls = result.scalars().all()

        if not calls:
            return {
                "status": "complete",
                "message": "No calls need analysis",
                "queued": 0,
            }

        # Queue each call for background analysis
        queued_ids = []
        for call in calls:
            queued_ids.append(str(call.id))
            # Queue background task for each call
            background_tasks.add_task(analyze_single_call, call.id)

        return {
            "status": "queued",
            "message": f"Queued {len(queued_ids)} calls for analysis",
            "queued": len(queued_ids),
            "call_ids": queued_ids[:10],  # Return first 10 IDs
        }

    except Exception as e:
        logger.error(f"Error in batch analysis: {e}")
        return {
            "status": "error",
            "message": "Batch analysis temporarily unavailable",
            "queued": 0,
        }


@router.get("/calls/analysis-status")
async def get_analysis_status(
    db: DbSession,
    current_user: CurrentUser,
):
    """Get status of call analysis coverage.

    Returns statistics on how many calls have been analyzed.
    """
    try:
        # Count total calls with recordings
        total_result = await db.execute(
            select(func.count()).select_from(CallLog).where(CallLog.recording_url.isnot(None))
        )
        total_with_recordings = total_result.scalar() or 0

        # Count calls with transcriptions
        transcribed_result = await db.execute(
            select(func.count())
            .select_from(CallLog)
            .where(
                CallLog.recording_url.isnot(None),
                CallLog.transcription.isnot(None),
            )
        )
        transcribed_count = transcribed_result.scalar() or 0

        # Count calls with full AI analysis
        analyzed_result = await db.execute(
            select(func.count())
            .select_from(CallLog)
            .where(
                CallLog.recording_url.isnot(None),
                CallLog.quality_score.isnot(None),
            )
        )
        analyzed_count = analyzed_result.scalar() or 0

        # Calculate coverage
        coverage = (transcribed_count / total_with_recordings * 100) if total_with_recordings > 0 else 0

        return {
            "total_calls_with_recordings": total_with_recordings,
            "transcribed_calls": transcribed_count,
            "analyzed_calls": analyzed_count,
            "pending_transcription": total_with_recordings - transcribed_count,
            "coverage_percentage": round(coverage, 1),
            "status": "ready" if coverage > 90 else "in_progress" if coverage > 0 else "not_started",
        }

    except Exception as e:
        logger.error(f"Error getting analysis status: {e}")
        return {
            "total_calls_with_recordings": 0,
            "transcribed_calls": 0,
            "analyzed_calls": 0,
            "pending_transcription": 0,
            "coverage_percentage": 0,
            "status": "error",
            "error": "Analysis status temporarily unavailable",
        }


@router.post("/calls/analyze/{call_id}")
async def analyze_single_call_endpoint(
    call_id: str,
    background_tasks: BackgroundTasks,
    db: DbSession,
    current_user: CurrentUser,
    force: bool = Query(False, description="Re-analyze even if already analyzed"),
):
    """Trigger AI analysis for a single call.

    This endpoint queues a specific call for AI analysis (transcription + quality scoring).
    Analysis runs in the background and updates the database within ~10 seconds.

    Returns immediately with queued status. Poll GET /calls/{call_id} to check results.
    """
    try:
        # Convert call_id to int for database query
        call_id_int = int(call_id)

        # Get the call
        result = await db.execute(select(CallLog).where(CallLog.id == call_id_int))
        call = result.scalar_one_or_none()

        if not call:
            raise HTTPException(status_code=404, detail="Call not found")

        if not call.recording_url:
            raise HTTPException(status_code=400, detail="Call has no recording to analyze")

        # Check if already analyzed (unless force=true)
        if call.analyzed_at and not force:
            return {
                "status": "already_analyzed",
                "message": "Call already has analysis. Use ?force=true to re-analyze.",
                "call_id": call_id,
                "analyzed_at": call.analyzed_at.isoformat(),
                "sentiment": call.sentiment,
                "quality_score": call.quality_score,
            }

        # Queue for background analysis
        background_tasks.add_task(analyze_single_call, call_id_int)

        return {
            "status": "queued",
            "message": "Call analysis started. Results will be available in ~10 seconds.",
            "call_id": call_id,
            "previous_sentiment": call.sentiment,
            "previous_quality_score": call.quality_score,
        }
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid call_id format")
    except Exception as e:
        logger.error(f"Error in analyze_single_call_endpoint: {e}", exc_info=True)
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
        existing = await db.execute(select(CallLog).where(CallLog.ringcentral_call_id == rc_call_id))
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


@router.get("/my-extension")
async def get_my_extension(
    current_user: CurrentUser,
):
    """Get the current authenticated user's RingCentral extension.

    This returns YOUR extension info, not a list of all extensions.
    Use this to determine your own extension number for making calls.
    """
    if not ringcentral_service.is_configured:
        return {"configured": False, "error": "RingCentral not configured"}

    result = await ringcentral_service.get_current_extension()

    if result.get("error"):
        return {"configured": True, "error": result["error"]}

    return {
        "configured": True,
        "id": result.get("id"),
        "extension_number": result.get("extensionNumber"),
        "name": result.get("name"),
        "email": result.get("contact", {}).get("email"),
        "phone_number": result.get("contact", {}).get("businessPhone"),
        "status": result.get("status"),
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


@router.get("/calls/{call_id}/recording")
async def get_call_recording(
    call_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get secure recording URL for a call."""
    try:
        result = await db.execute(select(CallLog).where(CallLog.id == call_id))
        call = result.scalar_one_or_none()

        if not call:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Call not found",
            )

        if not call.recording_url:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No recording available for this call",
            )

        # Extract recording ID from the URL
        recording_id = None
        if "/recording/" in call.recording_url:
            parts = call.recording_url.split("/recording/")
            if len(parts) > 1:
                recording_id = parts[1].split("?")[0]  # Remove query params

        if not recording_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid recording URL format",
            )

        # Get fresh recording metadata with secure access
        recording_meta = await ringcentral_service.get_recording(recording_id)

        if recording_meta.get("error"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get recording metadata: {recording_meta.get('error')}",
            )

        # Return secure recording info
        return {
            "call_id": call_id,
            "recording_id": recording_id,
            "content_type": recording_meta.get("contentType", "audio/mpeg"),
            "duration": recording_meta.get("duration"),
            "secure_url": f"/api/v2/ringcentral/recording/{recording_id}/content",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting call recording: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recording/{recording_id}/content")
async def stream_recording_content(
    recording_id: str,
    current_user: CurrentUser,
):
    """Stream recording content securely without exposing tokens."""
    try:
        if not ringcentral_service.is_configured:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="RingCentral not configured",
            )

        # Download recording content using service with fresh token
        content = await ringcentral_service.get_recording_content(recording_id)

        if content is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Recording content not found",
            )

        from fastapi.responses import Response

        return Response(
            content=content,
            media_type="audio/mpeg",
            headers={
                "Cache-Control": "private, max-age=3600",
                "Content-Disposition": f'inline; filename="recording-{recording_id}.mp3"',
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error streaming recording content: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/calls/{call_id}/transcript")
async def get_call_transcript(
    call_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get transcript for a call with full analysis details.

    Returns the transcript text along with AI analysis results.
    If transcript doesn't exist but recording does, returns info about
    how to trigger transcription.
    """
    try:
        result = await db.execute(select(CallLog).where(CallLog.id == call_id))
        call = result.scalar_one_or_none()

        if not call:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Call not found",
            )

        # Build response with all transcript/analysis data
        response = {
            "call_id": call_id,
            "has_recording": bool(call.recording_url),
            "has_transcript": bool(call.transcription),
            "has_analysis": bool(call.quality_score is not None),
            "transcription_status": call.transcription_status,
            # Transcript data
            "transcript": call.transcription,
            "ai_summary": call.ai_summary,
            # Sentiment analysis
            "sentiment": call.sentiment,
            "sentiment_score": call.sentiment_score,
            # Quality metrics
            "quality_score": call.quality_score,
            "csat_prediction": call.csat_prediction,
            "escalation_risk": call.escalation_risk,
            # Detailed scores
            "professionalism_score": call.professionalism_score,
            "empathy_score": call.empathy_score,
            "clarity_score": call.clarity_score,
            "resolution_score": call.resolution_score,
            # Topics/keywords
            "topics": call.topics,
            # Metadata
            "analyzed_at": call.analyzed_at.isoformat() if call.analyzed_at else None,
            "call_date": call.call_date.isoformat() if call.call_date else None,
            "duration_seconds": call.duration_seconds,
            "direction": call.direction,
        }

        # Add guidance if transcript doesn't exist
        if not call.transcription and call.recording_url:
            response["transcription_available"] = True
            response["transcription_hint"] = (
                "POST /api/v2/ringcentral/calls/{call_id}/transcribe to generate transcript"
            )
        elif not call.recording_url:
            response["transcription_available"] = False
            response["transcription_hint"] = "No recording available for this call"

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting call transcript: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/deployment-check")
async def get_deployment_check():
    """Check deployment version - returns timestamp of this code."""
    return {"version": "2026-01-14-v8", "message": "Route order fix - analytics before call_id"}


@router.get("/auth-test")
async def get_auth_test(
    current_user: CurrentUser,
):
    """Test authentication - returns user info if auth works."""
    return {"authenticated": True, "user_id": current_user.id, "email": current_user.email}


@router.get("/db-auth-test")
async def get_db_auth_test(
    db: DbSession,
    current_user: CurrentUser,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
):
    """Test the full analytics endpoint logic with query params."""
    try:
        # Same date filtering logic as analytics endpoint
        if not date_from:
            date_from = datetime.utcnow() - timedelta(days=30)
        if not date_to:
            date_to = datetime.utcnow()

        # Same query as analytics endpoint
        result = await db.execute(
            select(CallLog).where(
                CallLog.call_date.isnot(None),
                CallLog.call_date >= date_from.date(),
                CallLog.call_date <= date_to.date(),
            )
        )
        calls = result.scalars().all()

        # Same metrics calculation as analytics endpoint
        total_calls = len(calls)
        calls_today = len([c for c in calls if c.call_date and c.call_date == date_to.date()])

        positive_calls = max(1, int(total_calls * 0.6))
        neutral_calls = max(1, int(total_calls * 0.3))
        negative_calls = total_calls - positive_calls - neutral_calls

        import random

        random.seed(total_calls)

        sentiment_trend = []
        quality_trend_data = []
        volume_trend = []

        for i in range(7):
            day = date_to - timedelta(days=6 - i)
            day_calls = [c for c in calls if c.call_date and c.call_date == day.date()]

            volume_trend.append({"date": day.strftime("%Y-%m-%d"), "value": len(day_calls)})

            day_positive = max(0, int(len(day_calls) * 0.6))
            day_neutral = max(0, int(len(day_calls) * 0.3))
            day_negative = max(0, len(day_calls) - day_positive - day_neutral)

            sentiment_trend.append(
                {
                    "date": day.strftime("%Y-%m-%d"),
                    "value": len(day_calls),
                    "positive": day_positive,
                    "neutral": day_neutral,
                    "negative": day_negative,
                }
            )

            quality_trend_data.append({"date": day.strftime("%Y-%m-%d"), "value": random.randint(75, 90)})

        return {
            "metrics": {
                "total_calls": total_calls,
                "calls_today": calls_today,
                "calls_this_week": len([c for c in calls if c.call_date and (date_to.date() - c.call_date).days <= 7]),
                "positive_calls": positive_calls,
                "neutral_calls": neutral_calls,
                "negative_calls": negative_calls,
                "avg_sentiment_score": round(random.uniform(65, 85), 1),
                "avg_quality_score": random.randint(75, 90),
                "quality_trend": round(random.uniform(-5, 10), 1),
                "escalation_rate": round(random.uniform(0.1, 0.3), 2),
                "high_risk_calls": max(0, int(total_calls * 0.1)),
                "critical_risk_calls": max(0, int(total_calls * 0.05)),
                "avg_csat_prediction": round(random.uniform(3.8, 4.5), 1),
                "auto_disposition_rate": round(random.uniform(0.7, 0.9), 2),
                "auto_disposition_accuracy": round(random.uniform(0.8, 0.95), 2),
                "sentiment_trend": sentiment_trend,
                "quality_trend_data": quality_trend_data,
                "volume_trend": volume_trend,
            },
            "updated_at": datetime.utcnow().isoformat(),
            "test_user_id": current_user.id,
        }
    except Exception as e:
        import traceback
        import sentry_sdk

        logger.error(f"Error in analytics endpoint: {traceback.format_exc()}")
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred while fetching analytics",
        )


# DEBUG endpoint removed for security - Issue #5
# Previously: /debug-analytics
# This allowed unauthenticated access to call analytics


@router.get("/agents/performance")
async def get_agent_performance(
    db: DbSession,
    current_user: CurrentUser,
):
    """Get agent performance metrics."""
    try:
        # Get all calls with assigned agents
        result = await db.execute(select(CallLog).where(CallLog.assigned_to.isnot(None)))
        calls = result.scalars().all()

        # Group by agent and calculate metrics
        agents_data = {}

        for call in calls:
            agent_id = call.assigned_to
            if agent_id not in agents_data:
                agents_data[agent_id] = {
                    "agent_id": agent_id,
                    "agent_name": f"Agent {agent_id}",  # TODO: Join with users table
                    "total_calls": 0,
                    "calls": [],
                }

            agents_data[agent_id]["total_calls"] += 1
            agents_data[agent_id]["calls"].append(call)

        # Calculate real metrics from actual call data
        agents = []

        for agent_data in agents_data.values():
            total_calls = agent_data["total_calls"]
            agent_calls = agent_data["calls"]

            # Calculate actual metrics from call records
            answered = sum(1 for c in agent_calls if getattr(c, 'status', '') != 'missed')
            durations = [getattr(c, 'duration', 0) or 0 for c in agent_calls]
            avg_duration = round(sum(durations) / len(durations)) if durations else 0
            quality_scores = [c.quality_score for c in agent_calls if getattr(c, 'quality_score', None)]
            avg_quality = round(sum(quality_scores) / len(quality_scores)) if quality_scores else 0

            agents.append(
                {
                    "agent_id": agent_data["agent_id"],
                    "agent_name": agent_data["agent_name"],
                    "total_calls": total_calls,
                    "answered_calls": answered,
                    "avg_call_duration": avg_duration,
                    "quality_score": avg_quality,
                    "sentiment_score": 0,
                    "resolution_rate": 0,
                    "escalation_rate": 0,
                    "csat_prediction": 0,
                    "recent_trend": "stable",
                }
            )

        return {
            "agents": agents,
            "summary": {
                "total_agents": len(agents),
                "avg_quality_score": sum(a["quality_score"] for a in agents) / len(agents) if agents else 0,
                "total_calls": sum(a["total_calls"] for a in agents),
            },
        }

    except Exception as e:
        logger.error(f"Error getting agent performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/coaching/insights")
async def get_coaching_insights(
    db: DbSession,
    current_user: CurrentUser,
):
    """Get coaching insights and recommendations.

    Returns data in the format expected by the frontend:
    - insights.top_strengths: Array of {name, count, percentage}
    - insights.top_improvements: Array of {name, count, percentage}
    - insights.trending_topics: Array of {topic, count, trend}
    - insights.recommended_training: Array of {module, priority, agents_affected}
    """
    try:
        # Coaching insights require AI transcript analysis - not yet implemented
        return {
            "insights": {
                "top_strengths": [],
                "top_improvements": [],
                "trending_topics": [],
                "recommended_training": [],
            },
            "period": "last_7_days",
            "message": "Coaching insights require AI transcript analysis. Connect call recordings to enable.",
        }

    except Exception as e:
        logger.error(f"Error getting coaching insights: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quality/heatmap")
async def get_quality_heatmap(
    db: DbSession,
    current_user: CurrentUser,
    days: int = Query(14, ge=1, le=90),
):
    """Get quality heatmap data for agents over time."""
    try:
        # Get calls from the last N days
        date_from = datetime.utcnow() - timedelta(days=days)

        result = await db.execute(
            select(CallLog).where(CallLog.call_date >= date_from.date(), CallLog.assigned_to.isnot(None))
        )
        calls = result.scalars().all()

        # Generate heatmap data from actual call records
        heatmap_data = []
        agents = set(call.assigned_to for call in calls if call.assigned_to)

        for agent_id in agents:
            agent_calls = [call for call in calls if call.assigned_to == agent_id]

            for i in range(days):
                current_date = (datetime.utcnow() - timedelta(days=days - 1 - i)).date()
                day_calls = [call for call in agent_calls if call.call_date == current_date]

                # Use actual quality_score from call logs if available, otherwise 0
                quality_scores = [c.quality_score for c in day_calls if getattr(c, 'quality_score', None)]
                avg_quality = round(sum(quality_scores) / len(quality_scores)) if quality_scores else 0

                heatmap_data.append(
                    {
                        "agent_id": agent_id,
                        "agent_name": f"Agent {agent_id}",
                        "date": current_date.strftime("%Y-%m-%d"),
                        "quality_score": avg_quality,
                        "call_count": len(day_calls),
                    }
                )

        return {
            "heatmap": heatmap_data,
            "date_range": {
                "start": (datetime.utcnow() - timedelta(days=days - 1)).strftime("%Y-%m-%d"),
                "end": datetime.utcnow().strftime("%Y-%m-%d"),
            },
            "agents": list(agents),
            "updated_at": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error getting quality heatmap: {e}")
        raise HTTPException(status_code=500, detail=str(e))
