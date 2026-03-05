"""Brevo Conversations Webhook Handler — Live Chat Integration.

Handles:
- conversation_started: New visitor chat
- conversation_fragment: New messages in an active chat
- conversation_transcript: Chat ended, full transcript

Creates Message records (type='chat') and broadcasts WebSocket events
so CRM staff get real-time notifications for website live chats.
"""

from fastapi import APIRouter, Request
from sqlalchemy import select, or_
import logging
import uuid
from datetime import datetime, timezone

from app.database import async_session_maker
from app.models.message import Message
from app.models.notification import Notification
from app.models.customer import Customer
from app.models.user import User
from app.services.websocket_manager import manager

logger = logging.getLogger(__name__)

brevo_webhook_router = APIRouter()


async def _lookup_customer_by_email(db, email: str):
    """Find a customer by email address."""
    if not email:
        return None
    result = await db.execute(
        select(Customer).where(
            or_(Customer.email == email, Customer.email == email.lower())
        ).limit(1)
    )
    return result.scalar_one_or_none()


async def _get_admin_user_ids(db) -> list[int]:
    """Get all admin/superuser IDs for notification targeting."""
    result = await db.execute(
        select(User.id).where(User.is_superuser == True)  # noqa: E712
    )
    return [row[0] for row in result.all()]


async def _create_chat_notification(db, title: str, message: str, visitor_name: str,
                                     conversation_id: str, admin_ids: list[int]):
    """Create a notification for each admin user."""
    for user_id in admin_ids:
        notif = Notification(
            user_id=user_id,
            type="message",
            title=title,
            message=message,
            link="/communications",
            extra_data={
                "conversation_id": conversation_id,
                "visitor_name": visitor_name,
                "source": "brevo_chat",
            },
            source="webhook",
        )
        db.add(notif)


@brevo_webhook_router.post("/conversations")
async def handle_brevo_conversations(request: Request):
    """Handle Brevo Conversations webhook events.

    Brevo sends three event types:
    - conversation:started — visitor opens chat
    - conversation:fragment — new message(s) in chat
    - conversation:transcript — chat ended
    """
    try:
        payload = await request.json()
    except Exception:
        logger.warning("Brevo webhook: invalid JSON body")
        return {"status": "ignored", "reason": "invalid json"}

    event_type = payload.get("event", "")
    logger.info("Brevo webhook event: %s", event_type)

    if event_type == "conversation:started":
        return await _handle_conversation_started(payload)
    elif event_type == "conversation:fragment":
        return await _handle_conversation_fragment(payload)
    elif event_type == "conversation:transcript":
        return await _handle_conversation_transcript(payload)
    else:
        logger.debug("Brevo webhook: unhandled event type %s", event_type)
        return {"status": "ignored", "reason": f"unhandled event: {event_type}"}


async def _handle_conversation_started(payload: dict):
    """New conversation started by a website visitor."""
    conversation_id = payload.get("conversationId", "")
    visitor = payload.get("visitor", {})
    visitor_name = visitor.get("name", "Website Visitor")
    visitor_email = visitor.get("email", "")
    first_message = ""

    messages = payload.get("messages", [])
    if messages:
        first_message = messages[0].get("text", "")

    async with async_session_maker() as db:
        customer = await _lookup_customer_by_email(db, visitor_email)

        # Create message record
        msg = Message(
            id=uuid.uuid4(),
            customer_id=customer.id if customer else None,
            message_type="chat",
            direction="inbound",
            status="received",
            from_email=visitor_email or None,
            content=first_message or f"[Chat started by {visitor_name}]",
            subject=f"Live Chat: {visitor_name}",
            external_id=f"brevo-conv-{conversation_id}",
        )
        db.add(msg)

        # Create notifications for admins
        admin_ids = await _get_admin_user_ids(db)
        await _create_chat_notification(
            db,
            title="New Live Chat",
            message=f"{visitor_name} started a chat on macseptic.com" + (
                f": \"{first_message[:80]}\"" if first_message else ""
            ),
            visitor_name=visitor_name,
            conversation_id=conversation_id,
            admin_ids=admin_ids,
        )

        await db.commit()

        # Broadcast WebSocket event
        ws_payload = {
            "event": "conversation_started",
            "conversation_id": conversation_id,
            "message_id": str(msg.id),
            "visitor_name": visitor_name,
            "visitor_email": visitor_email,
            "content": first_message,
            "customer_id": str(customer.id) if customer else None,
            "customer_name": (
                f"{customer.first_name or ''} {customer.last_name or ''}".strip()
                if customer else None
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await manager.broadcast_event("chat_message_received", ws_payload)

    return {"status": "ok"}


async def _handle_conversation_fragment(payload: dict):
    """New messages in an active conversation."""
    conversation_id = payload.get("conversationId", "")
    visitor = payload.get("visitor", {})
    visitor_name = visitor.get("name", "Website Visitor")
    visitor_email = visitor.get("email", "")
    messages = payload.get("messages", [])

    if not messages:
        return {"status": "ignored", "reason": "no messages"}

    async with async_session_maker() as db:
        customer = await _lookup_customer_by_email(db, visitor_email)

        for msg_data in messages:
            msg_type = msg_data.get("type", "visitor")  # visitor or agent
            text = msg_data.get("text", "")
            brevo_msg_id = msg_data.get("id", "")
            agent_name = msg_data.get("agentName", "")

            if not text:
                continue

            # Only store visitor messages as inbound; agent messages are outbound
            direction = "inbound" if msg_type == "visitor" else "outbound"

            msg = Message(
                id=uuid.uuid4(),
                customer_id=customer.id if customer else None,
                message_type="chat",
                direction=direction,
                status="received" if direction == "inbound" else "sent",
                from_email=visitor_email if direction == "inbound" else None,
                content=text,
                subject=f"Live Chat: {visitor_name}",
                external_id=f"brevo-msg-{brevo_msg_id}" if brevo_msg_id else f"brevo-conv-{conversation_id}",
            )
            db.add(msg)

            # Only notify on visitor (inbound) messages
            if direction == "inbound":
                admin_ids = await _get_admin_user_ids(db)
                await _create_chat_notification(
                    db,
                    title="Live Chat Message",
                    message=f"{visitor_name}: \"{text[:100]}\"",
                    visitor_name=visitor_name,
                    conversation_id=conversation_id,
                    admin_ids=admin_ids,
                )

                # Broadcast WebSocket event
                ws_payload = {
                    "event": "new_message",
                    "conversation_id": conversation_id,
                    "message_id": str(msg.id),
                    "visitor_name": visitor_name,
                    "visitor_email": visitor_email,
                    "content": text,
                    "customer_id": str(customer.id) if customer else None,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                await manager.broadcast_event("chat_message_received", ws_payload)

        await db.commit()

    return {"status": "ok", "processed": len(messages)}


async def _handle_conversation_transcript(payload: dict):
    """Conversation ended — full transcript received."""
    conversation_id = payload.get("conversationId", "")
    visitor = payload.get("visitor", {})
    visitor_name = visitor.get("name", "Website Visitor")
    visitor_email = visitor.get("email", "")
    messages = payload.get("messages", [])

    logger.info(
        "Chat transcript received: conv=%s visitor=%s messages=%d",
        conversation_id, visitor_name, len(messages),
    )

    # Broadcast conversation ended event
    ws_payload = {
        "event": "conversation_ended",
        "conversation_id": conversation_id,
        "visitor_name": visitor_name,
        "visitor_email": visitor_email,
        "message_count": len(messages),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await manager.broadcast_event("chat_message_received", ws_payload)

    return {"status": "ok"}
