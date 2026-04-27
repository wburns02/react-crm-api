"""Twilio API - Voice calling endpoints.

Provides endpoints for making calls via Twilio as an alternative to RingCentral.
Includes browser-based calling via Twilio Voice SDK (Access Token + TwiML App).
"""

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from typing import Optional
import logging

from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant
from twilio.twiml.voice_response import VoiceResponse

from app.api.deps import DbSession, CurrentUser
from app.services.twilio_service import TwilioService
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# Create service instance
twilio_service = TwilioService()


class MakeCallRequest(BaseModel):
    to_number: str = Field(..., description="Phone number to call")
    from_number: Optional[str] = Field(None, description="Caller ID. If set, overrides smart routing.")
    customer_id: Optional[str] = Field(None, description="Customer ID to link call to")
    record: bool = Field(True, description="Whether to record the call")
    from_market: Optional[str] = Field(
        None,
        description=(
            "Caller-ID market selector. 'auto' (or omitted) routes by destination area code. "
            "Region values: 'TN', 'TX', 'SC'. Specific markets: 'TN_NASHVILLE', 'TN_COLUMBIA', "
            "'TX_AUSTIN', 'SC_COLUMBIA'. Ignored if from_number is set."
        ),
    )


@router.get("/status")
async def get_twilio_status():
    """Get Twilio connection status."""
    return twilio_service.get_status()


# Static routes BEFORE catch-all routes (per backend rules).
@router.get("/numbers")
async def list_twilio_numbers(current_user: CurrentUser):
    """List configured Twilio caller-ID numbers grouped by market.

    Used by the dialer UI to render the TN/TX/SC picker. Auto-routing reads the
    same set when no override is provided.
    """
    return twilio_service.list_caller_ids()


@router.post("/preview-caller-id")
async def preview_caller_id(
    request: MakeCallRequest,
    current_user: CurrentUser,
):
    """Preview which caller ID smart routing would pick for a given destination.

    Helpful for showing 'Will dial from X' before the agent clicks Call.
    """
    pick = twilio_service.pick_caller_id(
        to_number=request.to_number,
        market_override=request.from_market,
    )
    return pick


@router.post("/call")
async def make_call(
    request: MakeCallRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Make an outbound call via Twilio.

    Unlike RingCentral RingOut, Twilio makes a direct call to the destination
    without ringing your phone first. Caller ID is auto-routed by destination
    area code unless `from_number` or `from_market` is provided.
    """
    if not twilio_service.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Twilio not configured",
        )

    result = await twilio_service.make_call(
        to_number=request.to_number,
        from_number=request.from_number,
        record=request.record,
        market_override=request.from_market,
    )

    if result.get("error"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Twilio error: {result['error']}",
        )

    return result


@router.get("/calls")
async def list_calls(
    current_user: CurrentUser,
    limit: int = 50,
):
    """List recent calls from Twilio."""
    return await twilio_service.get_call_logs(limit=limit)


@router.get("/recordings")
async def list_recordings(
    current_user: CurrentUser,
    call_sid: Optional[str] = None,
    limit: int = 50,
):
    """List call recordings from Twilio."""
    return await twilio_service.get_recordings(call_sid=call_sid, limit=limit)


# ============ Browser-Based Calling (Voice SDK) ============


def _voice_sdk_configured() -> bool:
    """Check if all env vars for browser Voice SDK are present."""
    return all([
        settings.TWILIO_ACCOUNT_SID,
        settings.TWILIO_API_KEY_SID,
        settings.TWILIO_API_KEY_SECRET,
        settings.TWILIO_TWIML_APP_SID,
    ])


@router.get("/token")
async def get_voice_token(current_user: CurrentUser):
    """Generate a Twilio Access Token for browser-based Voice SDK calling."""
    if not _voice_sdk_configured():
        return {"error": "Twilio Voice SDK not configured", "token": None}

    identity = current_user.email or str(current_user.id)
    token = AccessToken(
        settings.TWILIO_ACCOUNT_SID,
        settings.TWILIO_API_KEY_SID,
        settings.TWILIO_API_KEY_SECRET,
        identity=identity,
        ttl=3600,
    )
    voice_grant = VoiceGrant(
        outgoing_application_sid=settings.TWILIO_TWIML_APP_SID,
        incoming_allow=True,
    )
    token.add_grant(voice_grant)

    return {"token": token.to_jwt()}


@router.post("/voice")
async def twilio_voice_webhook(request: Request):
    """TwiML webhook — Twilio calls this when the browser SDK initiates a call.

    No auth required (Twilio calls this directly).
    - Creates a CallLog row at call start, attributed to the CRM user identified
      by the Voice SDK token's identity (email or numeric id, sent in 'From')
    - Enables dual-channel recording so the Call Library populates
    - Wires status + recording callbacks so subsequent webhooks can update
      this exact row by CallSid
    - Optionally injects <Start><Stream> for Google STT live transcription
    """
    from datetime import date as _date, datetime as _dt
    from sqlalchemy import select as _select
    from app.database import async_session_maker as _session_maker
    from app.models.call_log import CallLog as _CallLog
    from app.models.user import User as _User
    import uuid as _uuid

    form = await request.form()
    to_number = form.get("To", "")
    call_sid = form.get("CallSid", "")
    from_identity = form.get("From", "")  # e.g. "client:dannia@macseptic.com"

    if not to_number:
        logger.warning("Twilio voice webhook called without To number")
        return Response(
            content="<Response><Say>No destination number provided.</Say></Response>",
            media_type="application/xml",
        )

    # Resolve the CRM user from the Voice SDK identity. Token is created in
    # /token with identity = current_user.email or str(current_user.id), so the
    # 'From' header on the TwiML POST will be "client:<identity>".
    user_id_str = "1"  # fallback: treat as Will
    identity = from_identity.replace("client:", "").strip() if from_identity else ""
    if identity and call_sid:
        try:
            async with _session_maker() as db:
                if "@" in identity:
                    res = await db.execute(
                        _select(_User).where(_User.email == identity).limit(1)
                    )
                else:
                    try:
                        res = await db.execute(
                            _select(_User).where(_User.id == int(identity)).limit(1)
                        )
                    except ValueError:
                        res = None
                user = res.scalar_one_or_none() if res is not None else None
                if user is not None:
                    user_id_str = str(user.id)
        except Exception as e:
            logger.warning("Voice SDK identity lookup failed: %s", e)

    # Insert a CallLog row for this outbound call so the Call Library and
    # downstream reporting can see it. Idempotent: skip if a row already exists
    # for this CallSid (Twilio retries in some failure modes).
    if call_sid:
        try:
            async with _session_maker() as db:
                existing = await db.execute(
                    _select(_CallLog).where(
                        _CallLog.ringcentral_call_id == call_sid,
                        _CallLog.external_system == "twilio",
                    ).limit(1)
                )
                if existing.scalar_one_or_none() is None:
                    now = _dt.utcnow()
                    db.add(_CallLog(
                        id=_uuid.uuid4(),
                        ringcentral_call_id=call_sid,
                        caller_number=settings.TWILIO_PHONE_NUMBER or "",
                        called_number=str(to_number),
                        user_id=user_id_str,
                        direction="outbound",
                        call_type="voice",
                        call_disposition="ringing",
                        call_date=now.date(),
                        call_time=now.time(),
                        duration_seconds=0,
                        external_system="twilio",
                    ))
                    await db.commit()
                    logger.info(
                        "Created outbound CallLog",
                        extra={"call_sid": call_sid, "user_id": user_id_str},
                    )
        except Exception as e:
            # Never block the call on a logging failure.
            logger.error("Failed to insert outbound CallLog: %s", e, exc_info=True)

    logger.info(f"Twilio browser voice webhook: dialing {to_number}")
    response = VoiceResponse()

    # Inject media stream for live STT when enabled
    if settings.GOOGLE_STT_ENABLED and settings.GOOGLE_STT_CREDENTIALS_JSON and call_sid:
        proto = request.headers.get("x-forwarded-proto", "https")
        host = request.headers.get("x-forwarded-host", request.headers.get("host", ""))
        ws_proto = "wss" if proto == "https" else "ws"
        stream_url = f"{ws_proto}://{host}/ws/twilio-media/{call_sid}"
        caller_number = form.get("From", "")
        called_number = form.get("To", "")
        start = response.start()
        stream = start.stream(url=stream_url, track="outbound_track")
        stream.parameter(name="caller_number", value=caller_number)
        stream.parameter(name="called_number", value=called_number)
        logger.info("Injected media stream: %s (caller=%s, called=%s)", stream_url, caller_number, called_number)

    # Build absolute callback URLs so Twilio can update the CallLog as the call
    # progresses (status) and when a recording becomes available.
    proto = request.headers.get("x-forwarded-proto", "https")
    host = request.headers.get("x-forwarded-host", request.headers.get("host", ""))
    base = f"{proto}://{host}" if host else ""
    voice_status_url = f"{base}/webhooks/twilio/voice-status" if base else None
    recording_status_url = f"{base}/webhooks/twilio/recording-status" if base else None

    dial_kwargs = {"caller_id": settings.TWILIO_PHONE_NUMBER}
    if voice_status_url:
        dial_kwargs["action"] = voice_status_url
        dial_kwargs["method"] = "POST"
    # Enable dual-channel recording so the Call Library has audio to play back.
    dial_kwargs["record"] = "record-from-answer-dual"
    if recording_status_url:
        dial_kwargs["recording_status_callback"] = recording_status_url
        dial_kwargs["recording_status_callback_method"] = "POST"

    dial = response.dial(**dial_kwargs)
    dial.number(str(to_number))
    return Response(content=str(response), media_type="application/xml")
