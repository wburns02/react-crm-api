"""Twilio API - Voice calling endpoints.

Provides endpoints for making calls via Twilio as an alternative to RingCentral.
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional
import logging

from app.api.deps import DbSession, CurrentUser
from app.services.twilio_service import TwilioService

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
