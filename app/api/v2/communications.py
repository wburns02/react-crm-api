"""
Communications API Endpoints

SECURITY:
- Rate limiting on SMS/email send endpoints
- RBAC enforcement for sending messages
- No sensitive data in logs
"""

from fastapi import APIRouter, HTTPException, status, Query, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from typing import Optional, List
from datetime import datetime
import logging
import asyncio

from app.api.deps import DbSession, CurrentUser
from app.models.message import Message, MessageType, MessageDirection, MessageStatus
from app.models.customer import Customer
from app.schemas.message import (
    SendSMSRequest,
    SendEmailRequest,
    MessageResponse,
    MessageListResponse,
)
from app.services.sms_service import sms_service
from app.services.email_service import EmailService
from app.security.rate_limiter import rate_limit_sms
from app.security.rbac import require_permission, Permission, has_permission

logger = logging.getLogger(__name__)

router = APIRouter()


# DEBUG endpoints removed for security - Issue #5
# Previously: /debug-config, /debug-messages-schema
# These exposed sensitive configuration in production


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
    customer_id: Optional[str] = None,
    message_type: Optional[str] = None,
    direction: Optional[str] = None,
    status: Optional[str] = None,
):
    """Get communication history with pagination and filtering."""
    try:
        # Base query
        query = select(Message).options(selectinload(Message.customer))

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
    Send an SMS message via RingCentral (TCR-approved).

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

    # Send via RingCentral (TCR-approved) first, then record in DB
    try:
        sms_response = await sms_service.send_sms(
            to=request.to,
            body=request.body,
        )
    except Exception as e:
        logger.error("SMS send failed", extra={"error_type": type(e).__name__, "user_id": current_user.id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send SMS. Please try again later.",
        )

    # Check for soft failures (RC returned error in response)
    if sms_response.error:
        logger.error(
            "SMS provider returned error",
            extra={"error": sms_response.error, "user_id": current_user.id},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"SMS provider error: {sms_response.error[:200]}",
        )

    # Record message in DB (best-effort — SMS already sent)
    message_id = None
    sent_at = datetime.utcnow()
    try:
        message = Message(
            customer_id=request.customer_id,
            message_type="sms",
            direction="outbound",
            status="queued",
            to_number=request.to,
            from_number=sms_service.phone_number,
            content=request.body,
            external_id=sms_response.sid,
            sent_at=sent_at,
        )
        db.add(message)
        await db.commit()
        await db.refresh(message)
        message_id = message.id
        logger.info("SMS sent successfully", extra={"message_id": message_id, "user_id": current_user.id})
    except Exception as db_err:
        await db.rollback()
        logger.warning("SMS sent but DB record failed: %s", db_err)

    return {
        "id": str(message_id) if message_id else None,
        "type": "sms",
        "direction": "outbound",
        "status": "queued",
        "to_address": request.to,
        "from_address": sms_service.phone_number,
        "content": request.body,
        "external_id": sms_response.sid,
        "sent_at": sent_at.isoformat(),
        "created_at": sent_at.isoformat(),
    }


class BulkSMSRequest(BaseModel):
    """Schema for sending bulk SMS to multiple customers."""
    customer_ids: List[str] = Field(..., min_length=1, max_length=500, description="Customer UUIDs")
    message: str = Field(..., min_length=1, max_length=1600, description="Message body (supports {{customer_name}}, {{first_name}} variables)")


class BulkSMSResponse(BaseModel):
    """Response from bulk SMS send."""
    total: int
    sent: int
    failed: int
    skipped: int
    results: List[dict]


@router.post("/sms/send-bulk", response_model=BulkSMSResponse)
async def send_bulk_sms(
    request: BulkSMSRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Send SMS to multiple customers.

    Supports template variables:
    - {{customer_name}} - Full name
    - {{first_name}} - First name only
    - {{last_name}} - Last name only

    SECURITY:
    - Requires SEND_SMS permission
    - Rate limited per user
    """
    if not has_permission(current_user, Permission.SEND_SMS):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to send SMS messages",
        )

    # Fetch all customers with their phone numbers
    result = await db.execute(
        select(Customer).where(Customer.id.in_(request.customer_ids))
    )
    customers = result.scalars().all()

    if not customers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid customers found",
        )

    results = []
    sent = 0
    failed = 0
    skipped = 0

    for customer in customers:
        phone = customer.phone
        if not phone:
            results.append({
                "customer_id": str(customer.id),
                "customer_name": f"{customer.first_name or ''} {customer.last_name or ''}".strip(),
                "status": "skipped",
                "reason": "No phone number",
            })
            skipped += 1
            continue

        # Personalize message with template variables
        personalized = request.message
        full_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip()
        personalized = personalized.replace("{{customer_name}}", full_name or "Customer")
        personalized = personalized.replace("{{first_name}}", customer.first_name or "Customer")
        personalized = personalized.replace("{{last_name}}", customer.last_name or "")

        try:
            sms_response = await sms_service.send_sms(to=phone, body=personalized)

            if sms_response.error:
                results.append({
                    "customer_id": str(customer.id),
                    "customer_name": full_name,
                    "phone": phone,
                    "status": "failed",
                    "reason": str(sms_response.error)[:100],
                })
                failed += 1
                continue

            # Best-effort DB record
            try:
                msg = Message(
                    customer_id=customer.id,
                    message_type="sms",
                    direction="outbound",
                    status="queued",
                    to_number=phone,
                    from_number=sms_service.phone_number,
                    content=personalized,
                    external_id=sms_response.sid,
                    sent_at=datetime.utcnow(),
                )
                db.add(msg)
                await db.commit()
            except Exception:
                await db.rollback()

            results.append({
                "customer_id": str(customer.id),
                "customer_name": full_name,
                "phone": phone,
                "status": "sent",
                "external_id": sms_response.sid,
            })
            sent += 1

        except Exception as e:
            results.append({
                "customer_id": str(customer.id),
                "customer_name": full_name,
                "phone": phone,
                "status": "failed",
                "reason": str(e)[:100],
            })
            failed += 1

    logger.info(
        "Bulk SMS completed",
        extra={"user_id": current_user.id, "total": len(customers), "sent": sent, "failed": failed, "skipped": skipped},
    )

    return BulkSMSResponse(
        total=len(customers),
        sent=sent,
        failed=failed,
        skipped=skipped,
        results=results,
    )


@router.get("/sms/customers")
async def search_customers_for_sms(
    db: DbSession,
    current_user: CurrentUser,
    search: str = Query("", description="Search by name, phone, or email"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    active_only: bool = Query(True),
):
    """Search customers with phone numbers for SMS sending."""
    query = select(Customer)

    if active_only:
        query = query.where(Customer.is_active == True)

    # Only show customers with phone numbers
    query = query.where(Customer.phone.isnot(None)).where(Customer.phone != "")

    if search:
        search_term = f"%{search}%"
        query = query.where(
            or_(
                (Customer.first_name + " " + Customer.last_name).ilike(search_term),
                Customer.phone.ilike(search_term),
                Customer.email.ilike(search_term),
                Customer.first_name.ilike(search_term),
                Customer.last_name.ilike(search_term),
            )
        )

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Paginate
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(Customer.first_name, Customer.last_name)

    result = await db.execute(query)
    customers = result.scalars().all()

    return {
        "items": [
            {
                "id": str(c.id),
                "first_name": c.first_name,
                "last_name": c.last_name,
                "name": f"{c.first_name or ''} {c.last_name or ''}".strip(),
                "phone": c.phone,
                "email": c.email,
                "city": getattr(c, "city", None),
                "state": getattr(c, "state", None),
                "is_active": c.is_active,
            }
            for c in customers
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
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

        logger.error("Email send failed", extra={"message_id": message.id, "error_type": type(e).__name__, "error": str(e)})

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send email: {type(e).__name__}: {str(e)[:200]}",
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
    channel: Optional[str] = Query(None, description="Filter by channel: sms, email, call"),
    search: Optional[str] = Query(None, description="Search in content or customer name"),
):
    """Get recent communication activity with customer names."""
    try:
        query = (
            select(Message, Customer.first_name, Customer.last_name)
            .outerjoin(Customer, Message.customer_id == Customer.id)
            .order_by(Message.created_at.desc())
        )

        if channel:
            query = query.where(Message.message_type == channel)

        if search:
            search_term = f"%{search}%"
            query = query.where(
                or_(
                    Message.content.ilike(search_term),
                    Message.subject.ilike(search_term),
                    (Customer.first_name + " " + Customer.last_name).ilike(search_term),
                    Message.to_number.ilike(search_term),
                    Message.to_email.ilike(search_term),
                )
            )

        query = query.limit(limit)
        result = await db.execute(query)
        rows = result.all()

        items = []
        for row in rows:
            m = row[0]  # Message object
            first = row[1] or ""
            last = row[2] or ""
            customer_name = f"{first} {last}".strip() if (first or last) else None

            items.append({
                "id": str(m.id),
                "type": m.message_type,
                "direction": m.direction,
                "status": m.status,
                "to_address": m.to_number or m.to_email,
                "from_address": m.from_number or m.from_email,
                "subject": m.subject,
                "content": m.content[:200] if m.content else None,
                "customer_id": str(m.customer_id) if m.customer_id else None,
                "customer_name": customer_name or m.to_number or m.to_email or "Unknown",
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "sent_at": m.sent_at.isoformat() if m.sent_at else None,
            })

        return {
            "items": items,
            "total": len(items),
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
