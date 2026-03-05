"""Live Chat API endpoints.

Public endpoints (no auth) for the chat widget on macseptic.com,
plus authenticated endpoints for CRM staff to manage conversations.

TODO: Add rate limiting to public endpoints to prevent abuse.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, case, desc, text
from sqlalchemy.orm import selectinload
from datetime import datetime, timezone, timedelta
from typing import Optional
from zoneinfo import ZoneInfo
import logging
import uuid

from app.database import async_session_maker
from app.models.live_chat import ChatConversation, ChatMessage
from app.models.notification import Notification
from app.models.user import User
from app.api.deps import get_current_user
from app.services.websocket_manager import manager

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
async def leave_offline_message(req: OfflineMessageRequest):
    """Leave a message when staff is offline. Creates a conversation flagged for callback."""
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

    return OfflineMessageResponse(
        conversation_id=str(conversation.id),
        status="active",
        message="Thank you! We'll call you back as soon as we can.",
    )


@router.post("/conversations", response_model=StartConversationResponse)
async def start_conversation(req: StartConversationRequest):
    """Start a new chat conversation from the website widget."""
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

    return StartConversationResponse(
        conversation_id=str(conversation.id),
        status="active",
    )


@router.post(
    "/conversations/{conversation_id}/messages", response_model=MessageResponse
)
async def send_visitor_message(conversation_id: str, req: SendMessageRequest):
    """Send a message from the website visitor."""
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

        # Subquery for last message + counts
        last_msg_sq = (
            select(
                ChatMessage.conversation_id,
                func.max(ChatMessage.created_at).label("last_message_at"),
                func.count(ChatMessage.id).label("message_count"),
            )
            .group_by(ChatMessage.conversation_id)
            .subquery()
        )

        query = (
            select(
                ChatConversation,
                last_msg_sq.c.last_message_at,
                last_msg_sq.c.message_count,
            )
            .outerjoin(
                last_msg_sq,
                ChatConversation.id == last_msg_sq.c.conversation_id,
            )
        )

        if status and status != "all":
            query = query.where(ChatConversation.status == status)

        query = query.order_by(desc(last_msg_sq.c.last_message_at.is_(None)), desc(last_msg_sq.c.last_message_at), desc(ChatConversation.created_at))
        result = await db.execute(query)
        rows = result.all()

        items = []
        for conv, last_msg_at, msg_count in rows:
            # Compute unread: visitor messages after last_read_at
            unread_query = select(func.count(ChatMessage.id)).where(
                ChatMessage.conversation_id == conv.id,
                ChatMessage.sender_type == "visitor",
            )
            if conv.last_read_at:
                unread_query = unread_query.where(
                    ChatMessage.created_at > conv.last_read_at
                )
            unread_result = await db.execute(unread_query)
            unread = unread_result.scalar() or 0
            # Fetch last message content
            last_content = None
            if msg_count and msg_count > 0:
                lm_result = await db.execute(
                    select(ChatMessage.content)
                    .where(ChatMessage.conversation_id == conv.id)
                    .order_by(desc(ChatMessage.created_at))
                    .limit(1)
                )
                last_content = lm_result.scalar_one_or_none()

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
