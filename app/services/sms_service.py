"""SMS Service - Unified facade for sending SMS via RingCentral (TCR-approved).

All SMS sending in the CRM routes through this module. RingCentral is the
TCR-registered A2P provider; Twilio is retained for voice/calling only.

Usage:
    from app.services.sms_service import sms_service
    await sms_service.send_sms("+15125551234", "Hello from MAC Septic!")

    # Or use the module-level convenience function:
    from app.services.sms_service import send_sms
    await send_sms("+15125551234", "Hello from MAC Septic!")
"""

import logging
from typing import Any

from app.services.ringcentral_service import ringcentral_service, SMSResponse

logger = logging.getLogger(__name__)


class SMSService:
    """Thin facade that delegates SMS sending to RingCentral."""

    def __init__(self):
        self._rc = ringcentral_service

    @property
    def phone_number(self) -> str | None:
        """The TCR-approved from-number used for outbound SMS."""
        return self._rc.phone_number

    @property
    def is_configured(self) -> bool:
        """Whether the SMS backend (RingCentral) is ready."""
        return self._rc.is_configured and bool(self._rc.phone_number)

    async def send_sms(self, to: str, body: str) -> Any:
        """Send an SMS message.

        Args:
            to: Destination phone number (any format — will be normalized)
            body: Message body text

        Returns:
            SMSResponse (has .sid, .status, .to, .body, .error attributes)

        Raises:
            Exception: If RingCentral is not configured or send fails hard
        """
        if not self.is_configured:
            raise Exception(
                "SMS service not configured — set RINGCENTRAL_CLIENT_ID, "
                "RINGCENTRAL_CLIENT_SECRET, RINGCENTRAL_JWT_TOKEN, and "
                "RINGCENTRAL_SMS_FROM_NUMBER"
            )
        return await self._rc.send_sms(to, body)


class MockSMSService(SMSService):
    """Mock SMS service for testing — no network calls."""

    def __init__(self):
        self._sent_messages: list[dict] = []

    @property
    def phone_number(self) -> str:
        return "+15555555555"

    @property
    def is_configured(self) -> bool:
        return True

    async def send_sms(self, to: str, body: str) -> SMSResponse:
        msg = SMSResponse(
            sid=f"MOCK-{'0' * 20}",
            status="Queued",
            to=to,
            body=body,
            from_number=self.phone_number,
        )
        self._sent_messages.append({"to": to, "body": body, "sid": msg.sid})
        logger.info(f"Mock SMS sent to {to}")
        return msg


# Singleton
sms_service = SMSService()


async def send_sms(to: str, body: str) -> Any:
    """Module-level convenience function for sending SMS."""
    return await sms_service.send_sms(to, body)
