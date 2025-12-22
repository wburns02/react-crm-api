from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from app.config import settings
import logging

logger = logging.getLogger(__name__)


class TwilioService:
    """Service for interacting with Twilio API."""

    def __init__(self):
        self.account_sid = settings.TWILIO_ACCOUNT_SID
        self.auth_token = settings.TWILIO_AUTH_TOKEN
        self.phone_number = settings.TWILIO_PHONE_NUMBER

        if self.account_sid and self.auth_token:
            self.client = Client(self.account_sid, self.auth_token)
        else:
            self.client = None
            logger.warning("Twilio credentials not configured")

    async def send_sms(self, to: str, body: str) -> dict:
        """Send an SMS message via Twilio."""
        if not self.client:
            raise Exception("Twilio client not configured")

        try:
            message = self.client.messages.create(
                to=to,
                from_=self.phone_number,
                body=body,
            )
            logger.info(f"SMS sent: {message.sid} to {to}")
            return message
        except TwilioRestException as e:
            logger.error(f"Twilio error: {e.msg}")
            raise Exception(f"Twilio error: {e.msg}")

    async def get_message_status(self, message_sid: str) -> dict:
        """Get the status of a message by SID."""
        if not self.client:
            raise Exception("Twilio client not configured")

        try:
            message = self.client.messages(message_sid).fetch()
            return {
                "sid": message.sid,
                "status": message.status,
                "error_code": message.error_code,
                "error_message": message.error_message,
            }
        except TwilioRestException as e:
            logger.error(f"Twilio error fetching message: {e.msg}")
            raise Exception(f"Twilio error: {e.msg}")


class MockTwilioService(TwilioService):
    """Mock Twilio service for testing."""

    def __init__(self):
        self.phone_number = "+15555555555"
        self.client = None
        self._sent_messages = []

    async def send_sms(self, to: str, body: str) -> dict:
        """Mock sending an SMS."""
        mock_response = type("MockMessage", (), {
            "sid": f"SM{''.join(['0'] * 32)}",
            "status": "queued",
            "to": to,
            "body": body,
        })()

        self._sent_messages.append({
            "to": to,
            "body": body,
            "sid": mock_response.sid,
        })

        logger.info(f"Mock SMS sent to {to}")
        return mock_response

    async def get_message_status(self, message_sid: str) -> dict:
        """Mock getting message status."""
        return {
            "sid": message_sid,
            "status": "delivered",
            "error_code": None,
            "error_message": None,
        }
