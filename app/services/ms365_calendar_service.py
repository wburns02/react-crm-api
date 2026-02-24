"""
Microsoft 365 Calendar Service

Creates/updates/deletes Outlook calendar events for work orders.
Uses application-level permissions (no user delegation needed).
"""

import logging
from datetime import datetime, timedelta

from app.services.ms365_base import MS365BaseService
from app.config import settings

logger = logging.getLogger(__name__)


class MS365CalendarService(MS365BaseService):
    """Service for Outlook calendar sync with work orders."""

    @classmethod
    async def create_event(
        cls,
        technician_microsoft_email: str,
        subject: str,
        location: str,
        body: str,
        start_dt: datetime,
        duration_hours: float = 2.0,
    ) -> str | None:
        """Create an Outlook calendar event for a technician. Returns event ID."""
        if not cls.is_configured() or not technician_microsoft_email:
            return None

        try:
            end_dt = start_dt + timedelta(hours=duration_hours)
            event_data = {
                "subject": subject,
                "body": {"contentType": "HTML", "content": body},
                "start": {
                    "dateTime": start_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                    "timeZone": "America/Chicago",
                },
                "end": {
                    "dateTime": end_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                    "timeZone": "America/Chicago",
                },
                "location": {"displayName": location},
                "isReminderOn": True,
                "reminderMinutesBeforeStart": 30,
            }

            result = await cls.graph_post(
                f"/users/{technician_microsoft_email}/events",
                event_data,
            )
            event_id = result.get("id")
            logger.info("Created Outlook event %s for %s", event_id, technician_microsoft_email)
            return event_id

        except Exception as e:
            logger.error("Failed to create Outlook event: %s", e)
            return None

    @classmethod
    async def update_event(
        cls,
        technician_microsoft_email: str,
        event_id: str,
        subject: str | None = None,
        location: str | None = None,
        body: str | None = None,
        start_dt: datetime | None = None,
        duration_hours: float | None = None,
    ) -> bool:
        """Update an existing Outlook calendar event."""
        if not cls.is_configured() or not technician_microsoft_email or not event_id:
            return False

        try:
            update_data: dict = {}
            if subject:
                update_data["subject"] = subject
            if location:
                update_data["location"] = {"displayName": location}
            if body:
                update_data["body"] = {"contentType": "HTML", "content": body}
            if start_dt:
                update_data["start"] = {
                    "dateTime": start_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                    "timeZone": "America/Chicago",
                }
                end_dt = start_dt + timedelta(hours=duration_hours or 2.0)
                update_data["end"] = {
                    "dateTime": end_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                    "timeZone": "America/Chicago",
                }

            if update_data:
                await cls.graph_patch(
                    f"/users/{technician_microsoft_email}/events/{event_id}",
                    update_data,
                )
                logger.info("Updated Outlook event %s", event_id)
            return True

        except Exception as e:
            logger.error("Failed to update Outlook event: %s", e)
            return False

    @classmethod
    async def delete_event(cls, technician_microsoft_email: str, event_id: str) -> bool:
        """Delete an Outlook calendar event."""
        if not cls.is_configured() or not technician_microsoft_email or not event_id:
            return False

        try:
            await cls.graph_delete(
                f"/users/{technician_microsoft_email}/events/{event_id}",
            )
            logger.info("Deleted Outlook event %s", event_id)
            return True

        except Exception as e:
            logger.error("Failed to delete Outlook event: %s", e)
            return False

    @classmethod
    async def list_events(
        cls,
        technician_microsoft_email: str,
        start_date: str,
        end_date: str,
    ) -> list[dict]:
        """List calendar events for a technician in a date range."""
        if not cls.is_configured() or not technician_microsoft_email:
            return []

        try:
            result = await cls.graph_get(
                f"/users/{technician_microsoft_email}/calendarView"
                f"?startDateTime={start_date}T00:00:00Z&endDateTime={end_date}T23:59:59Z"
                f"&$select=id,subject,start,end,location&$top=50",
            )
            return result.get("value", [])

        except Exception as e:
            logger.error("Failed to list Outlook events: %s", e)
            return []

    @classmethod
    def build_event_subject(cls, job_type: str, customer_name: str) -> str:
        return f"{job_type.replace('_', ' ').title()} - {customer_name}"

    @classmethod
    def build_event_body(cls, work_order_id: str, notes: str | None = None) -> str:
        frontend_url = settings.FRONTEND_URL.rstrip("/")
        body = f'<p><a href="{frontend_url}/work-orders/{work_order_id}">View in CRM</a></p>'
        if notes:
            body += f"<p><strong>Notes:</strong> {notes}</p>"
        return body

    @classmethod
    def build_event_location(cls, address: str | None, city: str | None, state: str | None) -> str:
        parts = [p for p in [address, city, state] if p]
        return ", ".join(parts) or "No address"
