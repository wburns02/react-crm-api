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

    # Area-code → market lookup. Drives smart caller-ID selection.
    # Map covers MAC Septic's three operating regions.
    _AREA_CODE_TO_MARKET: Dict[str, str] = {
        # Nashville metro (615 = original, 629 = 2014 overlay)
        "615": "TN_NASHVILLE", "629": "TN_NASHVILLE",
        # South-of-Nashville: Maury, Marshall, Lewis, Hickman, Lawrence, Giles, Wayne, Perry counties
        "931": "TN_COLUMBIA",
        # Austin metro
        "512": "TX_AUSTIN", "737": "TX_AUSTIN",
        "254": "TX_AUSTIN",  # Killeen/Temple/Waco — closest to Austin in TX list
        "830": "TX_AUSTIN",  # Hill Country / New Braunfels / Boerne
        # Columbia SC + the Carolinas footprint
        "803": "SC_COLUMBIA", "839": "SC_COLUMBIA",  # 839 is 803's overlay
        "843": "SC_COLUMBIA", "854": "SC_COLUMBIA",  # Lowcountry / Charleston
        "864": "SC_COLUMBIA",  # Upstate / Greenville
    }

    def _market_to_number(self, market: str) -> Optional[str]:
        """Return the configured Twilio number for a given market, or None."""
        return {
            "TN_NASHVILLE": settings.TWILIO_PHONE_NUMBER_TN_NASHVILLE,
            "TN_COLUMBIA": settings.TWILIO_PHONE_NUMBER_TN_COLUMBIA,
            "TX_AUSTIN": settings.TWILIO_PHONE_NUMBER_TX_AUSTIN,
            "SC_COLUMBIA": settings.TWILIO_PHONE_NUMBER_SC_COLUMBIA,
        }.get(market)

    def pick_caller_id(
        self,
        to_number: str,
        market_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Choose the best caller-ID number for an outbound call.

        Strategy:
          1. If market_override is a specific market ("TN_NASHVILLE", "TX_AUSTIN", etc.) and
             that market has a number configured, use it.
          2. If market_override is a region ("TN", "TX", "SC"), pick the best sub-market
             for that region based on the destination area code.
          3. Otherwise (auto / None / "auto"): match destination area code to a market.
          4. Fall back to TWILIO_PHONE_NUMBER if nothing matches.

        Returns dict: {from_number, market, reason} so the caller can log/show what was picked.
        """
        to_formatted = self._format_phone(to_number)
        # E.164 looks like +1NPANXXXXXX — area code is digits 2..5
        digits = "".join(c for c in to_formatted if c.isdigit())
        area_code = digits[1:4] if len(digits) >= 11 and digits.startswith("1") else digits[:3]

        override = (market_override or "").strip().upper() or None

        # Direct sub-market override
        if override and override in {"TN_NASHVILLE", "TN_COLUMBIA", "TX_AUSTIN", "SC_COLUMBIA"}:
            num = self._market_to_number(override)
            if num:
                return {"from_number": num, "market": override, "reason": "explicit-override"}

        # Region-only override — narrow by area code within the region
        if override in {"TN", "TX", "SC"}:
            ac_market = self._AREA_CODE_TO_MARKET.get(area_code)
            if ac_market and ac_market.startswith(override):
                num = self._market_to_number(ac_market)
                if num:
                    return {"from_number": num, "market": ac_market, "reason": "region-area-code"}
            # Region picked but area code doesn't match the region → use any number in that region
            region_markets = {
                "TN": ("TN_NASHVILLE", "TN_COLUMBIA"),
                "TX": ("TX_AUSTIN",),
                "SC": ("SC_COLUMBIA",),
            }.get(override, ())
            for m in region_markets:
                num = self._market_to_number(m)
                if num:
                    return {"from_number": num, "market": m, "reason": "region-fallback"}

        # Auto-route by destination area code
        ac_market = self._AREA_CODE_TO_MARKET.get(area_code)
        if ac_market:
            num = self._market_to_number(ac_market)
            if num:
                return {"from_number": num, "market": ac_market, "reason": "auto-area-code"}

        # Final fallback: global Twilio number
        if self.phone_number:
            return {"from_number": self.phone_number, "market": "DEFAULT", "reason": "fallback-default"}

        return {"from_number": None, "market": None, "reason": "no-number-configured"}

    def list_caller_ids(self) -> Dict[str, Any]:
        """List configured caller IDs by market — for the dialer UI's picker."""
        markets = []
        for key, label, area_codes in [
            ("TN_NASHVILLE", "Nashville TN (615/629)", "615, 629"),
            ("TN_COLUMBIA", "Columbia TN (931)", "931"),
            ("TX_AUSTIN", "Austin TX (512/737)", "512, 737, 254, 830"),
            ("SC_COLUMBIA", "Columbia SC (803/843/864)", "803, 843, 864"),
        ]:
            num = self._market_to_number(key)
            if num:
                markets.append({"market": key, "label": label, "from_number": num, "area_codes": area_codes})
        return {
            "default": self.phone_number,
            "markets": markets,
        }

    async def make_call(
        self,
        to_number: str,
        from_number: Optional[str] = None,
        record: bool = True,
        market_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Initiate an outbound call via Twilio.

        Unlike RingCentral RingOut, Twilio makes a direct call to the destination.
        Use this when you want to call a customer directly without ringing your phone first.

        Args:
            to_number: Phone number to call
            from_number: Optional caller ID — if provided, used as-is and overrides smart routing.
            record: Whether to record the call
            market_override: Optional "auto" | "TN" | "TX" | "SC" | specific market key
                             ("TN_NASHVILLE", "TN_COLUMBIA", "TX_AUSTIN", "SC_COLUMBIA"). When
                             from_number is None, this drives the smart caller-ID picker.

        Returns:
            Call information including SID, picked from_number, and the picker's reasoning.
        """
        if not self.client:
            return {"error": "Twilio not configured", "configured": False}

        try:
            to_formatted = self._format_phone(to_number)
            picker_reason = "explicit-from-number"
            picked_market = None
            if from_number:
                from_formatted = from_number
            else:
                pick = self.pick_caller_id(to_number=to_number, market_override=market_override)
                from_formatted = pick.get("from_number")
                picked_market = pick.get("market")
                picker_reason = pick.get("reason")
                if not from_formatted:
                    return {"error": "No caller ID configured for this destination", "configured": False}

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

            logger.info(
                f"Twilio call initiated: {call.sid} from={from_formatted} to={to_formatted} "
                f"market={picked_market} reason={picker_reason}"
            )

            return {
                "success": True,
                "call_sid": call.sid,
                "status": call.status,
                "from_number": from_formatted,
                "to_number": to_formatted,
                "direction": "outbound",
                "market": picked_market,
                "picker_reason": picker_reason,
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
                        "from_number": getattr(call, "from_formatted", "") or getattr(call, "from_", ""),
                        "to_number": call.to or "",
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
            to_formatted = self._format_phone(to)
            message = self.client.messages.create(
                to=to_formatted,
                from_=self.phone_number,
                body=body,
            )
            logger.info(f"SMS sent: {message.sid} to {to_formatted}")
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
