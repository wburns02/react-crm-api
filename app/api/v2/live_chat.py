"""Live Chat API endpoints.

Public endpoints (no auth) for the chat widget on macseptic.com,
plus authenticated endpoints for CRM staff to manage conversations.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, func, desc, text
from sqlalchemy.orm import selectinload
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo
import logging
import time
import uuid

from app.database import async_session_maker
from app.models.live_chat import ChatConversation, ChatMessage
from app.models.notification import Notification
from app.models.user import User
from app.api.deps import get_current_user
from app.services.websocket_manager import manager
from app.core.rate_limit import rate_limit_by_ip
from app.config import settings
import asyncio

logger = logging.getLogger(__name__)

router = APIRouter()


# ─── Pydantic Schemas ───────────────────────────────────────────────


class StartConversationRequest(BaseModel):
    visitor_name: Optional[str] = None
    visitor_email: Optional[str] = None
    visitor_phone: Optional[str] = None
    page_url: Optional[str] = None
    user_agent: Optional[str] = None


class StartConversationResponse(BaseModel):
    conversation_id: str
    status: str


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)
    sender_type: str = "visitor"


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    sender_type: str
    sender_name: Optional[str] = None
    content: str
    created_at: str


class AgentReplyRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)


class UpdateConversationRequest(BaseModel):
    status: Optional[str] = None  # active, closed, archived
    assigned_user_id: Optional[int] = None


class ConversationListItem(BaseModel):
    id: str
    visitor_name: Optional[str] = None
    visitor_email: Optional[str] = None
    visitor_phone: Optional[str] = None
    status: str
    assigned_user_id: Optional[int] = None
    created_at: str
    updated_at: Optional[str] = None
    closed_at: Optional[str] = None
    last_message: Optional[str] = None
    last_message_at: Optional[str] = None
    message_count: int = 0
    unread_count: int = 0
    callback_requested: bool = False


class ConversationDetail(BaseModel):
    id: str
    visitor_name: Optional[str] = None
    visitor_email: Optional[str] = None
    visitor_phone: Optional[str] = None
    customer_id: Optional[str] = None
    status: str
    assigned_user_id: Optional[int] = None
    metadata: Optional[dict] = None
    created_at: str
    updated_at: Optional[str] = None
    closed_at: Optional[str] = None
    messages: list[MessageResponse] = []


# ─── Helpers ─────────────────────────────────────────────────────────


def _msg_to_dict(msg: ChatMessage) -> MessageResponse:
    return MessageResponse(
        id=str(msg.id),
        conversation_id=str(msg.conversation_id),
        sender_type=msg.sender_type,
        sender_name=msg.sender_name,
        content=msg.content,
        created_at=msg.created_at.isoformat() if msg.created_at else "",
    )


async def _get_admin_user_ids(db) -> list[int]:
    """Get all superuser IDs for notification targeting."""
    result = await db.execute(
        select(User.id).where(User.is_superuser == True)  # noqa: E712
    )
    return [row[0] for row in result.all()]


async def _create_chat_notifications(
    db, title: str, message: str, conversation_id: str, admin_ids: list[int]
):
    """Create a notification for each admin user."""
    for user_id in admin_ids:
        notif = Notification(
            user_id=user_id,
            type="message",
            title=title,
            message=message,
            link="/chat",
            extra_data={
                "conversation_id": conversation_id,
                "source": "live_chat_widget",
            },
            source="system",
        )
        db.add(notif)


# Per-conversation throttle for follow-up visitor SMS alerts (timestamps).
_last_visitor_alert_ts: dict[str, float] = {}

# Per-admin-phone rolling list of recently-alerted conversations.
# Maps normalized admin phone (digits only) → list of (index, conversation_id, ts).
# Newest entries pushed to the front; trimmed to RECENT_ALERT_LIMIT.
RECENT_ALERT_LIMIT = 5
_recent_alerts_by_phone: dict[str, list[tuple[int, str, float]]] = {}
_alert_index_counter = 0


def _digits_only(phone: str) -> str:
    d = "".join(c for c in (phone or "") if c.isdigit())
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    return d


def _track_alert(admin_phone: str, conversation_id: str) -> int:
    """Record a chat-alert SMS sent to admin_phone. Returns the short index."""
    global _alert_index_counter
    _alert_index_counter += 1
    idx = _alert_index_counter
    key = _digits_only(admin_phone)
    history = _recent_alerts_by_phone.setdefault(key, [])
    history.insert(0, (idx, conversation_id, time.time()))
    del history[RECENT_ALERT_LIMIT:]
    return idx


def _resolve_chat_for_reply(
    from_phone: str, text: str
) -> tuple[Optional[str], str]:
    """Given an inbound SMS from an admin, figure out which chat to reply to.

    Returns (conversation_id, cleaned_text). cleaned_text strips any routing
    prefix the admin used. conversation_id is None if no match.
    """
    body = text.strip()
    key = _digits_only(from_phone)
    history = _recent_alerts_by_phone.get(key, [])

    # Form 1: "#<full-or-prefix-uuid> message"
    if body.startswith("#"):
        rest = body[1:].split(None, 1)
        prefix = rest[0] if rest else ""
        cleaned = rest[1] if len(rest) > 1 else ""
        for _idx, cid, _ts in history:
            if cid.startswith(prefix.lower()) or cid.replace("-", "").startswith(
                prefix.lower().replace("-", "")
            ):
                return cid, cleaned
        return None, cleaned

    # Form 2: "<index>: message" or "<index> message"
    parts = body.split(None, 1)
    if parts and parts[0].rstrip(":").isdigit():
        try:
            wanted = int(parts[0].rstrip(":"))
            cleaned = parts[1] if len(parts) > 1 else ""
            for idx, cid, _ts in history:
                if idx == wanted:
                    return cid, cleaned
        except ValueError:
            pass

    # Form 3: default — most recent alerted chat
    if history:
        return history[0][1], body
    return None, body


def _send_chat_sms_alerts(body: str, conversation_id: Optional[str] = None) -> None:
    """Fire-and-forget SMS blast to all numbers in CHAT_ALERT_SMS_NUMBERS.

    Each recipient gets a unique short [#N] index prepended so they can reply
    "N: message" to route their text-back to this conversation. Failures are
    logged but never raised — a chat must still succeed even if RingCentral
    is down or unconfigured.
    """
    numbers_csv = (settings.CHAT_ALERT_SMS_NUMBERS or "").strip()
    if not numbers_csv:
        return

    numbers = [n.strip() for n in numbers_csv.split(",") if n.strip()]
    if not numbers:
        return

    async def _send_one(number: str, indexed_body: str) -> None:
        try:
            from app.services.sms_service import send_sms
            result = await send_sms(to=number, body=indexed_body)
            if getattr(result, "error", None):
                logger.warning(
                    f"Chat SMS alert to {number} failed: {result.error}"
                )
        except Exception as e:
            logger.warning(f"Chat SMS alert to {number} raised: {e}")

    loop = asyncio.get_event_loop()
    for number in numbers:
        if conversation_id:
            idx = _track_alert(number, conversation_id)
            indexed_body = f"[#{idx}] {body}\n(Reply '{idx}: <msg>' to answer)"
        else:
            indexed_body = body
        loop.create_task(_send_one(number, indexed_body))


async def post_sms_reply_to_chat(
    from_phone: str, text: str
) -> Optional[dict]:
    """Called by the RingCentral webhook for inbound SMS from a known admin.

    Returns a dict describing what happened, or None if the sender is not a
    configured chat admin (so the webhook can fall through to customer SMS
    routing).
    """
    admin_csv = (settings.CHAT_ALERT_SMS_NUMBERS or "").strip()
    if not admin_csv:
        return None

    admin_keys = {_digits_only(n) for n in admin_csv.split(",") if n.strip()}
    sender_key = _digits_only(from_phone)
    if sender_key not in admin_keys:
        return None  # Not an admin — let customer SMS routing handle it

    conv_id_str, cleaned_text = _resolve_chat_for_reply(from_phone, text)
    if not conv_id_str or not cleaned_text:
        # Send a help text back so the admin knows why nothing happened
        loop = asyncio.get_event_loop()

        async def _help():
            try:
                from app.services.sms_service import send_sms
                await send_sms(
                    to=from_phone,
                    body=(
                        "MAC Septic chat: couldn't route your reply. "
                        "Use 'N: message' (e.g. '1: Hello') or '#<chatid> message'."
                    ),
                )
            except Exception:
                pass

        loop.create_task(_help())
        return {"handled": True, "routed": False, "reason": "no match"}

    try:
        conv_uuid = uuid.UUID(conv_id_str)
    except ValueError:
        return {"handled": True, "routed": False, "reason": "bad uuid"}

    async with async_session_maker() as db:
        result = await db.execute(
            select(ChatConversation).where(ChatConversation.id == conv_uuid)
        )
        conversation = result.scalar_one_or_none()
        if not conversation or conversation.status != "active":
            return {"handled": True, "routed": False, "reason": "conv inactive"}

        agent_name = "MAC Septic"  # SMS-originated replies aren't tied to a User row
        msg = ChatMessage(
            id=uuid.uuid4(),
            conversation_id=conv_uuid,
            sender_type="agent",
            sender_name=agent_name,
            content=cleaned_text,
        )
        db.add(msg)
        await db.commit()
        await db.refresh(msg)

        await manager.broadcast_event(
            "chat_message_received",
            {
                "event": "agent_reply",
                "conversation_id": str(conv_uuid),
                "message_id": str(msg.id),
                "sender_type": "agent",
                "sender_name": agent_name,
                "content": cleaned_text,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "via": "sms",
            },
        )

    return {
        "handled": True,
        "routed": True,
        "conversation_id": str(conv_uuid),
        "message_id": str(msg.id),
    }


# ─── Business Hours ──────────────────────────────────────────────────

CST = ZoneInfo("America/Chicago")
BUSINESS_HOURS_START = 8   # 8:00 AM CST
BUSINESS_HOURS_END = 17    # 5:00 PM CST
BUSINESS_DAYS = {0, 1, 2, 3, 4}  # Monday=0 through Friday=4


def _is_within_business_hours() -> bool:
    """Check if current time is within business hours (8 AM - 5 PM CST, Mon-Fri)."""
    now_cst = datetime.now(CST)
    return (
        now_cst.weekday() in BUSINESS_DAYS
        and BUSINESS_HOURS_START <= now_cst.hour < BUSINESS_HOURS_END
    )


class ChatStatusResponse(BaseModel):
    online: bool
    hours: str = "8:00 AM – 5:00 PM CST"
    days: str = "Monday – Friday"
    message: str = ""
    current_time_cst: str = ""


class OfflineMessageRequest(BaseModel):
    visitor_name: str = Field(..., min_length=1, max_length=255)
    visitor_phone: str = Field(..., min_length=7, max_length=50)
    visitor_email: Optional[str] = None
    message: str = Field(..., min_length=1, max_length=5000)
    page_url: Optional[str] = None


class OfflineMessageResponse(BaseModel):
    conversation_id: str
    status: str
    message: str


# ─── Public Endpoints (no auth — for the widget on macseptic.com) ───


@router.get("/status", response_model=ChatStatusResponse)
async def get_chat_status():
    """Check if live chat is currently online (within business hours)."""
    online = _is_within_business_hours()
    now_cst = datetime.now(CST)
    return ChatStatusResponse(
        online=online,
        hours="8:00 AM – 5:00 PM CST",
        days="Monday – Friday",
        message=(
            "We're online! Start a chat and we'll respond right away."
            if online
            else "We're currently offline. Leave a message with your phone number and we'll call you back as soon as we can!"
        ),
        current_time_cst=now_cst.strftime("%I:%M %p %Z"),
    )


@router.post("/offline-message", response_model=OfflineMessageResponse)
async def leave_offline_message(req: OfflineMessageRequest, request: Request):
    """Leave a message when staff is offline. Creates a conversation flagged for callback."""
    rate_limit_by_ip(request, requests_per_minute=5)
    async with async_session_maker() as db:
        conversation = ChatConversation(
            id=uuid.uuid4(),
            visitor_name=req.visitor_name,
            visitor_email=req.visitor_email,
            visitor_phone=req.visitor_phone,
            status="active",
            metadata_json={
                "page_url": req.page_url,
                "offline_message": True,
                "callback_requested": True,
            },
        )
        db.add(conversation)

        msg = ChatMessage(
            id=uuid.uuid4(),
            conversation_id=conversation.id,
            sender_type="visitor",
            sender_name=req.visitor_name,
            content=req.message,
        )
        db.add(msg)

        # Notify admins
        admin_ids = await _get_admin_user_ids(db)
        await _create_chat_notifications(
            db,
            title="📞 Callback Requested",
            message=f"{req.visitor_name} left an offline message — call back at {req.visitor_phone}",
            conversation_id=str(conversation.id),
            admin_ids=admin_ids,
        )

        await db.commit()

        # Broadcast for real-time CRM updates
        await manager.broadcast_event(
            "chat_message_received",
            {
                "event": "offline_message",
                "conversation_id": str(conversation.id),
                "visitor_name": req.visitor_name,
                "visitor_phone": req.visitor_phone,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    # SMS alert — callbacks are urgent, always notify
    _send_chat_sms_alerts(
        f"📞 MAC Septic callback request from {req.visitor_name} "
        f"({req.visitor_phone}). Message: {req.message[:120]}",
        conversation_id=str(conversation.id),
    )

    return OfflineMessageResponse(
        conversation_id=str(conversation.id),
        status="active",
        message="Thank you! We'll call you back as soon as we can.",
    )


@router.post("/conversations", response_model=StartConversationResponse)
async def start_conversation(req: StartConversationRequest, request: Request):
    """Start a new chat conversation from the website widget."""
    rate_limit_by_ip(request, requests_per_minute=5)
    async with async_session_maker() as db:
        conversation = ChatConversation(
            id=uuid.uuid4(),
            visitor_name=req.visitor_name,
            visitor_email=req.visitor_email,
            visitor_phone=req.visitor_phone,
            status="active",
            metadata_json={
                "page_url": req.page_url,
                "user_agent": req.user_agent,
            },
        )
        db.add(conversation)

        # Create notifications for all superusers
        admin_ids = await _get_admin_user_ids(db)
        await _create_chat_notifications(
            db,
            title="New Live Chat",
            message=f"{req.visitor_name or 'Website Visitor'} started a chat"
            + (f" from {req.page_url}" if req.page_url else ""),
            conversation_id=str(conversation.id),
            admin_ids=admin_ids,
        )

        await db.commit()

        # Broadcast WebSocket event
        await manager.broadcast_event(
            "chat_message_received",
            {
                "event": "conversation_started",
                "conversation_id": str(conversation.id),
                "visitor_name": req.visitor_name,
                "visitor_email": req.visitor_email,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    # SMS alert — new live chat started
    visitor = req.visitor_name or "Website Visitor"
    phone_part = f" ({req.visitor_phone})" if req.visitor_phone else ""
    _send_chat_sms_alerts(
        f"💬 New MAC Septic chat from {visitor}{phone_part}",
        conversation_id=str(conversation.id),
    )

    return StartConversationResponse(
        conversation_id=str(conversation.id),
        status="active",
    )


@router.post(
    "/conversations/{conversation_id}/messages", response_model=MessageResponse
)
async def send_visitor_message(
    conversation_id: str, req: SendMessageRequest, request: Request
):
    """Send a message from the website visitor."""
    rate_limit_by_ip(request, requests_per_minute=30)
    try:
        conv_uuid = uuid.UUID(conversation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid conversation ID")

    async with async_session_maker() as db:
        # Verify conversation exists and is active
        result = await db.execute(
            select(ChatConversation).where(ChatConversation.id == conv_uuid)
        )
        conversation = result.scalar_one_or_none()
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if conversation.status != "active":
            raise HTTPException(
                status_code=400, detail="Conversation is no longer active"
            )

        msg = ChatMessage(
            id=uuid.uuid4(),
            conversation_id=conv_uuid,
            sender_type="visitor",
            sender_name=conversation.visitor_name,
            content=req.content,
        )
        db.add(msg)
        await db.commit()
        await db.refresh(msg)

        msg_response = _msg_to_dict(msg)

        # Broadcast WebSocket event for real-time CRM updates
        await manager.broadcast_event(
            "chat_message_received",
            {
                "event": "new_message",
                "conversation_id": str(conv_uuid),
                "message_id": str(msg.id),
                "sender_type": "visitor",
                "sender_name": conversation.visitor_name,
                "content": req.content,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    # SMS alert for follow-up visitor messages — throttled to one alert per
    # conversation per 30s so a multi-line typer doesn't blow up the phone.
    now_ts = time.time()
    last = _last_visitor_alert_ts.get(str(conv_uuid), 0.0)
    if now_ts - last > 30:
        _last_visitor_alert_ts[str(conv_uuid)] = now_ts
        visitor = conversation.visitor_name or "Website Visitor"
        _send_chat_sms_alerts(
            f"💬 {visitor}: {req.content[:140]}",
            conversation_id=str(conv_uuid),
        )

    return msg_response


@router.get(
    "/conversations/{conversation_id}/messages", response_model=list[MessageResponse]
)
async def get_conversation_messages(
    conversation_id: str,
    after: Optional[str] = Query(None, description="ISO timestamp to get messages after"),
):
    """Get messages for a conversation (used by widget for polling)."""
    try:
        conv_uuid = uuid.UUID(conversation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid conversation ID")

    async with async_session_maker() as db:
        # Verify conversation exists
        result = await db.execute(
            select(ChatConversation).where(ChatConversation.id == conv_uuid)
        )
        conversation = result.scalar_one_or_none()
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        query = select(ChatMessage).where(
            ChatMessage.conversation_id == conv_uuid
        )

        if after:
            try:
                after_dt = datetime.fromisoformat(after.replace("Z", "+00:00"))
                query = query.where(ChatMessage.created_at > after_dt)
            except ValueError:
                raise HTTPException(
                    status_code=400, detail="Invalid 'after' timestamp format"
                )

        query = query.order_by(ChatMessage.created_at)
        result = await db.execute(query)
        messages = result.scalars().all()

    return [_msg_to_dict(m) for m in messages]


# ─── Authenticated Endpoints (for CRM staff) ────────────────────────


@router.get("/conversations", response_model=list[ConversationListItem])
async def list_conversations(
    status: Optional[str] = Query(None, description="Filter by status: active, closed, archived, or all"),
    current_user: User = Depends(get_current_user),
):
    """List all chat conversations (staff only)."""
    async with async_session_maker() as db:
        # Ensure last_read_at column exists (safe idempotent migration)
        try:
            await db.execute(text(
                "ALTER TABLE chat_conversations ADD COLUMN IF NOT EXISTS last_read_at TIMESTAMPTZ"
            ))
            await db.commit()
        except Exception:
            await db.rollback()

        # Single-pass aggregation: last_message_at, message_count, last content via DISTINCT ON
        last_msg_sq = (
            select(
                ChatMessage.conversation_id,
                func.max(ChatMessage.created_at).label("last_message_at"),
                func.count(ChatMessage.id).label("message_count"),
            )
            .group_by(ChatMessage.conversation_id)
            .subquery()
        )

        # Latest message content per conversation via correlated subquery
        latest_content_sq = (
            select(ChatMessage.content)
            .where(ChatMessage.conversation_id == ChatConversation.id)
            .order_by(desc(ChatMessage.created_at))
            .limit(1)
            .correlate(ChatConversation)
            .scalar_subquery()
        )

        # Unread count aggregated in one query: visitor messages after last_read_at
        unread_sq = (
            select(
                ChatMessage.conversation_id,
                func.count(ChatMessage.id).label("unread_count"),
            )
            .join(
                ChatConversation,
                ChatConversation.id == ChatMessage.conversation_id,
            )
            .where(
                ChatMessage.sender_type == "visitor",
                (
                    (ChatConversation.last_read_at.is_(None))
                    | (ChatMessage.created_at > ChatConversation.last_read_at)
                ),
            )
            .group_by(ChatMessage.conversation_id)
            .subquery()
        )

        query = (
            select(
                ChatConversation,
                last_msg_sq.c.last_message_at,
                last_msg_sq.c.message_count,
                latest_content_sq.label("last_content"),
                unread_sq.c.unread_count,
            )
            .outerjoin(
                last_msg_sq,
                ChatConversation.id == last_msg_sq.c.conversation_id,
            )
            .outerjoin(
                unread_sq,
                ChatConversation.id == unread_sq.c.conversation_id,
            )
        )

        if status and status != "all":
            query = query.where(ChatConversation.status == status)

        query = query.order_by(
            desc(last_msg_sq.c.last_message_at.is_(None)),
            desc(last_msg_sq.c.last_message_at),
            desc(ChatConversation.created_at),
        )
        result = await db.execute(query)
        rows = result.all()

        items = []
        for conv, last_msg_at, msg_count, last_content, unread in rows:
            meta = conv.metadata_json or {}
            items.append(
                ConversationListItem(
                    id=str(conv.id),
                    visitor_name=conv.visitor_name,
                    visitor_email=conv.visitor_email,
                    visitor_phone=conv.visitor_phone,
                    status=conv.status,
                    assigned_user_id=conv.assigned_user_id,
                    created_at=conv.created_at.isoformat() if conv.created_at else "",
                    updated_at=conv.updated_at.isoformat() if conv.updated_at else None,
                    closed_at=conv.closed_at.isoformat() if conv.closed_at else None,
                    last_message=last_content,
                    last_message_at=last_msg_at.isoformat() if last_msg_at else None,
                    message_count=msg_count or 0,
                    unread_count=unread or 0,
                    callback_requested=bool(meta.get("callback_requested")),
                )
            )

    return items


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get a conversation with all its messages (staff only)."""
    try:
        conv_uuid = uuid.UUID(conversation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid conversation ID")

    async with async_session_maker() as db:
        result = await db.execute(
            select(ChatConversation)
            .options(selectinload(ChatConversation.messages))
            .where(ChatConversation.id == conv_uuid)
        )
        conversation = result.scalar_one_or_none()
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

    return ConversationDetail(
        id=str(conversation.id),
        visitor_name=conversation.visitor_name,
        visitor_email=conversation.visitor_email,
        visitor_phone=conversation.visitor_phone,
        customer_id=str(conversation.customer_id) if conversation.customer_id else None,
        status=conversation.status,
        assigned_user_id=conversation.assigned_user_id,
        metadata=conversation.metadata_json,
        created_at=conversation.created_at.isoformat() if conversation.created_at else "",
        updated_at=conversation.updated_at.isoformat() if conversation.updated_at else None,
        closed_at=conversation.closed_at.isoformat() if conversation.closed_at else None,
        messages=[_msg_to_dict(m) for m in conversation.messages],
    )


@router.post(
    "/conversations/{conversation_id}/reply", response_model=MessageResponse
)
async def send_agent_reply(
    conversation_id: str,
    req: AgentReplyRequest,
    current_user: User = Depends(get_current_user),
):
    """Send a reply as an agent (staff only)."""
    try:
        conv_uuid = uuid.UUID(conversation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid conversation ID")

    async with async_session_maker() as db:
        result = await db.execute(
            select(ChatConversation).where(ChatConversation.id == conv_uuid)
        )
        conversation = result.scalar_one_or_none()
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if conversation.status != "active":
            raise HTTPException(
                status_code=400, detail="Conversation is no longer active"
            )

        agent_name = f"{current_user.first_name or ''} {current_user.last_name or ''}".strip() or current_user.email

        msg = ChatMessage(
            id=uuid.uuid4(),
            conversation_id=conv_uuid,
            sender_type="agent",
            sender_name=agent_name,
            content=req.content,
        )
        db.add(msg)

        # Auto-assign the conversation to this agent if not already assigned
        if not conversation.assigned_user_id:
            conversation.assigned_user_id = current_user.id

        await db.commit()
        await db.refresh(msg)

        msg_response = _msg_to_dict(msg)

        # Broadcast so the widget can pick up the reply via polling
        await manager.broadcast_event(
            "chat_message_received",
            {
                "event": "agent_reply",
                "conversation_id": str(conv_uuid),
                "message_id": str(msg.id),
                "sender_type": "agent",
                "sender_name": agent_name,
                "content": req.content,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    return msg_response


@router.patch("/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: str,
    req: UpdateConversationRequest,
    current_user: User = Depends(get_current_user),
):
    """Update a conversation — close, assign, archive, etc. (staff only)."""
    try:
        conv_uuid = uuid.UUID(conversation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid conversation ID")

    async with async_session_maker() as db:
        result = await db.execute(
            select(ChatConversation).where(ChatConversation.id == conv_uuid)
        )
        conversation = result.scalar_one_or_none()
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        if req.status is not None:
            if req.status not in ("active", "closed", "archived"):
                raise HTTPException(
                    status_code=400,
                    detail="Status must be 'active', 'closed', or 'archived'",
                )
            conversation.status = req.status
            if req.status == "closed":
                conversation.closed_at = datetime.now(timezone.utc)

        if req.assigned_user_id is not None:
            conversation.assigned_user_id = req.assigned_user_id

        await db.commit()

        # Broadcast status update
        await manager.broadcast_event(
            "chat_message_received",
            {
                "event": "conversation_updated",
                "conversation_id": str(conv_uuid),
                "status": conversation.status,
                "assigned_user_id": conversation.assigned_user_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    return {
        "id": str(conversation.id),
        "status": conversation.status,
        "assigned_user_id": conversation.assigned_user_id,
        "updated": True,
    }


@router.post("/conversations/{conversation_id}/mark-read")
async def mark_conversation_read(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
):
    """Mark all messages in a conversation as read (staff only)."""
    try:
        conv_uuid = uuid.UUID(conversation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid conversation ID")

    async with async_session_maker() as db:
        result = await db.execute(
            select(ChatConversation).where(ChatConversation.id == conv_uuid)
        )
        conversation = result.scalar_one_or_none()
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        conversation.last_read_at = datetime.now(timezone.utc)
        await db.commit()

    return {"id": str(conv_uuid), "marked_read": True}


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
):
    """Delete a conversation and all its messages (staff only)."""
    try:
        conv_uuid = uuid.UUID(conversation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid conversation ID")

    async with async_session_maker() as db:
        result = await db.execute(
            select(ChatConversation).where(ChatConversation.id == conv_uuid)
        )
        conversation = result.scalar_one_or_none()
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Delete messages first (CASCADE should handle this but be explicit)
        await db.execute(
            select(ChatMessage).where(ChatMessage.conversation_id == conv_uuid)
        )
        from sqlalchemy import delete as sa_delete
        await db.execute(
            sa_delete(ChatMessage).where(ChatMessage.conversation_id == conv_uuid)
        )
        await db.execute(
            sa_delete(ChatConversation).where(ChatConversation.id == conv_uuid)
        )
        await db.commit()

    return {"id": str(conv_uuid), "deleted": True}


# ─── Typing Indicators ──────────────────────────────────────────────
#
# In-memory store with 5s TTL. Keyed by conversation_id, value is
# {sender_type: (timestamp, sender_name)}. Not persisted — if the
# process restarts, indicators just vanish, which is fine.

_TYPING_TTL_SECONDS = 5.0
_typing_state: dict[str, dict[str, tuple[float, Optional[str]]]] = {}


def _prune_typing(conv_id: str) -> dict[str, Optional[str]]:
    """Remove expired entries and return active typers for a conversation."""
    now = time.time()
    entries = _typing_state.get(conv_id, {})
    active = {
        sender: name
        for sender, (ts, name) in entries.items()
        if now - ts < _TYPING_TTL_SECONDS
    }
    if active:
        _typing_state[conv_id] = {
            sender: (ts, name)
            for sender, (ts, name) in entries.items()
            if now - ts < _TYPING_TTL_SECONDS
        }
    else:
        _typing_state.pop(conv_id, None)
    return active


class TypingRequest(BaseModel):
    sender_type: str = Field(..., pattern="^(visitor|agent)$")
    sender_name: Optional[str] = None


class TypingStatusResponse(BaseModel):
    visitor_typing: bool = False
    agent_typing: bool = False
    agent_name: Optional[str] = None


@router.post("/conversations/{conversation_id}/typing")
async def set_typing(
    conversation_id: str,
    req: TypingRequest,
    request: Request,
):
    """Mark a conversation as being typed in. Public endpoint used by both
    widget (visitor) and CRM staff (agent). Rate-limited per IP."""
    rate_limit_by_ip(request, requests_per_minute=60)
    try:
        uuid.UUID(conversation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid conversation ID")

    _typing_state.setdefault(conversation_id, {})[req.sender_type] = (
        time.time(),
        req.sender_name,
    )
    return {"ok": True}


@router.get(
    "/conversations/{conversation_id}/typing",
    response_model=TypingStatusResponse,
)
async def get_typing(conversation_id: str):
    """Get current typing state for a conversation. Polled every ~2s."""
    try:
        uuid.UUID(conversation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid conversation ID")

    active = _prune_typing(conversation_id)
    return TypingStatusResponse(
        visitor_typing="visitor" in active,
        agent_typing="agent" in active,
        agent_name=active.get("agent") if "agent" in active else None,
    )


# ─── Canned Responses ───────────────────────────────────────────────

_CANNED_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS chat_canned_responses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    shortcut VARCHAR(50),
    sort_order INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_CANNED_SEED = [
    ("Greeting", "Hi! Thanks for reaching out to MAC Septic. How can I help you today?", "/hi"),
    ("Service area", "We serve the Austin metro and surrounding counties. What's your zip code so I can confirm?", "/area"),
    ("Pump-out pricing", "A standard residential pump-out is $395. Larger tanks or heavy solids may add $50–$150. Want me to schedule one?", "/pump"),
    ("Schedule question", "We can usually get a tech out within 1–2 business days. What day works best for you?", "/sched"),
    ("Aerobic maintenance", "Aerobic systems need a licensed maintenance contract — $290/yr covers 3 inspections + chlorine. Want me to sign you up?", "/aerobic"),
    ("Callback offer", "I'll have someone give you a call back shortly. What's the best number to reach you at?", "/call"),
]

_canned_seeded = False


async def _ensure_canned_table(db):
    """Create table + seed default responses on first use. Idempotent."""
    global _canned_seeded
    await db.execute(text(_CANNED_TABLE_DDL))
    if not _canned_seeded:
        count_result = await db.execute(
            text("SELECT COUNT(*) FROM chat_canned_responses")
        )
        if (count_result.scalar() or 0) == 0:
            for idx, (title, content, shortcut) in enumerate(_CANNED_SEED):
                await db.execute(
                    text(
                        "INSERT INTO chat_canned_responses (title, content, shortcut, sort_order) "
                        "VALUES (:t, :c, :s, :o)"
                    ),
                    {"t": title, "c": content, "s": shortcut, "o": idx},
                )
        _canned_seeded = True
    await db.commit()


class CannedResponseItem(BaseModel):
    id: str
    title: str
    content: str
    shortcut: Optional[str] = None
    sort_order: int = 0


class CannedResponseCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1, max_length=5000)
    shortcut: Optional[str] = Field(None, max_length=50)
    sort_order: int = 0


class CannedResponseUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    content: Optional[str] = Field(None, min_length=1, max_length=5000)
    shortcut: Optional[str] = Field(None, max_length=50)
    sort_order: Optional[int] = None


@router.get("/canned-responses", response_model=list[CannedResponseItem])
async def list_canned_responses(current_user: User = Depends(get_current_user)):
    """List all canned responses (staff only)."""
    async with async_session_maker() as db:
        await _ensure_canned_table(db)
        result = await db.execute(
            text(
                "SELECT id, title, content, shortcut, sort_order "
                "FROM chat_canned_responses ORDER BY sort_order, title"
            )
        )
        return [
            CannedResponseItem(
                id=str(row[0]),
                title=row[1],
                content=row[2],
                shortcut=row[3],
                sort_order=row[4],
            )
            for row in result.all()
        ]


@router.post("/canned-responses", response_model=CannedResponseItem)
async def create_canned_response(
    req: CannedResponseCreate,
    current_user: User = Depends(get_current_user),
):
    """Create a canned response (staff only)."""
    async with async_session_maker() as db:
        await _ensure_canned_table(db)
        new_id = uuid.uuid4()
        await db.execute(
            text(
                "INSERT INTO chat_canned_responses (id, title, content, shortcut, sort_order) "
                "VALUES (:id, :t, :c, :s, :o)"
            ),
            {
                "id": new_id,
                "t": req.title,
                "c": req.content,
                "s": req.shortcut,
                "o": req.sort_order,
            },
        )
        await db.commit()
    return CannedResponseItem(
        id=str(new_id),
        title=req.title,
        content=req.content,
        shortcut=req.shortcut,
        sort_order=req.sort_order,
    )


@router.patch("/canned-responses/{response_id}", response_model=CannedResponseItem)
async def update_canned_response(
    response_id: str,
    req: CannedResponseUpdate,
    current_user: User = Depends(get_current_user),
):
    """Update a canned response (staff only)."""
    try:
        resp_uuid = uuid.UUID(response_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid response ID")

    updates = {k: v for k, v in req.model_dump(exclude_none=True).items()}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_clause = ", ".join(f"{k} = :{k}" for k in updates.keys())
    params = {**updates, "id": resp_uuid}

    async with async_session_maker() as db:
        await _ensure_canned_table(db)
        await db.execute(
            text(
                f"UPDATE chat_canned_responses SET {set_clause}, updated_at = NOW() "
                f"WHERE id = :id"
            ),
            params,
        )
        await db.commit()
        result = await db.execute(
            text(
                "SELECT id, title, content, shortcut, sort_order "
                "FROM chat_canned_responses WHERE id = :id"
            ),
            {"id": resp_uuid},
        )
        row = result.one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Canned response not found")

    return CannedResponseItem(
        id=str(row[0]),
        title=row[1],
        content=row[2],
        shortcut=row[3],
        sort_order=row[4],
    )


@router.delete("/canned-responses/{response_id}")
async def delete_canned_response(
    response_id: str,
    current_user: User = Depends(get_current_user),
):
    """Delete a canned response (staff only)."""
    try:
        resp_uuid = uuid.UUID(response_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid response ID")

    async with async_session_maker() as db:
        await _ensure_canned_table(db)
        await db.execute(
            text("DELETE FROM chat_canned_responses WHERE id = :id"),
            {"id": resp_uuid},
        )
        await db.commit()
    return {"id": str(resp_uuid), "deleted": True}
