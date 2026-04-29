"""
Microsoft 365 Email Service

Monitor a mailbox, fetch unread emails, match to customers.
Uses application-level permissions.
"""

import logging

from app.services.ms365_base import MS365BaseService
from app.config import settings

logger = logging.getLogger(__name__)


class MS365EmailService(MS365BaseService):
    """Service for monitoring and processing inbound emails."""

    @classmethod
    def is_configured(cls) -> bool:
        return bool(super().is_configured() and settings.MS365_MONITORED_MAILBOX)

    @classmethod
    async def get_unread_emails(cls, top: int = 20) -> list[dict]:
        """Fetch unread emails from the monitored mailbox."""
        if not cls.is_configured():
            return []

        try:
            result = await cls.graph_get(
                f"/users/{settings.MS365_MONITORED_MAILBOX}/messages"
                f"?$filter=isRead eq false"
                f"&$select=id,subject,bodyPreview,from,receivedDateTime"
                f"&$orderby=receivedDateTime desc"
                f"&$top={top}",
            )
            return result.get("value", [])

        except Exception as e:
            logger.error("Failed to fetch unread emails: %s", e)
            return []

    @classmethod
    async def get_message_by_id(cls, message_id: str) -> dict | None:
        """Fetch a single email by Graph message ID, including the full body.

        Used by the AI Interaction Analyzer worker to pull the full email
        body for triage (the inbound_emails table only stores body_preview).
        Returns the raw Graph message dict (keys: id, subject, body, from,
        toRecipients, receivedDateTime), or None on failure.
        """
        if not cls.is_configured():
            return None

        try:
            return await cls.graph_get(
                f"/users/{settings.MS365_MONITORED_MAILBOX}/messages/{message_id}"
                f"?$select=id,subject,body,bodyPreview,from,toRecipients,receivedDateTime",
            )
        except Exception as e:  # noqa: BLE001
            logger.error("Failed to fetch email %s: %s", message_id, e)
            return None

    @classmethod
    async def mark_as_read(cls, message_id: str) -> bool:
        """Mark an email as read in the monitored mailbox."""
        if not cls.is_configured():
            return False

        try:
            await cls.graph_patch(
                f"/users/{settings.MS365_MONITORED_MAILBOX}/messages/{message_id}",
                {"isRead": True},
            )
            return True

        except Exception as e:
            logger.error("Failed to mark email as read: %s", e)
            return False

    @classmethod
    def parse_sender(cls, email_data: dict) -> tuple[str, str]:
        """Extract sender email and name from Graph API email object."""
        from_data = email_data.get("from", {}).get("emailAddress", {})
        return (
            from_data.get("address", "").lower(),
            from_data.get("name", ""),
        )
