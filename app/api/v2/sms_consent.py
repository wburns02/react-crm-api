"""
SMS Consent API - TCPA compliance management.
"""

from fastapi import APIRouter, HTTPException, status, Query, Request
from sqlalchemy import select, func
from typing import Optional
from datetime import datetime

from app.api.deps import DbSession, CurrentUser
from app.models.sms_consent import SMSConsent, SMSConsentAudit
from app.schemas.sms_consent import (
    SMSConsentCreate,
    SMSConsentUpdate,
    SMSConsentResponse,
    SMSConsentListResponse,
    SMSConsentStats,
)

router = APIRouter()

TCPA_DISCLOSURE_VERSION = "1.0"


@router.get("/", response_model=SMSConsentListResponse)
async def list_sms_consents(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    customer_id: Optional[int] = None,
    consent_status: Optional[str] = None,
    search: Optional[str] = None,
):
    """List SMS consents with pagination and filtering."""
    # Base query
    query = select(SMSConsent)

    # Apply filters
    if customer_id:
        query = query.where(SMSConsent.customer_id == customer_id)

    if consent_status:
        query = query.where(SMSConsent.consent_status == consent_status)

    if search:
        query = query.where(SMSConsent.phone_number.ilike(f"%{search}%"))

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(SMSConsent.created_at.desc())

    # Execute query
    result = await db.execute(query)
    consents = result.scalars().all()

    return SMSConsentListResponse(
        items=consents,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/stats", response_model=SMSConsentStats)
async def get_consent_stats(
    db: DbSession,
    current_user: CurrentUser,
):
    """Get SMS consent statistics."""
    # Total count
    total_result = await db.execute(select(func.count()).select_from(SMSConsent))
    total = total_result.scalar() or 0

    # Opted in count
    opted_in_result = await db.execute(
        select(func.count()).select_from(SMSConsent).where(SMSConsent.consent_status == "opted_in")
    )
    opted_in = opted_in_result.scalar() or 0

    # Opted out count
    opted_out_result = await db.execute(
        select(func.count()).select_from(SMSConsent).where(SMSConsent.consent_status == "opted_out")
    )
    opted_out = opted_out_result.scalar() or 0

    # Pending count
    pending_result = await db.execute(
        select(func.count()).select_from(SMSConsent).where(SMSConsent.consent_status == "pending")
    )
    pending = pending_result.scalar() or 0

    # Double opt-in rate
    double_opt_in_result = await db.execute(
        select(func.count())
        .select_from(SMSConsent)
        .where(SMSConsent.consent_status == "opted_in", SMSConsent.double_opt_in_confirmed == True)
    )
    double_opt_in_count = double_opt_in_result.scalar() or 0
    double_opt_in_rate = (double_opt_in_count / opted_in * 100) if opted_in > 0 else 0

    return SMSConsentStats(
        total=total,
        opted_in=opted_in,
        opted_out=opted_out,
        pending=pending,
        double_opt_in_rate=round(double_opt_in_rate, 2),
    )


@router.get("/{consent_id}", response_model=SMSConsentResponse)
async def get_sms_consent(
    consent_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a single SMS consent by ID."""
    result = await db.execute(select(SMSConsent).where(SMSConsent.id == consent_id))
    consent = result.scalar_one_or_none()

    if not consent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SMS consent record not found",
        )

    return consent


@router.post("/opt-in", response_model=SMSConsentResponse, status_code=status.HTTP_201_CREATED)
async def record_opt_in(
    consent_data: SMSConsentCreate,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
):
    """Record an SMS opt-in."""
    # Check if consent already exists for this customer/phone
    existing = await db.execute(
        select(SMSConsent).where(
            SMSConsent.customer_id == consent_data.customer_id, SMSConsent.phone_number == consent_data.phone_number
        )
    )
    existing_consent = existing.scalar_one_or_none()

    if existing_consent:
        # Update existing consent
        existing_consent.consent_status = "opted_in"
        existing_consent.opt_in_timestamp = datetime.utcnow()
        existing_consent.opt_in_ip_address = request.client.host if request.client else None
        existing_consent.tcpa_disclosure_version = TCPA_DISCLOSURE_VERSION
        existing_consent.tcpa_disclosure_accepted = True

        # Create audit log
        audit = SMSConsentAudit(
            consent_id=existing_consent.id,
            action="opt_in",
            previous_status=existing_consent.consent_status,
            new_status="opted_in",
            ip_address=request.client.host if request.client else None,
            performed_by=str(current_user.id),
        )
        db.add(audit)

        await db.commit()
        await db.refresh(existing_consent)
        return existing_consent

    # Create new consent
    data = consent_data.model_dump()
    data["consent_status"] = "opted_in"
    data["opt_in_timestamp"] = datetime.utcnow()
    data["opt_in_ip_address"] = request.client.host if request.client else None
    data["tcpa_disclosure_version"] = TCPA_DISCLOSURE_VERSION
    data["tcpa_disclosure_accepted"] = True

    consent = SMSConsent(**data)
    db.add(consent)
    await db.commit()
    await db.refresh(consent)

    # Create audit log
    audit = SMSConsentAudit(
        consent_id=consent.id,
        action="opt_in",
        previous_status=None,
        new_status="opted_in",
        ip_address=request.client.host if request.client else None,
        performed_by=str(current_user.id),
    )
    db.add(audit)
    await db.commit()

    return consent


@router.post("/opt-out", response_model=SMSConsentResponse)
async def record_opt_out(
    customer_id: int,
    phone_number: str,
    reason: Optional[str] = None,
    request: Request = None,
    db: DbSession = None,
    current_user: CurrentUser = None,
):
    """Record an SMS opt-out (STOP keyword processing)."""
    # Find existing consent
    result = await db.execute(
        select(SMSConsent).where(SMSConsent.customer_id == customer_id, SMSConsent.phone_number == phone_number)
    )
    consent = result.scalar_one_or_none()

    if not consent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No consent record found for this customer/phone",
        )

    previous_status = consent.consent_status
    consent.consent_status = "opted_out"
    consent.opt_out_timestamp = datetime.utcnow()
    consent.opt_out_reason = reason

    # Create audit log
    audit = SMSConsentAudit(
        consent_id=consent.id,
        action="opt_out",
        previous_status=previous_status,
        new_status="opted_out",
        ip_address=request.client.host if request and request.client else None,
        performed_by=str(current_user.id) if current_user else "system",
    )
    db.add(audit)

    await db.commit()
    await db.refresh(consent)
    return consent


@router.patch("/{consent_id}/toggle", response_model=SMSConsentResponse)
async def toggle_consent(
    consent_id: int,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
):
    """Toggle SMS consent status."""
    result = await db.execute(select(SMSConsent).where(SMSConsent.id == consent_id))
    consent = result.scalar_one_or_none()

    if not consent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SMS consent record not found",
        )

    previous_status = consent.consent_status
    new_status = "opted_out" if consent.consent_status == "opted_in" else "opted_in"

    consent.consent_status = new_status
    if new_status == "opted_in":
        consent.opt_in_timestamp = datetime.utcnow()
        consent.opt_in_ip_address = request.client.host if request.client else None
    else:
        consent.opt_out_timestamp = datetime.utcnow()

    # Create audit log
    audit = SMSConsentAudit(
        consent_id=consent.id,
        action="toggle",
        previous_status=previous_status,
        new_status=new_status,
        ip_address=request.client.host if request.client else None,
        performed_by=str(current_user.id),
    )
    db.add(audit)

    await db.commit()
    await db.refresh(consent)
    return consent


@router.delete("/{consent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_consent(
    consent_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete an SMS consent record."""
    result = await db.execute(select(SMSConsent).where(SMSConsent.id == consent_id))
    consent = result.scalar_one_or_none()

    if not consent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SMS consent record not found",
        )

    await db.delete(consent)
    await db.commit()
