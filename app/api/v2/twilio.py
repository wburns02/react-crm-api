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
    from_number: Optional[str] = Field(None, description="Caller ID (defaults to Twilio number)")
    customer_id: Optional[str] = Field(None, description="Customer ID to link call to")
    record: bool = Field(True, description="Whether to record the call")


@router.get("/status")
async def get_twilio_status():
    """Get Twilio connection status."""
    return twilio_service.get_status()


@router.post("/call")
async def make_call(
    request: MakeCallRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Make an outbound call via Twilio.

    Unlike RingCentral RingOut, Twilio makes a direct call to the destination
    without ringing your phone first.
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
    Reads 'To' from form data, returns TwiML XML.
    """
    form = await request.form()
    to_number = form.get("To", "")

    if not to_number:
        logger.warning("Twilio voice webhook called without To number")
        return Response(
            content="<Response><Say>No destination number provided.</Say></Response>",
            media_type="application/xml",
        )

    logger.info(f"Twilio browser voice webhook: dialing {to_number}")
    response = VoiceResponse()
    dial = response.dial(caller_id=settings.TWILIO_PHONE_NUMBER)
    dial.number(str(to_number))
    return Response(content=str(response), media_type="application/xml")
