"""
Inbound Email Poller Background Task

Runs every 5 minutes to fetch unread emails from monitored mailbox,
match to customers, and create leads/service requests.
"""

import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.services.ms365_email_service import MS365EmailService
from app.database import async_session_maker

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def poll_inbound_emails():
    """Fetch unread emails, match customers, log to inbound_emails table."""
    if not MS365EmailService.is_configured():
        return

    try:
        emails = await MS365EmailService.get_unread_emails(top=20)
        if not emails:
            return

        logger.info("Email poller: %d unread emails found", len(emails))

        from app.models.inbound_email import InboundEmail
        from app.models.customer import Customer

        async with async_session_maker() as db:
            for email_data in emails:
                msg_id = email_data.get("id", "")
                sender_email, sender_name = MS365EmailService.parse_sender(email_data)

                # Skip if already processed
                existing = await db.execute(
                    select(InboundEmail).where(InboundEmail.message_id == msg_id)
                )
                if existing.scalar_one_or_none():
                    continue

                # Try to match customer by email
                customer_id = None
                if sender_email:
                    result = await db.execute(
                        select(Customer.id).where(Customer.email == sender_email)
                    )
                    row = result.first()
                    if row:
                        customer_id = row[0]

                # Store the email
                inbound = InboundEmail(
                    message_id=msg_id,
                    sender_email=sender_email,
                    sender_name=sender_name,
                    subject=email_data.get("subject", ""),
                    body_preview=email_data.get("bodyPreview", ""),
                    received_at=email_data.get("receivedDateTime", datetime.utcnow().isoformat()),
                    customer_id=customer_id,
                    action_taken="matched_customer" if customer_id else "no_match",
                )
                db.add(inbound)

                # Mark as read in mailbox
                await MS365EmailService.mark_as_read(msg_id)

            await db.commit()

    except Exception as e:
        logger.error("Email poller error: %s", e)


def start_email_poller():
    """Start the email poller scheduler."""
    global _scheduler
    if not MS365EmailService.is_configured():
        logger.info("Email poller disabled: MS365 mailbox not configured")
        return

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(poll_inbound_emails, "interval", minutes=5, id="email_poller")
    _scheduler.start()
    logger.info("Email poller started (every 5 min)")


def stop_email_poller():
    """Stop the email poller scheduler."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Email poller stopped")
