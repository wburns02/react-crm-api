from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, func
from typing import Optional
from datetime import datetime

from app.api.deps import DbSession, CurrentUser
from app.models.message import Message, MessageType, MessageDirection, MessageStatus
from app.schemas.message import (
    SendSMSRequest,
    SendEmailRequest,
    MessageResponse,
    MessageListResponse,
)
from app.services.twilio_service import TwilioService

router = APIRouter()


@router.get("/history", response_model=MessageListResponse)
async def get_communication_history(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    customer_id: Optional[int] = None,
    type: Optional[MessageType] = None,
    direction: Optional[MessageDirection] = None,
    status: Optional[MessageStatus] = None,
):
    """Get communication history with pagination and filtering."""
    # Base query
    query = select(Message)

    # Apply filters
    if customer_id:
        query = query.where(Message.customer_id == customer_id)

    if type:
        query = query.where(Message.type == type)

    if direction:
        query = query.where(Message.direction == direction)

    if status:
        query = query.where(Message.status == status)

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


@router.post("/sms/send", response_model=MessageResponse)
async def send_sms(
    request: SendSMSRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Send an SMS message via Twilio."""
    twilio_service = TwilioService()

    # Create message record
    message = Message(
        customer_id=request.customer_id,
        type=MessageType.sms,
        direction=MessageDirection.outbound,
        status=MessageStatus.pending,
        to_address=request.to,
        from_address=twilio_service.phone_number,
        content=request.body,
        source=request.source,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)

    # Send via Twilio
    try:
        twilio_response = await twilio_service.send_sms(
            to=request.to,
            body=request.body,
        )

        # Update message with Twilio response
        message.twilio_sid = twilio_response.sid
        message.status = MessageStatus.queued
        message.sent_at = datetime.utcnow()
        await db.commit()
        await db.refresh(message)

    except Exception as e:
        message.status = MessageStatus.failed
        message.error_message = str(e)
        await db.commit()
        await db.refresh(message)

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send SMS: {str(e)}",
        )

    return message


@router.post("/email/send", response_model=MessageResponse)
async def send_email(
    request: SendEmailRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Send an email (placeholder - implement with your email service)."""
    # Create message record
    message = Message(
        customer_id=request.customer_id,
        type=MessageType.email,
        direction=MessageDirection.outbound,
        status=MessageStatus.pending,
        to_address=request.to,
        subject=request.subject,
        content=request.body,
        source=request.source,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)

    # TODO: Implement email sending with your preferred service
    # For now, just mark as queued
    message.status = MessageStatus.queued
    message.sent_at = datetime.utcnow()
    await db.commit()
    await db.refresh(message)

    return message


@router.get("/{message_id}", response_model=MessageResponse)
async def get_message(
    message_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a single message by ID."""
    result = await db.execute(select(Message).where(Message.id == message_id))
    message = result.scalar_one_or_none()

    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )

    return message
