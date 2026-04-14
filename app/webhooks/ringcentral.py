"""RingCentral Webhook Handlers — Inbound SMS + Delivery Status.

Handles:
- RC subscription validation (Validation-Token handshake)
- Inbound SMS via /message-store events
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
from app.config import settings
from app.services.websocket_manager import manager

logger = logging.getLogger(__name__)

ringcentral_webhook_router = APIRouter()


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
