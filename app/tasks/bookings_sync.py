"""
Microsoft Bookings Sync Background Task

Runs every 10 minutes to poll Microsoft Bookings for new/updated/cancelled appointments
and sync them to CRM work orders.
"""

import logging
import uuid
from datetime import date, timedelta, time as dt_time
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.services.ms365_bookings_service import MS365BookingsService
from app.database import async_session_maker
from app.models.technician import Technician

logger = logging.getLogger(__name__)

# Region-based technician assignment
# Maps state/region keywords to technician microsoft_email for lookup
REGION_TECH_MAP = [
    # Central Texas (default) → Ronnie Ransom
    {"states": ["TX", "texas"], "keywords": [], "tech_email": "ronnie@macseptic.com", "is_default": True},
    # South Carolina → Chandler
    {"states": ["SC", "south carolina"], "keywords": ["charleston", "columbia", "greenville", "spartanburg", "myrtle beach"],
     "tech_email": "chandler@macseptic.com", "is_default": False},
    # Tennessee → John Harvey
    {"states": ["TN", "tennessee"], "keywords": ["nashville", "memphis", "knoxville", "chattanooga", "murfreesboro"],
     "tech_email": "jharvey@macseptic.com", "is_default": False},
]


async def assign_technician_by_region(db, service_address: str) -> uuid.UUID | None:
    """Auto-assign a technician based on service address region."""
    addr = (service_address or "").lower()

    matched_email = None
    default_email = None

    for region in REGION_TECH_MAP:
        if region.get("is_default"):
            default_email = region["tech_email"]

        # Check state abbreviation or name in address
        for state in region["states"]:
            if f", {state.lower()}" in addr or f" {state.lower()} " in addr or addr.endswith(f" {state.lower()}"):
                matched_email = region["tech_email"]
                break

        # Check city keywords
        if not matched_email:
            for kw in region["keywords"]:
                if kw.lower() in addr:
                    matched_email = region["tech_email"]
                    break

        if matched_email:
            break

    # Use default (Texas/Ronnie) if no match
    tech_email = matched_email or default_email
    if not tech_email:
        return None

    result = await db.execute(
        select(Technician).where(Technician.microsoft_email == tech_email)
    )
    tech = result.scalar_one_or_none()
    return tech.id if tech else None

_scheduler: AsyncIOScheduler | None = None


async def sync_bookings():
    """Poll Microsoft Bookings and sync appointments to work orders."""
    if not MS365BookingsService.is_configured():
        return

    logger.debug("Bookings sync: starting")

    try:
        # Get appointments for next 30 days
        today = date.today()
        end = today + timedelta(days=30)
        appointments = await MS365BookingsService.get_appointments(
            start_date=today.isoformat(),
            end_date=end.isoformat(),
        )

        if not appointments:
            logger.debug("Bookings sync: no appointments found")
            return

        from app.models.work_order import WorkOrder
        from app.models.customer import Customer

        async with async_session_maker() as db:
            synced = 0
            for appt in appointments:
                appt_id = appt.get("id")
                if not appt_id:
                    continue

                appt_status = appt.get("status", "")

                # Skip cancelled appointments (handle cancellation below)
                # Check if we already have a work order for this appointment
                result = await db.execute(
                    select(WorkOrder).where(
                        WorkOrder.ms_booking_appointment_id == appt_id
                    )
                )
                existing_wo = result.scalar_one_or_none()

                if appt_status == "cancelled" and existing_wo:
                    # Cancel the work order if not already cancelled
                    if existing_wo.status != "canceled":
                        existing_wo.status = "canceled"
                        existing_wo.notes = (existing_wo.notes or "") + "\n[Auto-cancelled: MS Bookings cancellation]"
                        synced += 1
                    continue

                if existing_wo:
                    # Already synced, skip
                    continue

                if appt_status == "cancelled":
                    # Don't create WO for already-cancelled appointments
                    continue

                # Parse appointment data
                data = MS365BookingsService.parse_appointment_to_work_order_data(appt)

                # Try to find or create customer
                customer_id = None
                if data["customer_email"]:
                    result = await db.execute(
                        select(Customer).where(
                            Customer.email == data["customer_email"]
                        )
                    )
                    customer = result.scalar_one_or_none()
                    if customer:
                        customer_id = customer.id
                    elif data["customer_name"]:
                        # Create customer
                        parts = data["customer_name"].split(" ", 1)
                        new_customer = Customer(
                            id=uuid.uuid4(),
                            first_name=parts[0],
                            last_name=parts[1] if len(parts) > 1 else "",
                            email=data["customer_email"],
                            phone=data["customer_phone"],
                            address_line1=data["service_address"],
                        )
                        db.add(new_customer)
                        await db.flush()
                        customer_id = new_customer.id

                # Parse times
                time_start = None
                time_end = None
                if data["time_start"]:
                    try:
                        h, m = data["time_start"].split(":")
                        time_start = dt_time(int(h), int(m))
                    except (ValueError, TypeError):
                        pass
                if data["time_end"]:
                    try:
                        h, m = data["time_end"].split(":")
                        time_end = dt_time(int(h), int(m))
                    except (ValueError, TypeError):
                        pass

                # Parse scheduled date
                scheduled = None
                if data["scheduled_date"]:
                    try:
                        scheduled = date.fromisoformat(data["scheduled_date"])
                    except ValueError:
                        scheduled = today

                # Duration in hours
                duration_hours = 2.0
                if data["duration_minutes"]:
                    try:
                        # Duration format from Bookings is ISO 8601 (e.g. "PT1H30M")
                        dur = data["duration_minutes"]
                        if isinstance(dur, str) and "PT" in dur:
                            hours = 0
                            minutes = 0
                            dur = dur.replace("PT", "")
                            if "H" in dur:
                                h_part, dur = dur.split("H")
                                hours = int(h_part)
                            if "M" in dur:
                                m_part = dur.replace("M", "")
                                minutes = int(m_part)
                            duration_hours = hours + minutes / 60
                    except (ValueError, TypeError):
                        pass

                # Auto-assign technician based on service address region
                tech_id = await assign_technician_by_region(db, data["service_address"])

                # Create work order
                wo = WorkOrder(
                    id=uuid.uuid4(),
                    customer_id=customer_id,
                    technician_id=tech_id,
                    job_type=data["job_type"],
                    status="scheduled",
                    priority="normal",
                    scheduled_date=scheduled,
                    time_window_start=time_start,
                    time_window_end=time_end,
                    estimated_duration_hours=duration_hours,
                    service_address_line1=data["service_address"],
                    notes=f"MS Bookings: {data['service_name']}\n{data['notes']}".strip(),
                    ms_booking_appointment_id=appt_id,
                    booking_source="microsoft_bookings",
                )
                db.add(wo)
                synced += 1

            if synced > 0:
                await db.commit()
                logger.info("Bookings sync: synced %d appointments", synced)
            else:
                logger.debug("Bookings sync: nothing new to sync")

    except Exception as e:
        logger.error("Bookings sync error: %s", e)


def start_bookings_sync():
    """Start the bookings sync scheduler."""
    global _scheduler
    if not MS365BookingsService.is_configured():
        logger.info("Bookings sync disabled: MS365 Bookings not configured")
        return

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(sync_bookings, "interval", minutes=10, id="bookings_sync")
    _scheduler.start()
    logger.info("Bookings sync scheduler started (every 10 min)")


def stop_bookings_sync():
    """Stop the bookings sync scheduler."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Bookings sync scheduler stopped")
