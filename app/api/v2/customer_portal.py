"""
Customer Self-Service Portal

Allows customers to log in via OTP (no password) and view their
own service history, invoices, and upcoming appointments.

Auth Flow:
1. POST /customer-portal/request-code — sends OTP via SMS or email
2. POST /customer-portal/verify-code  — exchanges OTP for JWT
3. All other endpoints require Bearer JWT with role="customer"
"""

import random
import uuid
import logging
from datetime import datetime, timedelta, date
from typing import Optional, Annotated

from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import select, or_, desc, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DbSession, get_db
from app.config import settings
from app.models.customer import Customer
from app.models.work_order import WorkOrder
from app.models.invoice import Invoice
from app.models.service_interval import CustomerServiceSchedule, ServiceInterval
from app.services.cache_service import get_cache_service

logger = logging.getLogger(__name__)
router = APIRouter()

# Bearer security — auto_error=False so we return a clean 401
_bearer = HTTPBearer(auto_error=False)

# ---------------------------------------------------------------------------
# Pydantic request schemas
# ---------------------------------------------------------------------------


class RequestCodeBody(BaseModel):
    contact: str  # phone OR email


class VerifyCodeBody(BaseModel):
    customer_id: str
    code: str


class RequestServiceBody(BaseModel):
    service_type: str
    preferred_date: Optional[str] = None  # ISO date string e.g. "2026-03-01"
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Redis OTP helpers
# ---------------------------------------------------------------------------

OTP_TTL = 600  # 10 minutes


async def _store_otp(customer_id: str, code: str) -> None:
    cache = get_cache_service()
    ok = await cache.set(f"otp:{customer_id}", code, ttl=OTP_TTL)
    if not ok:
        logger.warning(
            "Redis unavailable — OTP for customer %s could not be stored. Code: %s",
            customer_id,
            code,
        )


async def _get_otp(customer_id: str) -> Optional[str]:
    cache = get_cache_service()
    return await cache.get(f"otp:{customer_id}")


async def _delete_otp(customer_id: str) -> None:
    cache = get_cache_service()
    await cache.delete(f"otp:{customer_id}")


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

CUSTOMER_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days


def _create_customer_token(customer_id: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=CUSTOMER_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": customer_id, "role": "customer", "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


async def get_current_customer_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> str:
    """
    FastAPI dependency — validates customer portal Bearer JWT.
    Returns customer UUID (str) or raises HTTP 401.
    """
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate customer credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not credentials:
        raise exc
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        customer_id: str = payload.get("sub")
        role: str = payload.get("role")
        if customer_id is None or role != "customer":
            raise exc
        return customer_id
    except JWTError:
        logger.warning("Customer portal JWT validation failed")
        raise exc


# Convenience type alias
CustomerPortalAuth = Annotated[str, Depends(get_current_customer_id)]
PortalDb = Annotated[AsyncSession, Depends(get_db)]


# ---------------------------------------------------------------------------
# Public endpoints: OTP request & verify
# ---------------------------------------------------------------------------


@router.post("/request-code")
async def request_code(body: RequestCodeBody, db: DbSession):
    """
    Step 1 — request a 6-digit OTP.

    Looks up customer by phone OR email. Stores OTP in Redis (TTL=10 min)
    and sends it via Twilio SMS if the contact is a phone number.
    Returns customer_id so the client can pass it to /verify-code.
    """
    contact = body.contact.strip()
    digits_only = "".join(c for c in contact if c.isdigit())

    stmt = select(Customer).where(
        or_(
            Customer.email == contact,
            Customer.phone == contact,
            Customer.phone == digits_only,
        )
    )
    result = await db.execute(stmt)
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No account found for that phone number or email address.",
        )

    code = str(random.randint(100000, 999999))
    customer_id_str = str(customer.id)

    await _store_otp(customer_id_str, code)

    is_phone = len(digits_only) >= 10 and "@" not in contact
    sms_sent = False

    if is_phone:
        try:
            from app.services.twilio_service import TwilioService

            twilio = TwilioService()
            if twilio.is_configured:
                await twilio.send_sms(
                    to=contact,
                    body=(
                        f"Your MAC Service Platform verification code is: {code}. "
                        "Valid for 10 minutes. Do not share this code."
                    ),
                )
                sms_sent = True
                logger.info("OTP SMS sent to customer %s", customer_id_str)
            else:
                logger.warning(
                    "Twilio not configured — OTP for customer %s: %s",
                    customer_id_str,
                    code,
                )
        except Exception as exc:
            logger.error("Failed to send OTP SMS: %s", exc)
            # Don't fail the request; OTP is still stored in Redis
    else:
        # Email flow — log OTP (email sending not implemented here)
        logger.info(
            "Email OTP for customer %s (%s): %s", customer_id_str, contact, code
        )

    return {
        "success": True,
        "message": "Verification code sent" if sms_sent else "Verification code generated",
        "customer_id": customer_id_str,
        "sms_sent": sms_sent,
    }


@router.post("/verify-code")
async def verify_code(body: VerifyCodeBody, db: DbSession):
    """
    Step 2 — exchange OTP for a JWT.

    Validates the OTP against Redis. On success, deletes the OTP
    (single-use) and returns a signed JWT with role="customer".
    """
    try:
        customer_uuid = uuid.UUID(body.customer_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid customer_id format.",
        )

    result = await db.execute(select(Customer).where(Customer.id == customer_uuid))
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found.",
        )

    stored_code = await _get_otp(body.customer_id)
    if stored_code is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification code expired or not found. Please request a new code.",
        )

    if stored_code != body.code.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid verification code.",
        )

    # Single-use: remove from Redis immediately
    await _delete_otp(body.customer_id)

    token = _create_customer_token(body.customer_id)
    logger.info("Customer portal login successful: %s", body.customer_id)

    return {
        "success": True,
        "access_token": token,
        "token_type": "bearer",
        "customer_id": body.customer_id,
        "customer_name": f"{customer.first_name or ''} {customer.last_name or ''}".strip(),
    }


# ---------------------------------------------------------------------------
# Protected portal endpoints (require valid customer JWT)
# ---------------------------------------------------------------------------


@router.get("/my-account")
async def get_my_account(
    customer_id: CustomerPortalAuth,
    db: PortalDb,
):
    """Return basic account info for the authenticated customer."""
    try:
        customer_uuid = uuid.UUID(customer_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid customer_id in token.")

    result = await db.execute(select(Customer).where(Customer.id == customer_uuid))
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found.")

    return {
        "id": str(customer.id),
        "first_name": customer.first_name,
        "last_name": customer.last_name,
        "email": customer.email,
        "phone": customer.phone,
        "address_line1": customer.address_line1,
        "city": customer.city,
        "state": customer.state,
        "postal_code": customer.postal_code,
        "system_type": customer.system_type,
        "manufacturer": customer.manufacturer,
    }


@router.get("/my-services")
async def get_my_services(
    customer_id: CustomerPortalAuth,
    db: PortalDb,
):
    """
    Return the customer's service history (last 20 work orders).
    """
    try:
        customer_uuid = uuid.UUID(customer_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid customer_id in token.")

    stmt = (
        select(WorkOrder)
        .where(WorkOrder.customer_id == customer_uuid)
        .order_by(desc(WorkOrder.scheduled_date))
        .limit(20)
    )
    result = await db.execute(stmt)
    work_orders = result.scalars().all()

    def _fmt_date(d):
        if d is None:
            return None
        if hasattr(d, "isoformat"):
            return d.isoformat()
        return str(d)

    return [
        {
            "id": str(wo.id),
            "work_order_number": wo.work_order_number,
            "service_type": wo.job_type,
            "status": wo.status,
            "scheduled_date": _fmt_date(wo.scheduled_date),
            "service_address": " ".join(
                filter(
                    None,
                    [
                        wo.service_address_line1,
                        wo.service_city,
                        wo.service_state,
                        wo.service_postal_code,
                    ],
                )
            ),
            "technician_name": wo.assigned_technician,
            "notes": wo.notes,
        }
        for wo in work_orders
    ]


@router.get("/my-invoices")
async def get_my_invoices(
    customer_id: CustomerPortalAuth,
    db: PortalDb,
):
    """
    Return the customer's invoices (last 20).
    """
    try:
        customer_uuid = uuid.UUID(customer_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid customer_id in token.")

    try:
        stmt = (
            select(Invoice)
            .where(Invoice.customer_id == customer_uuid)
            .order_by(desc(Invoice.created_at))
            .limit(20)
        )
        result = await db.execute(stmt)
        invoices = result.scalars().all()

        def _fmt(v):
            if v is None:
                return None
            if hasattr(v, "isoformat"):
                return v.isoformat()
            return str(v)

        return [
            {
                "id": str(inv.id),
                "invoice_number": inv.invoice_number,
                "amount_due": float(inv.amount) if inv.amount is not None else 0.0,
                "amount_paid": float(inv.paid_amount) if inv.paid_amount is not None else 0.0,
                "status": inv.status,
                "due_date": _fmt(inv.due_date),
                "created_at": _fmt(inv.created_at),
            }
            for inv in invoices
        ]
    except Exception as exc:
        logger.warning("my-invoices query failed for customer %s: %s", customer_id, exc)
        return []


@router.get("/my-next-service")
async def get_my_next_service(
    customer_id: CustomerPortalAuth,
    db: PortalDb,
):
    """
    Return the customer's next scheduled service date.

    Priority:
    1. customer_service_schedules table (explicit schedule)
    2. Last completed work order + 12 months (estimated)
    3. No data — return None
    """
    try:
        customer_uuid = uuid.UUID(customer_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid customer_id in token.")

    # 1. Check customer_service_schedules
    try:
        sched_stmt = (
            select(CustomerServiceSchedule, ServiceInterval)
            .join(
                ServiceInterval,
                CustomerServiceSchedule.service_interval_id == ServiceInterval.id,
            )
            .where(
                CustomerServiceSchedule.customer_id == customer_uuid,
                CustomerServiceSchedule.status.in_(["upcoming", "due", "overdue"]),
            )
            .order_by(CustomerServiceSchedule.next_due_date)
            .limit(1)
        )
        sched_result = await db.execute(sched_stmt)
        row = sched_result.first()

        if row:
            sched, interval = row
            return {
                "next_service_date": sched.next_due_date.isoformat()
                if sched.next_due_date
                else None,
                "estimated": False,
                "service_type": interval.service_type,
                "notes": sched.notes,
            }
    except Exception as exc:
        logger.warning(
            "my-next-service schedule lookup failed for customer %s: %s",
            customer_id,
            exc,
        )

    # 2. Estimate from last completed work order + 12 months
    try:
        last_wo_stmt = (
            select(WorkOrder)
            .where(
                WorkOrder.customer_id == customer_uuid,
                WorkOrder.status == "completed",
            )
            .order_by(desc(WorkOrder.scheduled_date))
            .limit(1)
        )
        wo_result = await db.execute(last_wo_stmt)
        last_wo = wo_result.scalar_one_or_none()

        if last_wo and last_wo.scheduled_date:
            svc_date = last_wo.scheduled_date
            # scheduled_date may be a date or datetime
            if hasattr(svc_date, "date"):
                svc_date = svc_date.date()
            estimated_date = date(
                svc_date.year + (1 if svc_date.month <= 12 else 0),
                ((svc_date.month % 12) + 1) if svc_date.month == 12 else svc_date.month + 1,
                svc_date.day,
            )
            # Simpler: add ~365 days
            from datetime import timedelta as td

            estimated_date = svc_date + td(days=365)

            return {
                "next_service_date": estimated_date.isoformat(),
                "estimated": True,
                "service_type": "Annual Pumping",
                "notes": "Estimated based on last service date",
            }
    except Exception as exc:
        logger.warning(
            "my-next-service WO estimation failed for customer %s: %s",
            customer_id,
            exc,
        )

    return {
        "next_service_date": None,
        "estimated": False,
        "service_type": None,
        "notes": "No service history found",
    }


@router.post("/request-service")
async def request_service(
    body: RequestServiceBody,
    customer_id: CustomerPortalAuth,
    db: PortalDb,
):
    """
    Create a new work order (status=pending) on behalf of the customer.
    """
    try:
        customer_uuid = uuid.UUID(customer_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid customer_id in token.")

    # Verify customer exists
    cust_result = await db.execute(select(Customer).where(Customer.id == customer_uuid))
    customer = cust_result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found.")

    # Parse preferred date
    preferred = None
    if body.preferred_date:
        try:
            preferred = date.fromisoformat(body.preferred_date)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid preferred_date format. Use YYYY-MM-DD.",
            )

    # Generate work order number
    import time

    wo_number = f"WO-P{int(time.time()) % 1000000:06d}"

    portal_note = "Requested via customer portal"
    combined_notes = (
        f"{portal_note}\n{body.notes}" if body.notes else portal_note
    )

    new_wo = WorkOrder(
        id=uuid.uuid4(),
        customer_id=customer_uuid,
        work_order_number=wo_number,
        job_type=body.service_type,
        status="pending",
        scheduled_date=preferred,
        notes=combined_notes,
        # Copy service address from customer record
        service_address_line1=customer.address_line1,
        service_city=customer.city,
        service_state=customer.state,
        service_postal_code=customer.postal_code,
        created_at=datetime.utcnow(),
    )

    db.add(new_wo)
    await db.commit()
    await db.refresh(new_wo)

    logger.info(
        "Customer portal work order created: %s for customer %s",
        wo_number,
        customer_id,
    )

    return {
        "success": True,
        "work_order_id": str(new_wo.id),
        "work_order_number": new_wo.work_order_number,
        "status": "pending",
        "scheduled_date": preferred.isoformat() if preferred else None,
    }
