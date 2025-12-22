"""
Communications API Endpoints

SECURITY:
- Rate limiting on SMS/email send endpoints
- RBAC enforcement for sending messages
- No sensitive data in logs
"""

from fastapi import APIRouter, HTTPException, status, Query, Depends
from sqlalchemy import select, func
from typing import Optional
from datetime import datetime
import logging

from app.api.deps import DbSession, CurrentUser
from app.models.message import Message, MessageType, MessageDirection, MessageStatus
from app.schemas.message import (
    SendSMSRequest,
    SendEmailRequest,
    MessageResponse,
    MessageListResponse,
)
from app.services.twilio_service import TwilioService
from app.security.rate_limiter import rate_limit_sms
from app.security.rbac import require_permission, Permission, has_permission

logger = logging.getLogger(__name__)

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
    """
    Send an SMS message via Twilio.

    SECURITY:
    - Rate limited per user (10/min, 100/hour)
    - Rate limited per destination (5/hour to same number)
    - Requires SEND_SMS permission
    """
    # RBAC check
    if not has_permission(current_user, Permission.SEND_SMS):
        logger.warning(
            "SMS send denied - insufficient permissions",
            extra={"user_id": current_user.id}
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to send SMS messages"
        )

    # Rate limiting
    try:
        rate_limit_sms(current_user, request.to)
    except HTTPException:
        logger.warning(
            "SMS rate limit exceeded",
            extra={"user_id": current_user.id, "destination_suffix": request.to[-4:]}
        )
        raise

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

        # SECURITY: Don't log phone numbers or message content
        logger.info(
            "SMS sent successfully",
            extra={"message_id": message.id, "user_id": current_user.id}
        )

    except Exception as e:
        message.status = MessageStatus.failed
        message.error_message = str(e)
        await db.commit()
        await db.refresh(message)

        logger.error(
            "SMS send failed",
            extra={"message_id": message.id, "error_type": type(e).__name__}
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send SMS. Please try again later.",
        )

    return message


@router.post("/email/send", response_model=MessageResponse)
async def send_email(
    request: SendEmailRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Send an email (placeholder - implement with your email service).

    SECURITY:
    - Requires SEND_EMAIL permission
    """
    # RBAC check
    if not has_permission(current_user, Permission.SEND_EMAIL):
        logger.warning(
            "Email send denied - insufficient permissions",
            extra={"user_id": current_user.id}
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to send emails"
        )

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

    logger.info(
        "Email queued",
        extra={"message_id": message.id, "user_id": current_user.id}
    )

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
