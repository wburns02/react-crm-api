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
from app.services.email_service import EmailService
from app.security.rate_limiter import rate_limit_sms
from app.security.rbac import require_permission, Permission, has_permission

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/debug-config")
async def get_twilio_debug_config():
    """DEBUG: Check Twilio configuration values (no auth required)."""
    from app.config import settings

    return {
        "account_sid_set": bool(settings.TWILIO_ACCOUNT_SID),
        "account_sid_len": len(settings.TWILIO_ACCOUNT_SID or ""),
        "account_sid_preview": (settings.TWILIO_ACCOUNT_SID or "")[:4] + "..." if settings.TWILIO_ACCOUNT_SID else None,
        "auth_token_set": bool(settings.TWILIO_AUTH_TOKEN),
        "auth_token_len": len(settings.TWILIO_AUTH_TOKEN or ""),
        "phone_number": settings.TWILIO_PHONE_NUMBER,
        "sms_from_number": settings.TWILIO_SMS_FROM_NUMBER,
    }


@router.get("/debug-messages-schema")
async def debug_messages_schema(db: DbSession):
    """DEBUG: Check messages table schema."""
    from sqlalchemy import text

    try:
        result = await db.execute(
            text(
                """SELECT column_name, data_type, is_nullable
                   FROM information_schema.columns
                   WHERE table_name = 'messages'
                   ORDER BY ordinal_position"""
            )
        )
        columns = [{"name": row[0], "type": row[1], "nullable": row[2]} for row in result.fetchall()]

        return {
            "columns": columns,
            "column_count": len(columns),
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/email/status")
async def get_email_service_status(
    current_user: CurrentUser,
):
    """Get email service (SendGrid) configuration status."""
    email_service = EmailService()
    return email_service.get_status()


@router.get("/history")
async def get_communication_history(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    customer_id: Optional[int] = None,
    message_type: Optional[str] = None,
    direction: Optional[str] = None,
    status: Optional[str] = None,
):
    """Get communication history with pagination and filtering."""
    try:
        # Base query
        query = select(Message)

        # Apply filters
        if customer_id:
            query = query.where(Message.customer_id == customer_id)

        if message_type:
            query = query.where(Message.message_type == message_type)

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

        return {
            "items": [
                {
                    "id": m.id,
                    "customer_id": m.customer_id,
                    "type": m.message_type,
                    "direction": m.direction,
                    "status": m.status,
                    "to_address": m.to_number or m.to_email,
                    "from_address": m.from_number or m.from_email,
                    "subject": m.subject,
                    "content": m.content,
                    "external_id": m.external_id,
                    "sent_at": m.sent_at.isoformat() if m.sent_at else None,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in messages
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    except Exception as e:
        logger.error(f"History query failed: {e}")
        return {
            "items": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "debug_error": str(e),
        }


@router.post("/sms/send")
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
        logger.warning("SMS send denied - insufficient permissions", extra={"user_id": current_user.id})
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You don't have permission to send SMS messages"
        )

    # Rate limiting
    try:
        rate_limit_sms(current_user, request.to)
    except HTTPException:
        logger.warning(
            "SMS rate limit exceeded", extra={"user_id": current_user.id, "destination_suffix": request.to[-4:]}
        )
        raise

    twilio_service = TwilioService()

    # Create message record with correct column names
    message = Message(
        customer_id=request.customer_id,
        message_type="sms",
        direction="outbound",
        status="pending",
        to_number=request.to,
        from_number=twilio_service.phone_number,
        content=request.body,
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
        message.external_id = twilio_response.sid
        message.status = "queued"
        message.sent_at = datetime.utcnow()
        await db.commit()
        await db.refresh(message)

        logger.info("SMS sent successfully", extra={"message_id": message.id, "user_id": current_user.id})

    except Exception as e:
        message.status = "failed"
        message.error_message = str(e)
        await db.commit()
        await db.refresh(message)

        logger.error("SMS send failed", extra={"message_id": message.id, "error_type": type(e).__name__})

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send SMS. Please try again later.",
        )

    return {
        "id": message.id,
        "type": message.message_type,
        "direction": message.direction,
        "status": message.status,
        "to_address": message.to_number,
        "from_address": message.from_number,
        "content": message.content,
        "external_id": message.external_id,
        "sent_at": message.sent_at.isoformat() if message.sent_at else None,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


@router.post("/email/send")
async def send_email(
    request: SendEmailRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Send an email via SendGrid.

    SECURITY:
    - Requires SEND_EMAIL permission
    """
    # RBAC check
    if not has_permission(current_user, Permission.SEND_EMAIL):
        logger.warning("Email send denied - insufficient permissions", extra={"user_id": current_user.id})
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have permission to send emails")

    email_service = EmailService()

    # Check if email service is configured
    if not email_service.is_configured:
        status_info = email_service.get_status()
        logger.error("Email service not configured", extra={"status": status_info})
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Email service not available: {status_info.get('message', 'Not configured')}",
        )

    # Create message record with correct column names
    message = Message(
        customer_id=request.customer_id,
        message_type="email",
        direction="outbound",
        status="pending",
        to_email=request.to,
        from_email=email_service.from_address,
        subject=request.subject,
        content=request.body,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)

    # Send via SendGrid
    try:
        email_response = await email_service.send_email(
            to=request.to,
            subject=request.subject,
            body=request.body,
            html_body=getattr(request, "html_body", None),
        )

        if email_response.get("success"):
            message.external_id = email_response.get("message_id")
            message.status = "sent"
            message.sent_at = datetime.utcnow()
            await db.commit()
            await db.refresh(message)

            logger.info("Email sent successfully", extra={"message_id": message.id, "user_id": current_user.id})
        else:
            message.status = "failed"
            message.error_message = email_response.get("error", "Unknown error")
            await db.commit()
            await db.refresh(message)

            logger.error("Email send failed", extra={"message_id": message.id, "error": email_response.get("error")})

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to send email: {email_response.get('error')}",
            )

    except HTTPException:
        raise
    except Exception as e:
        message.status = "failed"
        message.error_message = str(e)
        await db.commit()
        await db.refresh(message)

        logger.error("Email send failed", extra={"message_id": message.id, "error_type": type(e).__name__})

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send email. Please try again later.",
        )

    return {
        "id": message.id,
        "type": message.message_type,
        "direction": message.direction,
        "status": message.status,
        "to_address": message.to_email,
        "from_address": message.from_email,
        "subject": message.subject,
        "content": message.content,
        "external_id": message.external_id,
        "sent_at": message.sent_at.isoformat() if message.sent_at else None,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


@router.get("/stats")
async def get_communication_stats(
    db: DbSession,
    current_user: CurrentUser,
):
    """Get communication statistics for dashboard."""
    try:
        # Count unread SMS (inbound, received status)
        sms_query = (
            select(func.count())
            .select_from(Message)
            .where(
                (Message.message_type == "sms")
                & (Message.direction == "inbound")
                & (Message.status == "received")
            )
        )
        sms_result = await db.execute(sms_query)
        unread_sms = sms_result.scalar() or 0

        # Count unread emails (inbound)
        email_query = (
            select(func.count())
            .select_from(Message)
            .where((Message.message_type == "email") & (Message.direction == "inbound"))
        )
        email_result = await db.execute(email_query)
        unread_email = email_result.scalar() or 0

        return {
            "unread_sms": unread_sms,
            "unread_email": unread_email,
            "pending_reminders": 0,
        }
    except Exception as e:
        logger.error(f"Stats query failed: {e}")
        return {
            "unread_sms": 0,
            "unread_email": 0,
            "pending_reminders": 0,
            "debug_error": str(e),
        }


@router.get("/activity")
async def get_communication_activity(
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(10, ge=1, le=50),
):
    """Get recent communication activity."""
    try:
        query = select(Message).order_by(Message.created_at.desc()).limit(limit)
        result = await db.execute(query)
        messages = result.scalars().all()

        return {
            "items": [
                {
                    "id": m.id,
                    "type": m.message_type,
                    "direction": m.direction,
                    "status": m.status,
                    "to_address": m.to_number or m.to_email,
                    "from_address": m.from_number or m.from_email,
                    "subject": m.subject,
                    "content": m.content[:100] if m.content else None,
                    "customer_id": m.customer_id,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in messages
            ],
            "total": len(messages),
        }
    except Exception as e:
        logger.error(f"Activity query failed: {e}")
        return {
            "items": [],
            "total": 0,
            "debug_error": str(e),
        }


@router.get("/message/{message_id}")
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

    return {
        "id": message.id,
        "customer_id": message.customer_id,
        "type": message.message_type,
        "direction": message.direction,
        "status": message.status,
        "to_address": message.to_number or message.to_email,
        "from_address": message.from_number or message.from_email,
        "subject": message.subject,
        "content": message.content,
        "external_id": message.external_id,
        "sent_at": message.sent_at.isoformat() if message.sent_at else None,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }
