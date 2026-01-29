"""Twilio Service - Voice calling and SMS integration.

Features:
- Outbound calling via Twilio Programmable Voice
- SMS sending/receiving
- Call recordings
- Status callbacks
"""

from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from app.config import settings
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class TwilioService:
    """Service for interacting with Twilio API (voice and SMS)."""

    def __init__(self):
        self.account_sid = settings.TWILIO_ACCOUNT_SID
        self.auth_token = settings.TWILIO_AUTH_TOKEN
        self.phone_number = settings.TWILIO_PHONE_NUMBER

        if self.account_sid and self.auth_token:
            self.client = Client(self.account_sid, self.auth_token)
        else:
            self.client = None
            logger.warning("Twilio credentials not configured")

    @property
    def is_configured(self) -> bool:
        """Check if Twilio is configured."""
        return self.client is not None and bool(self.phone_number)

    def get_status(self) -> Dict[str, Any]:
        """Get Twilio connection status."""
        if not self.client:
            return {
                "connected": False,
                "configured": False,
                "message": "Twilio credentials not configured",
            }

        try:
            # Test connection by fetching account info
            account = self.client.api.accounts(self.account_sid).fetch()
            return {
                "connected": True,
                "configured": True,
                "account_name": account.friendly_name,
                "phone_number": self.phone_number,
                "message": "Connected to Twilio",
            }
        except TwilioRestException as e:
            logger.error(f"Twilio connection test failed: {e}")
            return {
                "connected": False,
                "configured": True,
                "message": f"Connection failed: {e.msg}",
            }

    async def make_call(
        self,
        to_number: str,
        from_number: Optional[str] = None,
        record: bool = True,
    ) -> Dict[str, Any]:
        """Initiate an outbound call via Twilio.

        Unlike RingCentral RingOut, Twilio makes a direct call to the destination.
        Use this when you want to call a customer directly without ringing your phone first.

        Args:
            to_number: Phone number to call
            from_number: Optional caller ID (defaults to Twilio number)
            record: Whether to record the call

        Returns:
            Call information including SID
        """
        if not self.client:
            return {"error": "Twilio not configured", "configured": False}

        try:
            to_formatted = self._format_phone(to_number)
            from_formatted = from_number or self.phone_number

            # Simple TwiML to connect the call
            twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Connecting your call from MAC Septic CRM.</Say>
    <Dial callerId="{from_formatted}" record="{"record-from-answer" if record else "do-not-record"}">
        <Number>{to_formatted}</Number>
    </Dial>
</Response>"""

            call = self.client.calls.create(
                to=to_formatted,
                from_=from_formatted,
                twiml=twiml,
            )

            logger.info(f"Twilio call initiated: {call.sid}")

            return {
                "success": True,
                "call_sid": call.sid,
                "status": call.status,
                "from_number": call.from_,
                "to_number": call.to,
                "direction": "outbound",
            }

        except TwilioRestException as e:
            logger.error(f"Twilio call failed: {e.msg}")
            return {"error": e.msg}
        except Exception as e:
            logger.error(f"Twilio call failed: {e}")
            return {"error": str(e)}

    async def get_call_logs(
        self,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Get recent call logs from Twilio."""
        if not self.client:
            return {"error": "Twilio not configured", "items": []}

        try:
            calls = self.client.calls.list(limit=limit)

            return {
                "items": [
                    {
                        "id": call.sid,
                        "from_number": call.from_,
                        "to_number": call.to,
                        "direction": call.direction,
                        "status": call.status,
                        "start_time": call.start_time.isoformat() if call.start_time else None,
                        "duration_seconds": int(call.duration) if call.duration else 0,
                    }
                    for call in calls
                ],
                "total": len(calls),
            }

        except TwilioRestException as e:
            logger.error(f"Failed to get Twilio call logs: {e.msg}")
            return {"error": e.msg, "items": []}

    async def get_recordings(
        self,
        call_sid: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Get call recordings from Twilio."""
        if not self.client:
            return {"error": "Twilio not configured", "items": []}

        try:
            if call_sid:
                recordings = self.client.recordings.list(call_sid=call_sid, limit=limit)
            else:
                recordings = self.client.recordings.list(limit=limit)

            return {
                "items": [
                    {
                        "id": rec.sid,
                        "call_sid": rec.call_sid,
                        "duration_seconds": int(rec.duration) if rec.duration else 0,
                        "url": f"https://api.twilio.com{rec.uri.replace('.json', '.mp3')}",
                        "created_at": rec.date_created.isoformat() if rec.date_created else None,
                    }
                    for rec in recordings
                ],
                "total": len(recordings),
            }

        except TwilioRestException as e:
            logger.error(f"Failed to get Twilio recordings: {e.msg}")
            return {"error": e.msg, "items": []}

    def _format_phone(self, phone: str) -> str:
        """Format phone number to E.164 format."""
        digits = "".join(c for c in phone if c.isdigit())

        if len(digits) == 10:
            return f"+1{digits}"
        elif len(digits) == 11 and digits.startswith("1"):
            return f"+{digits}"
        elif phone.startswith("+"):
            return phone
        else:
            return f"+{digits}"

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
        mock_response = type(
            "MockMessage",
            (),
            {
                "sid": f"SM{''.join(['0'] * 32)}",
                "status": "queued",
                "to": to,
                "body": body,
            },
        )()

        self._sent_messages.append(
            {
                "to": to,
                "body": body,
                "sid": mock_response.sid,
            }
        )

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
