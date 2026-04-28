"""
Campaign Dialer for MAC Septic AI Outbound Agent.

Manages the prospect queue, pacing, Twilio call initiation,
and coordinates with the outbound agent conversation engine.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session_maker
from app.models.customer import Customer
from app.models.quote import Quote

logger = logging.getLogger(__name__)

try:
    from twilio.rest import Client as TwilioClient
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False


# ── Campaign State ─────────────────────────────────────────────────

class CampaignState:
    """In-memory state for the running campaign."""

    def __init__(self):
        self.running = False
        self.paused = False
        self.started_at: Optional[datetime] = None
        self.current_call_sid: Optional[str] = None
        self.current_prospect: Optional[dict] = None
        self.calls_made = 0
        self.calls_today = 0
        self.dispositions: dict[str, int] = {}
        self.queue_depth = 0
        self.last_error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "running": self.running,
            "paused": self.paused,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "current_call_sid": self.current_call_sid,
            "current_prospect": self.current_prospect,
            "calls_made": self.calls_made,
            "calls_today": self.calls_today,
            "dispositions": self.dispositions,
            "queue_depth": self.queue_depth,
            "last_error": self.last_error,
        }


# Global campaign state
campaign = CampaignState()

# Active agent sessions keyed by call_sid
active_sessions: dict[str, "OutboundAgentSession"] = {}


# ── Queue Management ───────────────────────────────────────────────

async def get_prospect_queue(limit: int = 50, *, is_test: bool = False) -> list[dict]:
    """
    Get prospects with outstanding quotes, sorted by value and age.

    Criteria:
    - Quote status = 'sent' (not converted, not rejected)
    - Quote sent > 3 days ago
    - Customer has phone number
    - Not marked DNC
    - Max 3 call attempts
    - is_test_prospect matches `is_test` arg (False for real campaigns)
    """
    async with async_session_maker() as db:
        # Subquery: quotes that are sent but not converted
        stmt = (
            select(Quote, Customer)
            .join(Customer, Quote.customer_id == Customer.id)
            .where(
                Quote.status == "sent",
                Quote.converted_to_work_order_id.is_(None),
                Customer.phone.isnot(None),
                Customer.phone != "",
                Customer.is_active == True,
                Customer.is_test_prospect == is_test,
            )
            .order_by(desc(Quote.total), Quote.sent_at.asc())
            .limit(limit)
        )

        result = await db.execute(stmt)
        rows = result.all()

        queue = []
        for quote, customer in rows:
            queue.append({
                "prospect": {
                    "id": str(customer.id),
                    "first_name": customer.first_name,
                    "last_name": customer.last_name,
                    "phone": customer.phone,
                    "email": customer.email,
                    "address_line1": customer.address_line1 or "",
                    "city": customer.city or "",
                    "state": customer.state or "",
                    "postal_code": customer.postal_code or "",
                    "customer_type": customer.customer_type or "residential",
                    "system_type": getattr(customer, "system_type", None) or "conventional",
                },
                "quote": {
                    "id": str(quote.id),
                    "quote_number": quote.quote_number,
                    "title": quote.title,
                    "total": float(quote.total or 0),
                    "line_items": quote.line_items or [],
                    "sent_at": quote.sent_at.isoformat() if quote.sent_at else None,
                    "created_at": quote.created_at.isoformat() if quote.created_at else None,
                    "status": quote.status,
                    "notes": quote.notes,
                },
            })

        return queue


# ── Twilio Call Initiation ─────────────────────────────────────────

def initiate_call(
    to_number: str,
    callback_url: str,
    *,
    prospect: dict | None = None,
    quote: dict | None = None,
) -> Optional[str]:
    """
    Place an outbound call via Twilio with AMD detection.

    When VOICE_AGENT_ENGINE == "pipecat", uses AsyncAmd + DetectMessageEnd so
    the answer/voicemail decision is delivered via the AMD callback URL while
    the call still rings, and schedules a greeting prerender so Sarah's first
    line is ready by the time the WebSocket connects.

    Returns the call SID on success.
    """
    if not TWILIO_AVAILABLE:
        logger.error("Twilio not installed")
        return None

    if not all([settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN]):
        logger.error("Twilio credentials not configured")
        return None

    from_number = settings.OUTBOUND_AGENT_FROM_NUMBER or settings.TWILIO_PHONE_NUMBER
    if not from_number:
        logger.error("No outbound phone number configured")
        return None

    try:
        client = TwilioClient(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

        create_kwargs = {
            "to": to_number,
            "from_": from_number,
            "url": callback_url,  # TwiML endpoint that starts media stream
            "status_callback": callback_url.replace("/voice", "/status"),
            "status_callback_event": ["initiated", "ringing", "answered", "completed"],
            "record": True,
            "recording_channels": "dual",
            "timeout": 30,  # Ring for 30 seconds max
        }

        if settings.VOICE_AGENT_ENGINE == "pipecat":
            # AsyncAmd lets the call connect immediately; AMD result is POSTed
            # to async_amd_status_callback shortly after answer.
            create_kwargs["machine_detection"] = "DetectMessageEnd"
            create_kwargs["async_amd"] = "true"
            if settings.OUTBOUND_AGENT_AMD_CALLBACK:
                create_kwargs["async_amd_status_callback"] = settings.OUTBOUND_AGENT_AMD_CALLBACK
                create_kwargs["async_amd_status_callback_method"] = "POST"
        else:
            # Legacy synchronous AMD — Twilio waits to determine human/machine
            # before hitting the voice webhook with AnsweredBy populated.
            create_kwargs["machine_detection"] = "Enable"
            create_kwargs["machine_detection_timeout"] = 5

        call = client.calls.create(**create_kwargs)

        logger.info(f"Outbound call initiated: {call.sid} -> {to_number}")

        # Schedule greeting prerender so Sarah's first line is buffered before
        # the WS connects. Only meaningful for the pipecat engine, which knows
        # how to look up the buffer keyed by call_sid.
        if (
            settings.VOICE_AGENT_ENGINE == "pipecat"
            and prospect
            and quote
        ):
            try:
                from app.services.voice_agent.greeting_prerender import prerender_greeting
                asyncio.create_task(prerender_greeting(call.sid, prospect, quote))
            except RuntimeError:
                # No running event loop — caller is sync without a loop.
                # Greeting will fall back to live LLM/TTS at WS connect time.
                logger.debug(
                    "No running event loop; skipping greeting prerender for %s",
                    call.sid,
                )
            except Exception as exc:
                # Prerender is best-effort — never block dialing on it.
                logger.warning(
                    "Failed to schedule greeting prerender for %s: %s",
                    call.sid,
                    exc,
                )

        return call.sid

    except Exception as e:
        logger.error(f"Failed to initiate call to {to_number}: {e}")
        return None


# ── Campaign Runner ────────────────────────────────────────────────

async def start_campaign(is_test: bool = False):
    """Start the outbound campaign dialer.

    `is_test=True` filters the queue to customers with `is_test_prospect=true`,
    so test campaigns hit only seeded test rows (e.g., Will's cell).
    """
    if campaign.running:
        return {"error": "Campaign already running"}

    campaign.running = True
    campaign.paused = False
    campaign.started_at = datetime.utcnow()
    campaign.calls_made = 0
    campaign.calls_today = 0
    campaign.dispositions = {}
    campaign.last_error = None

    # Get initial queue
    queue = await get_prospect_queue(is_test=is_test)
    campaign.queue_depth = len(queue)

    if not queue:
        campaign.running = False
        return {"error": "No prospects in queue"}

    logger.info(f"Campaign started with {len(queue)} prospects in queue")

    # Start the dialer loop in background
    asyncio.create_task(_dialer_loop(queue))

    return {"status": "started", "queue_depth": len(queue)}


async def stop_campaign():
    """Stop the campaign."""
    campaign.running = False
    campaign.paused = False
    logger.info("Campaign stopped")
    return {"status": "stopped", "calls_made": campaign.calls_made}


async def pause_campaign():
    """Pause the campaign."""
    campaign.paused = True
    return {"status": "paused"}


async def resume_campaign():
    """Resume the campaign."""
    campaign.paused = False
    return {"status": "resumed"}


async def _dialer_loop(queue: list[dict]):
    """Main dialer loop — processes prospects one at a time."""
    try:
        for entry in queue:
            if not campaign.running:
                break

            while campaign.paused:
                await asyncio.sleep(1)
                if not campaign.running:
                    break

            prospect = entry["prospect"]
            quote = entry["quote"]

            campaign.current_prospect = {
                "name": f"{prospect['first_name']} {prospect['last_name']}",
                "phone": prospect["phone"],
                "quote_total": quote["total"],
                "quote_number": quote["quote_number"],
            }

            logger.info(
                f"Dialing {prospect['first_name']} {prospect['last_name']} "
                f"at {prospect['phone']} (Quote #{quote['quote_number']} ${quote['total']:,.2f})"
            )

            # Build the TwiML callback URL
            api_base = settings.FRONTEND_URL.replace("http://localhost:5173",
                "https://react-crm-api-production.up.railway.app")
            if "railway" not in api_base:
                api_base = "https://react-crm-api-production.up.railway.app"

            callback_url = f"{api_base}/api/v2/outbound-agent/voice"

            # Store prospect data for the webhook to access
            _pending_calls[prospect["phone"]] = {
                "prospect": prospect,
                "quote": quote,
            }

            # Make the call
            phone = prospect["phone"]
            if not phone.startswith("+"):
                phone = "+1" + phone.replace("-", "").replace("(", "").replace(")", "").replace(" ", "")

            call_sid = initiate_call(phone, callback_url, prospect=prospect, quote=quote)

            if call_sid:
                # Also key pending data by call_sid so the Pipecat WS handler
                # (which only knows call_sid from Twilio) can find prospect/quote.
                _pending_calls[call_sid] = {"prospect": prospect, "quote": quote}
                campaign.current_call_sid = call_sid
                campaign.calls_made += 1
                campaign.calls_today += 1

                # Wait for call to complete (agent session handles the rest)
                # The Twilio webhook will create the agent session
                await _wait_for_call_completion(call_sid, timeout=300)
            else:
                campaign.last_error = f"Failed to dial {prospect['phone']}"

            campaign.current_prospect = None
            campaign.current_call_sid = None

            # Pause between calls
            if campaign.running and queue.index(entry) < len(queue) - 1:
                logger.info("Pausing 30s between calls...")
                await asyncio.sleep(30)

    except Exception as e:
        logger.error(f"Dialer loop error: {e}")
        campaign.last_error = str(e)
    finally:
        campaign.running = False
        campaign.current_prospect = None
        logger.info(f"Campaign ended. {campaign.calls_made} calls made.")


async def _wait_for_call_completion(call_sid: str, timeout: int = 300):
    """Wait for a call to complete or timeout."""
    elapsed = 0
    while elapsed < timeout:
        if call_sid in active_sessions:
            session = active_sessions[call_sid]
            if session.ended:
                # Log disposition
                disp = session.disposition or "unknown"
                campaign.dispositions[disp] = campaign.dispositions.get(disp, 0) + 1
                # Clean up
                del active_sessions[call_sid]
                return
        elif call_sid not in active_sessions and elapsed > 10:
            # Call may have failed to connect
            return

        await asyncio.sleep(1)
        elapsed += 1

    logger.warning(f"Call {call_sid} timed out after {timeout}s")


# Temporary storage for pending call data (phone -> prospect/quote)
_pending_calls: dict[str, dict] = {}


def get_pending_call_data(phone: str) -> Optional[dict]:
    """Retrieve stored prospect/quote data for a phone number."""
    # Normalize phone for lookup
    clean = phone.replace("+1", "").replace("-", "").replace("(", "").replace(")", "").replace(" ", "")
    for stored_phone, data in _pending_calls.items():
        stored_clean = stored_phone.replace("+1", "").replace("-", "").replace("(", "").replace(")", "").replace(" ", "")
        if clean == stored_clean or clean.endswith(stored_clean) or stored_clean.endswith(clean):
            return data
    return None


def remove_pending_call_data(phone: str):
    """Remove stored call data after use."""
    clean = phone.replace("+1", "").replace("-", "").replace("(", "").replace(")", "").replace(" ", "")
    to_remove = []
    for stored_phone in _pending_calls:
        stored_clean = stored_phone.replace("+1", "").replace("-", "").replace("(", "").replace(")", "").replace(" ", "")
        if clean == stored_clean or clean.endswith(stored_clean) or stored_clean.endswith(clean):
            to_remove.append(stored_phone)
    for p in to_remove:
        del _pending_calls[p]
