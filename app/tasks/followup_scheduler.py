"""Post-service follow-up and Google review request scheduling."""

from datetime import datetime, timedelta
import logging

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models.work_order import WorkOrder
from app.models.customer import Customer

logger = logging.getLogger(__name__)

# Follow-up delays
FOLLOWUP_DELAY_HOURS = 24
REVIEW_REQUEST_DELAY_HOURS = 72
GOOGLE_REVIEW_URL = "https://g.page/r/macseptic/review"


async def send_followup_sms(phone: str, customer_name: str, wo_number: str):
    """Send a post-service follow-up SMS."""
    from app.services.twilio_service import send_sms
    message = (
        f"Hi {customer_name}, thank you for choosing MAC Septic Services! "
        f"We hope your recent service (#{wo_number}) went well. "
        f"If you have any questions or concerns, reply to this message or call us."
    )
    try:
        await send_sms(phone, message)
        logger.info(f"Sent follow-up SMS to {phone} for WO {wo_number}")
    except Exception as e:
        logger.error(f"Failed to send follow-up SMS to {phone}: {e}")


async def send_review_request_sms(phone: str, customer_name: str):
    """Send Google review request SMS."""
    from app.services.twilio_service import send_sms
    message = (
        f"Hi {customer_name}, we'd love your feedback! "
        f"If you were happy with our service, please leave us a Google review: "
        f"{GOOGLE_REVIEW_URL} — Thank you!"
    )
    try:
        await send_sms(phone, message)
        logger.info(f"Sent review request SMS to {phone}")
    except Exception as e:
        logger.error(f"Failed to send review request SMS to {phone}: {e}")


async def process_followups():
    """Check for completed work orders that need follow-up or review requests."""
    async with async_session_maker() as db:
        now = datetime.utcnow()

        # Find WOs completed 24h ago that haven't had follow-up
        followup_cutoff = now - timedelta(hours=FOLLOWUP_DELAY_HOURS)
        review_cutoff = now - timedelta(hours=REVIEW_REQUEST_DELAY_HOURS)

        # Follow-up SMS (24h after completion)
        result = await db.execute(
            select(WorkOrder, Customer)
            .join(Customer, WorkOrder.customer_id == Customer.id)
            .where(
                and_(
                    WorkOrder.status == "completed",
                    WorkOrder.completed_date <= followup_cutoff,
                    WorkOrder.completed_date > followup_cutoff - timedelta(hours=1),
                )
            )
        )
        for wo, cust in result.all():
            if cust.phone:
                await send_followup_sms(
                    cust.phone, cust.first_name or "Valued Customer", wo.wo_number or str(wo.id)
                )

        # Google review request (72h after completion)
        result2 = await db.execute(
            select(WorkOrder, Customer)
            .join(Customer, WorkOrder.customer_id == Customer.id)
            .where(
                and_(
                    WorkOrder.status == "completed",
                    WorkOrder.completed_date <= review_cutoff,
                    WorkOrder.completed_date > review_cutoff - timedelta(hours=1),
                )
            )
        )
        for wo, cust in result2.all():
            if cust.phone:
                await send_review_request_sms(cust.phone, cust.first_name or "Valued Customer")

        logger.info("Follow-up scheduler run complete")
