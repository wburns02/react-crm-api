"""Service Reminder Scheduler - Automatic reminders for upcoming service dates.

Sends SMS and email reminders to customers based on their service schedules.
Runs daily at 8 AM to check for upcoming service dates and send reminders
at configured intervals (e.g., 30, 14, 7 days before due date).
"""

import logging
from datetime import datetime, date, timedelta
from typing import Optional
import uuid

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models.service_interval import CustomerServiceSchedule, ServiceInterval, ServiceReminder
from app.models.customer import Customer
from app.services.twilio_service import TwilioService
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler: Optional[AsyncIOScheduler] = None


def get_scheduler() -> AsyncIOScheduler:
    """Get or create the scheduler instance."""
    global scheduler
    if scheduler is None:
        scheduler = AsyncIOScheduler()
    return scheduler


async def check_and_send_reminders():
    """
    Main job: Check all service schedules and send reminders for those due soon.

    This runs daily and:
    1. Queries all 'upcoming' and 'due' schedules
    2. Calculates days until next_due_date
    3. If days_until matches one of the reminder_days_before values, sends reminders
    4. Logs all sent reminders to service_reminders table
    """
    logger.info("Starting service reminder check...")
    today = date.today()
    reminders_sent = 0
    errors = 0

    try:
        async with async_session_maker() as db:
            # Query active schedules that may need reminders
            query = select(CustomerServiceSchedule).where(CustomerServiceSchedule.status.in_(["upcoming", "due"]))
            result = await db.execute(query)
            schedules = result.scalars().all()

            logger.info(f"Found {len(schedules)} active schedules to check")

            for schedule in schedules:
                try:
                    await process_schedule_reminders(db, schedule, today)
                    reminders_sent += 1
                except Exception as e:
                    errors += 1
                    logger.error(f"Error processing schedule {schedule.id}: {e}", exc_info=True)

            await db.commit()

    except Exception as e:
        logger.error(f"Fatal error in reminder check: {e}", exc_info=True)

    logger.info(f"Reminder check complete. Processed: {reminders_sent}, Errors: {errors}")


async def process_schedule_reminders(db: AsyncSession, schedule: CustomerServiceSchedule, today: date):
    """
    Process reminders for a single schedule.

    Checks if a reminder should be sent based on days until due date
    and the configured reminder intervals.
    """
    if not schedule.next_due_date:
        return

    # Calculate days until due
    days_until = (schedule.next_due_date - today).days

    # Skip if already overdue or too far in future
    if days_until < 0:
        # Update status to overdue
        schedule.status = "overdue"
        return

    # Get the service interval to check reminder_days_before
    interval_result = await db.execute(
        select(ServiceInterval).where(ServiceInterval.id == schedule.service_interval_id)
    )
    interval = interval_result.scalar_one_or_none()

    if not interval:
        logger.warning(f"Service interval not found for schedule {schedule.id}")
        return

    # Check if today matches one of the reminder days
    reminder_days = interval.reminder_days_before or [30, 14, 7]

    if days_until not in reminder_days:
        return

    # Check if we already sent a reminder for this schedule at this interval
    existing_result = await db.execute(
        select(ServiceReminder).where(
            and_(ServiceReminder.schedule_id == schedule.id, ServiceReminder.days_before_due == days_until)
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        logger.debug(f"Reminder already sent for schedule {schedule.id} at {days_until} days")
        return

    # Get customer details
    customer_result = await db.execute(select(Customer).where(Customer.id == schedule.customer_id))
    customer = customer_result.scalar_one_or_none()

    if not customer:
        logger.warning(f"Customer not found for schedule {schedule.id}")
        return

    # Build reminder message
    customer_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip() or "Valued Customer"
    service_name = interval.name
    due_date_str = schedule.next_due_date.strftime("%B %d, %Y")

    message_body = (
        f"Hi {customer_name}! This is a reminder from Mac Septic Services. "
        f"Your {service_name} service is due on {due_date_str}. "
        f"Please call us at (512) 555-0123 to schedule your appointment. Thank you!"
    )

    email_subject = f"Service Reminder: {service_name} Due {due_date_str}"
    email_body = f"""
Dear {customer_name},

This is a friendly reminder that your {service_name} service is scheduled to be due on {due_date_str}.

To ensure your septic system continues to operate efficiently, we recommend scheduling your service appointment soon.

Please contact us at:
- Phone: (512) 555-0123
- Email: service@macseptic.com

Or visit our website to schedule online.

Thank you for choosing Mac Septic Services!

Best regards,
Mac Septic Services Team
"""

    # Send SMS if customer has phone
    sms_sent = False
    sms_message_id = None
    if customer.phone:
        try:
            twilio = TwilioService()
            if twilio.is_configured:
                sms_response = await twilio.send_sms(to=customer.phone, body=message_body)
                sms_sent = True
                sms_message_id = getattr(sms_response, "sid", None)
                logger.info(f"SMS reminder sent to {customer.phone[-4:]} for schedule {schedule.id}")
        except Exception as e:
            logger.error(f"Failed to send SMS reminder: {e}")

    # Send email if customer has email
    email_sent = False
    email_message_id = None
    if customer.email:
        try:
            email_service = EmailService()
            if email_service.is_configured:
                email_response = await email_service.send_email(
                    to=customer.email, subject=email_subject, body=email_body
                )
                if email_response.get("success"):
                    email_sent = True
                    email_message_id = email_response.get("message_id")
                    logger.info(f"Email reminder sent to {customer.email} for schedule {schedule.id}")
        except Exception as e:
            logger.error(f"Failed to send email reminder: {e}")

    # Log the reminder(s)
    now = datetime.utcnow()

    if sms_sent:
        sms_reminder = ServiceReminder(
            id=uuid.uuid4(),
            schedule_id=schedule.id,
            customer_id=schedule.customer_id,
            reminder_type="sms",
            days_before_due=days_until,
            status="sent",
            sent_at=now,
        )
        db.add(sms_reminder)

    if email_sent:
        email_reminder = ServiceReminder(
            id=uuid.uuid4(),
            schedule_id=schedule.id,
            customer_id=schedule.customer_id,
            reminder_type="email",
            days_before_due=days_until,
            status="sent",
            sent_at=now,
        )
        db.add(email_reminder)

    # Update schedule reminder status if any reminder was sent
    if sms_sent or email_sent:
        schedule.reminder_sent = True
        schedule.last_reminder_sent_at = now
        logger.info(f"Reminders sent for schedule {schedule.id}: SMS={sms_sent}, Email={email_sent}")


async def update_schedule_statuses():
    """
    Background job to update schedule statuses based on due dates.

    Runs daily to:
    - Mark 'upcoming' schedules as 'due' when due date arrives
    - Mark 'due' schedules as 'overdue' when past due date
    """
    logger.info("Updating service schedule statuses...")
    today = date.today()

    try:
        async with async_session_maker() as db:
            # Get all active schedules
            result = await db.execute(
                select(CustomerServiceSchedule).where(CustomerServiceSchedule.status.in_(["upcoming", "due"]))
            )
            schedules = result.scalars().all()

            updated = 0
            for schedule in schedules:
                if not schedule.next_due_date:
                    continue

                days_until = (schedule.next_due_date - today).days

                new_status = None
                if days_until < 0 and schedule.status != "overdue":
                    new_status = "overdue"
                elif days_until <= 7 and schedule.status == "upcoming":
                    new_status = "due"

                if new_status:
                    schedule.status = new_status
                    updated += 1

            await db.commit()
            logger.info(f"Updated {updated} schedule statuses")

    except Exception as e:
        logger.error(f"Error updating schedule statuses: {e}", exc_info=True)


def start_reminder_scheduler():
    """Start the reminder scheduler with all configured jobs."""
    global scheduler

    scheduler = get_scheduler()

    # Add job to send reminders daily at 8 AM
    scheduler.add_job(
        check_and_send_reminders,
        CronTrigger(hour=8, minute=0),
        id="service_reminders",
        name="Send service reminders",
        replace_existing=True,
    )

    # Add job to update statuses daily at 6 AM (before reminders)
    scheduler.add_job(
        update_schedule_statuses,
        CronTrigger(hour=6, minute=0),
        id="update_schedule_statuses",
        name="Update schedule statuses",
        replace_existing=True,
    )

    # Start the scheduler
    if not scheduler.running:
        scheduler.start()
        logger.info("Service reminder scheduler started")
        logger.info("Jobs scheduled:")
        for job in scheduler.get_jobs():
            logger.info(f"  - {job.name}: {job.trigger}")


def stop_reminder_scheduler():
    """Stop the reminder scheduler."""
    global scheduler

    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Service reminder scheduler stopped")


async def run_reminders_now():
    """Manually trigger reminder check (for testing/admin use)."""
    logger.info("Manual reminder check triggered")
    await check_and_send_reminders()
    return {"status": "completed", "message": "Reminder check completed"}
