"""RingCentral Webhook Handlers — Inbound SMS + Delivery Status + Call Recordings.

Handles:
- RC subscription validation (Validation-Token handshake)
- Inbound SMS via /message-store events
- Call recording completed events (for AI Interaction Analyzer)
- Creates Message records and broadcasts WebSocket events
"""

from fastapi import APIRouter, Request, Response
from sqlalchemy import select, or_
import logging
import uuid
from datetime import datetime, timezone

from app.database import async_session_maker
from app.models.message import Message
from app.models.customer import Customer
from app.models.call_log import CallLog
from app.config import settings
from app.services.websocket_manager import manager
from app.services.ai.queue import enqueue_interaction_analysis

logger = logging.getLogger(__name__)

ringcentral_webhook_router = APIRouter()


def _last10(raw: str) -> str:
    """Strip non-digits, return last 10 digits (for phone matching)."""
    digits = "".join(c for c in (raw or "") if c.isdigit())
    return digits[-10:] if len(digits) >= 10 else digits


def _normalize_phone(raw: str) -> str:
    """Normalize +1XXXXXXXXXX to (XXX) XXX-XXXX for DB lookup."""
    digits = "".join(c for c in (raw or "") if c.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return raw or ""


@ringcentral_webhook_router.post("/sms")
async def handle_ringcentral_sms(request: Request):
    """Handle RingCentral webhook events for SMS.

    RingCentral sends a Validation-Token header during subscription setup.
    We must echo it back in the response header to prove we own the endpoint.

    For actual events, we process /message-store notifications for inbound SMS.
    """
    # --- RC subscription verification handshake ---
    validation_token = request.headers.get("Validation-Token")
    if validation_token:
        logger.info("RingCentral webhook validation handshake")
        return Response(
            content="",
            status_code=200,
            headers={"Validation-Token": validation_token},
        )

    # --- Process event payload ---
    try:
        payload = await request.json()
    except Exception:
        logger.warning("RingCentral webhook: invalid JSON body")
        return {"status": "ignored", "reason": "invalid json"}

    event = payload.get("event", "")
    body = payload.get("body", {})

    # We only care about message-store events (SMS)
    if "/message-store" not in event:
        logger.debug("RingCentral webhook: ignoring non-SMS event %s", event)
        return {"status": "ignored", "reason": "not message-store"}

    # Extract message details
    direction = (body.get("direction") or "").lower()  # "Inbound" or "Outbound"
    msg_type = (body.get("type") or "").lower()  # "SMS", "Pager", etc.
    msg_status = body.get("messageStatus", "")
    rc_message_id = str(body.get("id", ""))

    # For outbound messages, this is a delivery status update
    if direction == "outbound":
        return await _handle_delivery_status(rc_message_id, msg_status)

    # For inbound SMS only
    if direction != "inbound" or msg_type != "sms":
        return {"status": "ignored", "reason": f"direction={direction}, type={msg_type}"}

    from_number = ""
    to_number = ""

    from_entries = body.get("from", {})
    if isinstance(from_entries, dict):
        from_number = from_entries.get("phoneNumber", "")

    to_entries = body.get("to", [])
    if isinstance(to_entries, list) and to_entries:
        to_number = to_entries[0].get("phoneNumber", "")
    elif isinstance(to_entries, dict):
        to_number = to_entries.get("phoneNumber", "")

    text = body.get("subject", "") or ""

    logger.info(
        "Inbound SMS via RingCentral",
        extra={"from_suffix": from_number[-4:] if from_number else None, "rc_id": rc_message_id},
    )

    # Intercept: if the sender is a configured live-chat admin, route their
    # text as an agent reply to the chat instead of treating it as a
    # customer-originated SMS.
    try:
        from app.api.v2.live_chat import post_sms_reply_to_chat
        chat_result = await post_sms_reply_to_chat(from_number, text)
    except Exception as e:
        logger.warning(f"Chat SMS reply routing failed: {e}")
        chat_result = None

    if chat_result and chat_result.get("handled"):
        logger.info(
            "Inbound SMS routed to live chat",
            extra={"routed": chat_result.get("routed"), "conv": chat_result.get("conversation_id")},
        )
        return {"status": "ok", "routed_to_chat": True, **chat_result}

    normalized = _normalize_phone(from_number)

    async with async_session_maker() as db:
        # Look up customer by phone number
        customer = None
        result = await db.execute(
            select(Customer).where(
                or_(Customer.phone == normalized, Customer.phone == from_number)
            ).limit(1)
        )
        customer = result.scalar_one_or_none()

        # Create inbound message record
        incoming = Message(
            id=uuid.uuid4(),
            customer_id=customer.id if customer else None,
            message_type="sms",
            direction="inbound",
            status="received",
            from_number=from_number,
            to_number=to_number,
            content=text,
            external_id=rc_message_id,
        )
        db.add(incoming)
        await db.commit()

        # Broadcast WebSocket event for real-time UI
        ws_payload = {
            "message_id": str(incoming.id),
            "from_number": from_number,
            "to_number": to_number,
            "content": text,
            "customer_id": str(customer.id) if customer else None,
            "customer_name": (
                f"{customer.first_name or ''} {customer.last_name or ''}".strip()
                if customer else None
            ),
            "received_at": datetime.now(timezone.utc).isoformat(),
        }
        await manager.broadcast_event("sms_received", ws_payload)

    return {"status": "ok"}


async def _handle_delivery_status(rc_message_id: str, msg_status: str):
    """Update outbound message status from RingCentral delivery callback."""
    if not rc_message_id:
        return {"status": "ignored", "reason": "no message id"}

    # Map RC statuses to our internal statuses
    status_map = {
        "Queued": "queued",
        "Sent": "sent",
        "Delivered": "delivered",
        "DeliveryFailed": "failed",
        "SendingFailed": "failed",
        "Received": "received",
    }

    new_status = status_map.get(msg_status)
    if not new_status:
        return {"status": "ignored", "reason": f"unknown status: {msg_status}"}

    async with async_session_maker() as db:
        result = await db.execute(
            select(Message).where(Message.external_id == rc_message_id)
        )
        message = result.scalar_one_or_none()

        if message:
            message.status = new_status
            if new_status == "delivered":
                message.delivered_at = datetime.now(timezone.utc)
            await db.commit()
            logger.info("RC delivery status updated: %s -> %s", rc_message_id, new_status)
        else:
            logger.debug("RC delivery status for unknown message: %s", rc_message_id)

    return {"status": "ok"}


@ringcentral_webhook_router.post("/calls")
async def handle_ringcentral_call_recording(request: Request):
    """Handle RingCentral webhook events for call-log / recording-completed events.

    Validation-Token handshake is identical to /sms.

    For events, we filter to recording-completed call-log notifications,
    upsert a row in call_logs keyed by ringcentral_call_id, attempt to
    match a customer by phone (last-10-digit normalization), then enqueue
    the interaction-analyzer worker.
    """
    # --- RC subscription verification handshake ---
    validation_token = request.headers.get("Validation-Token")
    if validation_token:
        logger.info("RingCentral /calls webhook validation handshake")
        return Response(
            content="",
            status_code=200,
            headers={"Validation-Token": validation_token},
        )

    # --- Process event payload ---
    try:
        payload = await request.json()
    except Exception:
        logger.warning("RingCentral /calls webhook: invalid JSON body")
        return {"status": "ignored", "reason": "invalid json"}

    event = payload.get("event", "") or ""
    body = payload.get("body", {}) or {}

    # Only act on call-log / recording events.
    # RC's call-log webhook fires when a recording becomes available; the
    # event filter typically looks like
    #   /restapi/v1.0/account/~/extension/~/call-log
    # and the body carries a `recording` block when available.
    is_call_log = "/call-log" in event or "call-log" in event
    has_recording_marker = "recording" in event.lower()
    recording = body.get("recording") or {}

    if not (is_call_log or has_recording_marker) or not recording:
        logger.debug(
            "RingCentral /calls webhook: ignoring non-recording event %s", event
        )
        return {"status": "ignored", "reason": "not a recording event"}

    # Extract the call identifiers + payload.
    rc_call_id = str(body.get("id") or body.get("sessionId") or "").strip()
    rc_session_id = str(body.get("sessionId") or "").strip() or None
    if not rc_call_id:
        return {"status": "ignored", "reason": "missing call id"}

    recording_url = (
        recording.get("contentUri")
        or recording.get("uri")
        or recording.get("link")
        or ""
    )

    direction_raw = (body.get("direction") or "").lower()
    if direction_raw == "inbound":
        direction = "inbound"
    elif direction_raw == "outbound":
        direction = "outbound"
    else:
        direction = direction_raw or None

    # from / to phone numbers
    from_entry = body.get("from") or {}
    to_entry = body.get("to") or {}
    if isinstance(from_entry, list) and from_entry:
        from_entry = from_entry[0]
    if isinstance(to_entry, list) and to_entry:
        to_entry = to_entry[0]
    caller_number = (from_entry or {}).get("phoneNumber", "") if isinstance(from_entry, dict) else ""
    called_number = (to_entry or {}).get("phoneNumber", "") if isinstance(to_entry, dict) else ""

    # duration + start time
    duration_seconds = body.get("duration")
    try:
        duration_seconds = int(duration_seconds) if duration_seconds is not None else None
    except (TypeError, ValueError):
        duration_seconds = None

    start_time_raw = body.get("startTime") or ""
    call_date = None
    call_time = None
    if start_time_raw:
        try:
            # RC ISO timestamps may end in "Z"
            iso = start_time_raw.replace("Z", "+00:00")
            dt = datetime.fromisoformat(iso)
            call_date = dt.date()
            call_time = dt.time().replace(tzinfo=None)
        except (ValueError, AttributeError):
            logger.debug("RC /calls: unparseable startTime=%r", start_time_raw)

    # Identify the phone number to match a customer with
    match_number = caller_number if direction == "inbound" else called_number
    match_last10 = _last10(match_number)

    async with async_session_maker() as db:
        customer_id = None
        if match_last10:
            # Find any customer whose phone (after last-10 normalization) matches
            cust_result = await db.execute(select(Customer.id, Customer.phone))
            for cid, cphone in cust_result.all():
                if _last10(cphone or "") == match_last10:
                    customer_id = cid
                    break

        # Idempotent upsert keyed by ringcentral_call_id.
        existing_result = await db.execute(
            select(CallLog).where(CallLog.ringcentral_call_id == rc_call_id)
        )
        existing = existing_result.scalar_one_or_none()

        if existing is not None:
            # Update the recording-related fields; don't clobber prior CRM linkage.
            if recording_url:
                existing.recording_url = recording_url
            if duration_seconds is not None:
                existing.duration_seconds = duration_seconds
            existing.transcription_status = "pending"
            if customer_id and not existing.customer_id:
                existing.customer_id = customer_id
            call_log = existing
        else:
            call_log = CallLog(
                id=uuid.uuid4(),
                ringcentral_call_id=rc_call_id,
                ringcentral_session_id=rc_session_id,
                external_system="ringcentral",
                direction=direction,
                call_type="voice",
                caller_number=caller_number or None,
                called_number=called_number or None,
                call_date=call_date,
                call_time=call_time,
                duration_seconds=duration_seconds,
                recording_url=recording_url or None,
                transcription_status="pending",
                customer_id=customer_id,
                user_id="1",
            )
            db.add(call_log)

        await db.commit()
        await db.refresh(call_log)
        log_id = call_log.id

    # Fan out to the AI analyzer worker (stub in Stage 2; real fanout in Stage 3).
    try:
        await enqueue_interaction_analysis(log_id, "call")
    except Exception as e:
        # Never let queue failures break the webhook ack.
        logger.warning("enqueue_interaction_analysis failed for call %s: %s", log_id, e)

    return {"status": "ok", "call_log_id": str(log_id)}
