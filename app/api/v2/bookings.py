"""
Booking API endpoints for direct book & pay services.

Supports test mode for development without real payment processing.
"""
import logging
from datetime import datetime, time
from decimal import Decimal
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select, and_

from app.api.deps import DbSession, CurrentUser
from app.models.booking import Booking
from app.models.customer import Customer
from app.schemas.booking import (
    BookingCreate,
    BookingResponse,
    BookingCaptureRequest,
    BookingCaptureResponse,
    PricingInfo,
    BookingListResponse,
)
from app.services.clover_service import get_clover_service

logger = logging.getLogger(__name__)

router = APIRouter()

# Pricing configuration
PUMPING_PRICING = {
    "service_type": "pumping",
    "base_price": Decimal("575.00"),
    "included_gallons": 1750,
    "overage_rate": Decimal("0.45"),
    "preauth_amount": Decimal("775.00"),  # Base + $200 buffer
    "description": "Septic Tank Pumping - up to 1,750 gallons",
}

# Time slot mapping
TIME_SLOTS = {
    "morning": (time(8, 0), time(12, 0)),
    "afternoon": (time(12, 0), time(17, 0)),
    "any": (time(8, 0), time(17, 0)),
}


@router.get("/pricing", response_model=PricingInfo)
async def get_pricing(
    service_type: str = Query("pumping", description="Service type"),
) -> PricingInfo:
    """
    Get pricing information for a service type.

    This is a PUBLIC endpoint - no authentication required.
    """
    if service_type == "pumping":
        return PricingInfo(**PUMPING_PRICING)

    raise HTTPException(status_code=404, detail=f"Unknown service type: {service_type}")


@router.post("/create", response_model=BookingResponse)
async def create_booking(
    db: DbSession,
    booking_data: BookingCreate,
) -> BookingResponse:
    """
    Create a new booking with payment pre-authorization.

    This is a PUBLIC endpoint - no authentication required.

    Set test_mode=true to simulate payment without calling Clover.
    """
    # Get pricing for service type
    if booking_data.service_type != "pumping":
        raise HTTPException(status_code=400, detail="Only pumping service is available for direct booking")

    pricing = PUMPING_PRICING

    # Require overage acknowledgment
    if not booking_data.overage_acknowledged:
        raise HTTPException(
            status_code=400,
            detail="You must acknowledge the overage pricing policy"
        )

    # Get time window from slot
    time_start, time_end = TIME_SLOTS.get(booking_data.time_slot or "any", TIME_SLOTS["any"])

    # Process payment (pre-authorize)
    clover = get_clover_service()
    preauth_cents = int(pricing["preauth_amount"] * 100)

    if booking_data.test_mode:
        # Test mode - simulate payment
        payment_result = await clover.preauthorize(
            amount_cents=preauth_cents,
            token="test_token",
            description=f"Septic Pumping - {booking_data.scheduled_date}",
            test_mode=True
        )
    else:
        # Live mode - require token
        if not booking_data.payment_token:
            raise HTTPException(
                status_code=400,
                detail="Payment token is required for live bookings"
            )
        payment_result = await clover.preauthorize(
            amount_cents=preauth_cents,
            token=booking_data.payment_token,
            description=f"Septic Pumping - {booking_data.scheduled_date}",
            test_mode=False
        )

    if not payment_result.success:
        raise HTTPException(
            status_code=402,
            detail=f"Payment authorization failed: {payment_result.error_message}"
        )

    # Create booking record
    booking = Booking(
        customer_first_name=booking_data.first_name,
        customer_last_name=booking_data.last_name,
        customer_email=booking_data.email,
        customer_phone=booking_data.phone,
        service_address=booking_data.service_address,

        service_type=booking_data.service_type,
        scheduled_date=booking_data.scheduled_date,
        time_slot=booking_data.time_slot,
        time_window_start=time_start,
        time_window_end=time_end,

        base_price=pricing["base_price"],
        included_gallons=pricing["included_gallons"],
        overage_rate=pricing["overage_rate"],
        preauth_amount=pricing["preauth_amount"],

        clover_charge_id=payment_result.charge_id,
        payment_status="preauthorized" if not booking_data.test_mode else "test",
        is_test=booking_data.test_mode,

        overage_acknowledged=booking_data.overage_acknowledged,
        sms_consent=booking_data.sms_consent,
        customer_notes=booking_data.notes,

        status="confirmed",
    )

    db.add(booking)
    await db.commit()
    await db.refresh(booking)

    logger.info(
        f"Booking created: {booking.id} for {booking.customer_first_name} {booking.customer_last_name} "
        f"on {booking.scheduled_date} ({'TEST' if booking.is_test else 'LIVE'})"
    )

    return BookingResponse.model_validate(booking)


@router.get("/{booking_id}", response_model=BookingResponse)
async def get_booking(
    db: DbSession,
    booking_id: str,
) -> BookingResponse:
    """
    Get booking details by ID.

    This is a PUBLIC endpoint - allows customers to view their booking.
    """
    result = await db.execute(
        select(Booking).where(Booking.id == booking_id)
    )
    booking = result.scalar_one_or_none()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    return BookingResponse.model_validate(booking)


@router.post("/{booking_id}/capture", response_model=BookingCaptureResponse)
async def capture_booking_payment(
    db: DbSession,
    booking_id: str,
    capture_data: BookingCaptureRequest,
    current_user: CurrentUser,
) -> BookingCaptureResponse:
    """
    Capture payment after service completion.

    Requires authentication (admin/technician).

    Calculates final amount based on actual gallons pumped.
    """
    result = await db.execute(
        select(Booking).where(Booking.id == booking_id)
    )
    booking = result.scalar_one_or_none()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.payment_status not in ("preauthorized", "test"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot capture payment with status: {booking.payment_status}"
        )

    # Calculate final amount
    booking.actual_gallons = capture_data.actual_gallons
    final_amount, overage_gallons, overage_amount = booking.calculate_final_amount()

    booking.overage_gallons = overage_gallons
    booking.overage_amount = Decimal(str(overage_amount))
    booking.final_amount = Decimal(str(final_amount))

    # Capture payment
    clover = get_clover_service()
    final_cents = int(final_amount * 100)

    payment_result = await clover.capture(
        charge_id=booking.clover_charge_id,
        amount_cents=final_cents,
        test_mode=booking.is_test
    )

    if not payment_result.success:
        raise HTTPException(
            status_code=402,
            detail=f"Payment capture failed: {payment_result.error_message}"
        )

    booking.payment_status = "captured" if not booking.is_test else "test_captured"
    booking.captured_at = datetime.utcnow()
    booking.status = "completed"

    if capture_data.notes:
        booking.internal_notes = capture_data.notes

    await db.commit()
    await db.refresh(booking)

    logger.info(
        f"Payment captured for booking {booking.id}: ${final_amount:.2f} "
        f"({booking.actual_gallons} gallons, {overage_gallons} overage) "
        f"({'TEST' if booking.is_test else 'LIVE'})"
    )

    return BookingCaptureResponse(
        id=booking.id,
        actual_gallons=booking.actual_gallons,
        overage_gallons=booking.overage_gallons,
        overage_amount=booking.overage_amount,
        final_amount=booking.final_amount,
        payment_status=booking.payment_status,
        captured_at=booking.captured_at,
    )


@router.get("/", response_model=BookingListResponse)
async def list_bookings(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    include_test: bool = Query(False, description="Include test bookings"),
) -> BookingListResponse:
    """
    List bookings (admin only).

    Requires authentication.
    """
    query = select(Booking)

    if not include_test:
        query = query.where(Booking.is_test == False)

    if status:
        query = query.where(Booking.status == status)

    query = query.order_by(Booking.created_at.desc())

    # Get total count
    count_result = await db.execute(
        select(Booking.id).where(
            Booking.is_test == False if not include_test else True
        )
    )
    total = len(count_result.all())

    # Get page
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    bookings = result.scalars().all()

    return BookingListResponse(
        items=[BookingResponse.model_validate(b) for b in bookings],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/{booking_id}/cancel")
async def cancel_booking(
    db: DbSession,
    booking_id: str,
    current_user: CurrentUser,
) -> dict:
    """
    Cancel a booking and refund the pre-authorization.

    Requires authentication.
    """
    result = await db.execute(
        select(Booking).where(Booking.id == booking_id)
    )
    booking = result.scalar_one_or_none()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.status == "cancelled":
        raise HTTPException(status_code=400, detail="Booking already cancelled")

    if booking.payment_status == "captured":
        raise HTTPException(
            status_code=400,
            detail="Cannot cancel - payment already captured. Use refund instead."
        )

    # Release pre-authorization (Clover auto-releases after 7 days, but we can void it)
    # For test mode, just mark as cancelled
    booking.status = "cancelled"
    booking.payment_status = "cancelled"

    await db.commit()

    logger.info(f"Booking {booking.id} cancelled")

    return {"status": "cancelled", "booking_id": booking_id}
