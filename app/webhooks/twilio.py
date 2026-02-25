"""
Twilio Webhook Handlers

SECURITY:
- All webhook endpoints validate Twilio signature
- Invalid signatures are rejected with 403
- No sensitive data is logged
"""

from fastapi import APIRouter, Request, HTTPException, Response, Depends, BackgroundTasks
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import httpx
import logging
import uuid
from datetime import date, datetime, timezone

from app.database import async_session_maker
from app.models.message import Message, MessageStatus
from app.models.call_log import CallLog
from app.models.customer import Customer
from app.models.work_order import WorkOrder
from app.config import settings
from app.security.twilio_validator import validate_twilio_signature
from app.services.websocket_manager import manager

logger = logging.getLogger(__name__)

twilio_router = APIRouter()


@twilio_router.post("/incoming")
async def handle_incoming_sms(
    request: Request,
    _signature_valid: bool = Depends(validate_twilio_signature),
):
    """
    Handle incoming SMS from Twilio.

    SECURITY: Validates X-Twilio-Signature before processing.

    Routes messages based on source:
    - If message is a reply to a React-originated message -> handle here
    - If message is a reply to a Legacy-originated message -> forward to legacy backend
    """
    form_data = await request.form()

    message_sid = form_data.get("MessageSid")
    from_number = form_data.get("From")
    to_number = form_data.get("To")
    body = form_data.get("Body", "")

    # SECURITY: Don't log message content or full phone numbers
    logger.info(
        "Incoming SMS received",
        extra={"message_sid": message_sid, "from_suffix": from_number[-4:] if from_number else None},
    )

    # Try to find if this is a reply to an existing conversation
    async with async_session_maker() as db:
        # Look for recent messages to this phone number
        result = await db.execute(
            select(Message).where(Message.to_address == from_number).order_by(Message.created_at.desc()).limit(1)
        )
        last_message = result.scalar_one_or_none()

        if last_message and last_message.source == "react":
            # This is a reply to a React message - handle it
            logger.info("Processing React reply", extra={"customer_id": last_message.customer_id})

            # Create incoming message record
            incoming = Message(
                customer_id=last_message.customer_id,
                type="sms",
                direction="inbound",
                status=MessageStatus.received,
                to_address=to_number,
                from_address=from_number,
                content=body,
                twilio_sid=message_sid,
                source="react",
            )
            db.add(incoming)
            await db.commit()

            # Return TwiML response (empty = no auto-reply)
            return Response(
                content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
                media_type="application/xml",
            )

        else:
            # Forward to legacy backend
            logger.info("Forwarding to legacy backend")
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{settings.LEGACY_BACKEND_URL}/twilio/incoming",
                        data=dict(form_data),
                        timeout=10.0,
                    )
                    return Response(
                        content=response.content,
                        status_code=response.status_code,
                        media_type=response.headers.get("content-type", "application/xml"),
                    )
            except httpx.RequestError as e:
                logger.error(f"Failed to forward to legacy: {type(e).__name__}")
                # Still return success to Twilio to prevent retries
                return Response(
                    content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
                    media_type="application/xml",
                )


@twilio_router.post("/status")
async def handle_status_callback(
    request: Request,
    _signature_valid: bool = Depends(validate_twilio_signature),
):
    """
    Handle Twilio status callbacks.

    SECURITY: Validates X-Twilio-Signature before processing.

    Updates message status when Twilio reports delivery status changes.
    """
    form_data = await request.form()

    message_sid = form_data.get("MessageSid")
    message_status = form_data.get("MessageStatus")
    error_code = form_data.get("ErrorCode")
    error_message = form_data.get("ErrorMessage")

    # SECURITY: Don't log error messages which might contain PII
    logger.info("Status callback received", extra={"message_sid": message_sid, "status": message_status})

    async with async_session_maker() as db:
        # Find the message
        result = await db.execute(select(Message).where(Message.twilio_sid == message_sid))
        message = result.scalar_one_or_none()

        if message:
            # Only update if it's a React message
            if message.source == "react":
                # Map Twilio status to our status
                status_map = {
                    "queued": MessageStatus.queued,
                    "sending": MessageStatus.queued,
                    "sent": MessageStatus.sent,
                    "delivered": MessageStatus.delivered,
                    "undelivered": MessageStatus.failed,
                    "failed": MessageStatus.failed,
                }

                message.status = status_map.get(message_status, message.status)
                message.twilio_status = message_status

                if error_code:
                    message.error_code = error_code
                    message.error_message = error_message

                await db.commit()
                logger.info(
                    "Message status updated", extra={"message_id": message.id, "new_status": message.status.value}
                )
            else:
                # Forward to legacy
                logger.info("Forwarding status to legacy")
                try:
                    async with httpx.AsyncClient() as client:
                        await client.post(
                            f"{settings.LEGACY_BACKEND_URL}/twilio/status",
                            data=dict(form_data),
                            timeout=10.0,
                        )
                except httpx.RequestError as e:
                    logger.error(f"Failed to forward status to legacy: {type(e).__name__}")
        else:
            # Message not found in React DB - might be legacy
            logger.info("Message not found, forwarding to legacy")
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        f"{settings.LEGACY_BACKEND_URL}/twilio/status",
                        data=dict(form_data),
                        timeout=10.0,
                    )
            except httpx.RequestError as e:
                logger.error(f"Failed to forward status to legacy: {type(e).__name__}")

    return {"status": "ok"}


def _normalize_phone(raw: str) -> str:
    """Normalize +1XXXXXXXXXX to (XXX) XXX-XXXX for DB lookup."""
    digits = "".join(c for c in (raw or "") if c.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return raw or ""


@twilio_router.post("/voice")
async def handle_incoming_voice(
    request: Request,
    background_tasks: BackgroundTasks,
    _signature_valid: bool = Depends(validate_twilio_signature),
):
    """
    Handle incoming voice call from Twilio.

    - Looks up caller in customers table
    - Creates CallLog record
    - Broadcasts screen pop via WebSocket
    - Returns TwiML to dial forward number with recording
    """
    form_data = await request.form()

    call_sid = form_data.get("CallSid", "")
    from_number = form_data.get("From", "")
    to_number = form_data.get("To", "")

    logger.info("Incoming voice call", extra={"call_sid": call_sid, "from_suffix": from_number[-4:] if from_number else None})

    normalized = _normalize_phone(from_number)

    async with async_session_maker() as db:
        # Look up customer by phone
        customer = None
        customer_data = None
        last_service_data = None
        open_wo_data = []

        result = await db.execute(
            select(Customer).where(
                or_(Customer.phone == normalized, Customer.phone == from_number)
            ).limit(1)
        )
        customer = result.scalar_one_or_none()

        if customer:
            customer_data = {
                "id": str(customer.id),
                "name": f"{customer.first_name or ''} {customer.last_name or ''}".strip(),
                "address": f"{customer.address_line1 or ''}, {customer.city or ''}, {customer.state or ''}".strip(", "),
                "email": customer.email,
                "phone": customer.phone,
            }

            # Last completed service
            last_wo_result = await db.execute(
                select(WorkOrder)
                .where(WorkOrder.customer_id == customer.id, WorkOrder.status == "completed")
                .order_by(WorkOrder.scheduled_date.desc())
                .limit(1)
            )
            last_wo = last_wo_result.scalar_one_or_none()
            if last_wo:
                last_service_data = {
                    "id": str(last_wo.id),
                    "job_type": last_wo.job_type,
                    "date": str(last_wo.scheduled_date) if last_wo.scheduled_date else None,
                    "status": last_wo.status,
                }

            # Open work orders
            open_wo_result = await db.execute(
                select(WorkOrder)
                .where(
                    WorkOrder.customer_id == customer.id,
                    WorkOrder.status.notin_(["completed", "canceled"]),
                )
                .order_by(WorkOrder.scheduled_date.asc())
            )
            for wo in open_wo_result.scalars():
                open_wo_data.append({
                    "id": str(wo.id),
                    "job_type": wo.job_type,
                    "status": wo.status,
                    "scheduled_date": str(wo.scheduled_date) if wo.scheduled_date else None,
                })

        # Create CallLog
        call_log = CallLog(
            id=uuid.uuid4(),
            direction="inbound",
            call_type="voice",
            caller_number=from_number,
            called_number=to_number,
            customer_id=customer.id if customer else None,
            call_date=date.today(),
            call_disposition="ringing",
            external_system="twilio",
            user_id="1",
        )
        db.add(call_log)
        await db.commit()

        call_log_id = str(call_log.id)

    # Broadcast screen pop
    ws_payload = {
        "call_sid": call_sid,
        "caller_number": from_number,
        "caller_display": normalized,
        "customer": customer_data,
        "last_service": last_service_data,
        "open_work_orders": open_wo_data,
        "call_log_id": call_log_id,
    }
    background_tasks.add_background_task(manager.broadcast_event, "incoming_call", ws_payload)

    # Return TwiML — dial forward number with recording
    forward = settings.TWILIO_FORWARD_NUMBER
    base_url = str(request.base_url).rstrip("/")
    # Use forwarded headers for public URL
    proto = request.headers.get("x-forwarded-proto", "https")
    host = request.headers.get("x-forwarded-host", request.headers.get("host", ""))
    public_base = f"{proto}://{host}" if host else base_url

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Dial record="record-from-answer-dual"
        recordingStatusCallback="{public_base}/webhooks/twilio/recording-status"
        recordingStatusCallbackMethod="POST"
        action="{public_base}/webhooks/twilio/voice-status">
    {forward}
  </Dial>
</Response>"""

    return Response(content=twiml, media_type="application/xml")


@twilio_router.post("/voice-status")
async def handle_voice_status(
    request: Request,
    _signature_valid: bool = Depends(validate_twilio_signature),
):
    """Handle voice call status updates (ringing → in-progress → completed)."""
    form_data = await request.form()

    call_sid = form_data.get("CallSid", "")
    call_status = form_data.get("CallStatus", "")  # completed, busy, no-answer, failed, canceled
    duration = form_data.get("CallDuration") or form_data.get("Duration")

    logger.info("Voice status callback", extra={"call_sid": call_sid, "status": call_status})

    # Map Twilio status to disposition
    disposition_map = {
        "completed": "answered",
        "busy": "busy",
        "no-answer": "no-answer",
        "failed": "failed",
        "canceled": "canceled",
    }

    async with async_session_maker() as db:
        # Find by caller_number match on recent calls (CallSid not stored as column)
        # Find most recent ringing call log
        result = await db.execute(
            select(CallLog)
            .where(CallLog.external_system == "twilio", CallLog.call_disposition == "ringing")
            .order_by(CallLog.created_at.desc())
            .limit(1)
        )
        call_log = result.scalar_one_or_none()

        if call_log:
            call_log.call_disposition = disposition_map.get(call_status, call_status)
            if duration:
                try:
                    call_log.duration_seconds = int(duration)
                except (ValueError, TypeError):
                    pass
            await db.commit()

            # Broadcast call ended
            await manager.broadcast_event("call_ended", {
                "call_sid": call_sid,
                "call_log_id": str(call_log.id),
                "duration": call_log.duration_seconds,
                "disposition": call_log.call_disposition,
            })

    # Return TwiML (Twilio expects XML from action URL)
    return Response(
        content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        media_type="application/xml",
    )


@twilio_router.post("/recording-status")
async def handle_recording_status(
    request: Request,
    background_tasks: BackgroundTasks,
    _signature_valid: bool = Depends(validate_twilio_signature),
):
    """Handle recording ready callback — save URL and kick off AI analysis."""
    form_data = await request.form()

    recording_url = form_data.get("RecordingUrl", "")
    recording_duration = form_data.get("RecordingDuration")
    call_sid = form_data.get("CallSid", "")

    logger.info("Recording status callback", extra={"call_sid": call_sid, "duration": recording_duration})

    async with async_session_maker() as db:
        # Find the most recent call log with twilio external_system
        result = await db.execute(
            select(CallLog)
            .where(CallLog.external_system == "twilio")
            .order_by(CallLog.created_at.desc())
            .limit(1)
        )
        call_log = result.scalar_one_or_none()

        if call_log:
            call_log.recording_url = recording_url
            if recording_duration:
                try:
                    call_log.duration_seconds = int(recording_duration)
                except (ValueError, TypeError):
                    pass
            call_log.transcription_status = "pending"
            await db.commit()

            # Kick off AI analysis in background
            if settings.VOICE_AI_ENABLED:
                from app.services.call_analysis_service import analyze_call
                background_tasks.add_background_task(analyze_call, str(call_log.id))

    return {"status": "ok"}
