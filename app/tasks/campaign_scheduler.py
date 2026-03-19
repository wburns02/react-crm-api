"""Scheduled email campaign processor.

Checks for campaigns with status='draft' and scheduled_at <= now(),
then triggers sending via the same flow as manual sends.

Runs every 5 minutes via APScheduler.
"""

import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.database import async_session_maker
from app.models.marketing import MarketingCampaign, EmailTemplate
from app.models.customer import Customer
from app.services.email_service import EmailService
from app.services.sendgrid_service import sendgrid_service
from sqlalchemy import select, and_

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def process_scheduled_campaigns():
    """Find and send campaigns that are due."""
    async with async_session_maker() as db:
        now = datetime.utcnow()
        result = await db.execute(
            select(MarketingCampaign).where(
                and_(
                    MarketingCampaign.status.in_(["draft", "scheduled"]),
                    MarketingCampaign.scheduled_at.isnot(None),
                    MarketingCampaign.scheduled_at <= now,
                )
            )
        )
        campaigns = result.scalars().all()

        if not campaigns:
            return

        logger.info("Found %d scheduled campaigns to send", len(campaigns))

        for campaign in campaigns:
            try:
                # Load template
                if not campaign.template_id:
                    logger.warning("Campaign %s has no template, skipping", campaign.id)
                    campaign.status = "failed"
                    continue

                t_result = await db.execute(
                    select(EmailTemplate).where(EmailTemplate.id == campaign.template_id)
                )
                template = t_result.scalar_one_or_none()
                if not template:
                    logger.warning("Template %s not found for campaign %s", campaign.template_id, campaign.id)
                    campaign.status = "failed"
                    continue

                # Get segment customers
                from app.api.v2.email_marketing import _get_segment_query
                segment_id = campaign.segment or "all"
                conditions = await _get_segment_query(db, segment_id)
                q = select(Customer).where(*conditions)
                cust_result = await db.execute(q)
                customers = cust_result.scalars().all()

                if not customers:
                    logger.warning("No customers in segment '%s' for campaign %s", segment_id, campaign.id)
                    campaign.status = "sent"
                    campaign.total_sent = 0
                    continue

                # Send emails
                campaign.status = "sending"
                await db.commit()

                use_sendgrid = sendgrid_service.is_configured()
                email_service = None if use_sendgrid else EmailService()
                sent = 0
                failed = 0

                for cust in customers:
                    if not cust.email or "@" not in cust.email:
                        continue

                    context = {
                        "customer_name": f"{cust.first_name or ''} {cust.last_name or ''}".strip() or "Customer",
                        "first_name": cust.first_name or "Customer",
                        "company_name": "MAC Septic",
                    }

                    subject = template.subject or "Update from MAC Septic"
                    html_body = template.body_html or ""
                    text_body = template.body_text or ""
                    for key, value in context.items():
                        subject = subject.replace(f"{{{{{key}}}}}", str(value) if value else "")
                        html_body = html_body.replace(f"{{{{{key}}}}}", str(value) if value else "")
                        text_body = text_body.replace(f"{{{{{key}}}}}", str(value) if value else "")

                    try:
                        if use_sendgrid:
                            result = await sendgrid_service.send_email(
                                to_email=cust.email,
                                to_name=context["customer_name"],
                                subject=subject,
                                html_content=html_body,
                            )
                        else:
                            result = await email_service.send_email(
                                to_email=cust.email,
                                to_name=context["customer_name"],
                                subject=subject,
                                html_body=html_body,
                                text_body=text_body,
                            )

                        if result.get("success"):
                            sent += 1
                        else:
                            failed += 1
                    except Exception as e:
                        logger.error("Failed to send to %s: %s", cust.email, e)
                        failed += 1

                campaign.status = "sent"
                campaign.total_sent = sent
                campaign.total_delivered = sent
                campaign.total_bounced = failed
                campaign.sent_at = datetime.utcnow()
                await db.commit()

                logger.info(
                    "Campaign '%s' sent: %d delivered, %d failed",
                    campaign.name, sent, failed,
                )

            except Exception as e:
                logger.error("Error processing campaign %s: %s", campaign.id, e, exc_info=True)
                campaign.status = "failed"
                await db.commit()


def start_campaign_scheduler():
    """Start the campaign scheduler."""
    global _scheduler
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        process_scheduled_campaigns,
        "interval",
        minutes=5,
        id="campaign_scheduler",
    )
    _scheduler.start()
    logger.info("Campaign scheduler started (every 5 minutes)")


def stop_campaign_scheduler():
    """Stop the campaign scheduler."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Campaign scheduler stopped")
