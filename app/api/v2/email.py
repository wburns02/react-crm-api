"""
Email API Endpoints

Provides email-specific endpoints for:
- Listing email conversations
- Getting individual email threads
- Replying to email threads
"""

from fastapi import APIRouter, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from typing import Optional
from datetime import datetime
import logging

from app.api.deps import DbSession, CurrentUser
from app.models.message import Message, MessageType, MessageDirection, MessageStatus
from app.schemas.message import MessageResponse, MessageListResponse

logger = logging.getLogger(__name__)

router = APIRouter()


class EmailReplyRequest(BaseModel):
    """Request body for replying to an email."""

    conversation_id: int
    body: str


@router.get("/conversations", response_model=MessageListResponse)
async def list_email_conversations(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List email conversations (messages with type=email)."""
    # Query for email messages
    query = select(Message).where(Message.type == MessageType.email)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(Message.created_at.desc())

    # Execute query
    result = await db.execute(query)
    messages = result.scalars().all()

    return MessageListResponse(
        items=messages,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/conversations/{conversation_id}")
async def get_email_conversation(
    conversation_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a single email conversation/thread."""
    # Get the original message
    result = await db.execute(select(Message).where(Message.id == conversation_id, Message.type == MessageType.email))
    message = result.scalar_one_or_none()

    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email conversation not found",
        )

    # For now, return as a thread with single message
    # In future, could group by subject/customer for threaded view
    return {
        "id": message.id,
        "subject": message.subject or "(No Subject)",
        "customer_name": message.to_address.split("@")[0] if message.to_address else "Unknown",
        "customer_email": message.to_address,
        "messages": [
            {
                "id": message.id,
                "subject": message.subject,
                "body": message.content,
                "direction": message.direction.value,
                "sent_at": message.sent_at.isoformat() if message.sent_at else message.created_at.isoformat(),
                "from_email": message.from_address or "system@macseptic.com",
                "to_email": message.to_address,
            }
        ],
    }


@router.post("/reply")
async def reply_to_email(
    request: EmailReplyRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Reply to an email conversation."""
    if not request.body or not request.body.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reply body is required",
        )

    conversation_id = request.conversation_id
    body = request.body

    # Get original message
    result = await db.execute(select(Message).where(Message.id == conversation_id))
    original = result.scalar_one_or_none()

    if not original:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Original email not found",
        )

    # Create reply message
    reply = Message(
        customer_id=original.customer_id,
        type=MessageType.email,
        direction=MessageDirection.outbound,
        status=MessageStatus.queued,
        to_address=original.to_address,
        from_address="support@macseptic.com",
        subject=f"Re: {original.subject}" if original.subject else "Re: (No Subject)",
        content=body,
        source="react",
        sent_at=datetime.utcnow(),
    )
    db.add(reply)
    await db.commit()
    await db.refresh(reply)

    logger.info("Email reply created", extra={"message_id": reply.id, "user_id": current_user.id})

    return {
        "id": reply.id,
        "status": "queued",
        "message": "Reply queued for sending",
    }
