"""
Microsoft Teams Webhook Service

Sends formatted MessageCard notifications to a Teams channel via Incoming Webhook.
"""

import httpx
import logging

from app.config import settings

logger = logging.getLogger(__name__)


class TeamsWebhookService:
    """Send notifications to Microsoft Teams via Incoming Webhook connector."""

    @classmethod
    def is_configured(cls) -> bool:
        return bool(settings.MS_TEAMS_WEBHOOK_URL)

    @classmethod
    async def send_notification(
        cls,
        title: str,
        body: str,
        color: str = "0078d4",
        facts: list[dict] | None = None,
    ) -> bool:
        """Send a MessageCard to Teams.

        Args:
            title: Card title
            body: Card body text
            color: Theme color hex (no #)
            facts: List of {"name": str, "value": str} pairs
        """
        if not cls.is_configured():
            logger.debug("Teams webhook not configured, skipping")
            return False

        card = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": color,
            "summary": title,
            "sections": [
                {
                    "activityTitle": title,
                    "text": body,
                }
            ],
        }

        if facts:
            card["sections"][0]["facts"] = facts

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    settings.MS_TEAMS_WEBHOOK_URL,
                    json=card,
                    timeout=10,
                )
                resp.raise_for_status()
                logger.info("Teams notification sent: %s", title)
                return True
        except Exception as e:
            logger.error("Teams webhook failed: %s", e)
            return False

    @classmethod
    async def notify_job_completed(
        cls,
        job_type: str,
        customer_name: str,
        technician_name: str,
        work_order_id: str,
    ) -> bool:
        return await cls.send_notification(
            title=f"Job Completed: {job_type.replace('_', ' ').title()}",
            body=f"{technician_name} completed a job for {customer_name}",
            color="00c853",
            facts=[
                {"name": "Customer", "value": customer_name},
                {"name": "Technician", "value": technician_name},
                {"name": "Job Type", "value": job_type},
            ],
        )

    @classmethod
    async def notify_new_payment(
        cls,
        amount: float,
        customer_name: str,
        payment_method: str = "unknown",
    ) -> bool:
        return await cls.send_notification(
            title=f"Payment Received: ${amount:.2f}",
            body=f"Payment from {customer_name}",
            color="2e7d32",
            facts=[
                {"name": "Amount", "value": f"${amount:.2f}"},
                {"name": "Customer", "value": customer_name},
                {"name": "Method", "value": payment_method},
            ],
        )

    @classmethod
    async def notify_new_quote(
        cls,
        customer_name: str,
        total: float,
    ) -> bool:
        return await cls.send_notification(
            title="New Quote Created",
            body=f"Quote for {customer_name} — ${total:.2f}",
            color="ff9800",
            facts=[
                {"name": "Customer", "value": customer_name},
                {"name": "Total", "value": f"${total:.2f}"},
            ],
        )

    @classmethod
    async def notify_new_booking(
        cls,
        customer_name: str,
        service_type: str,
        scheduled_date: str,
    ) -> bool:
        return await cls.send_notification(
            title="New Booking",
            body=f"{customer_name} booked a {service_type}",
            color="0078d4",
            facts=[
                {"name": "Customer", "value": customer_name},
                {"name": "Service", "value": service_type},
                {"name": "Date", "value": scheduled_date},
            ],
        )
