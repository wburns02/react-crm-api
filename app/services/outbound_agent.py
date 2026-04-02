"""
AI Outbound Sales Agent for MAC Septic.

Autonomously calls prospects with outstanding quotes, follows up,
answers questions, and books appointments.

Architecture:
  Twilio call → Media Streams WebSocket → Deepgram STT
    → Claude conversation engine (with tools)
    → ElevenLabs TTS → Twilio audio playback
"""

import asyncio
import base64
import json
import logging
import struct
from datetime import datetime, timedelta, date
from typing import Optional, Any
from uuid import UUID

import httpx
from app.config import settings

logger = logging.getLogger(__name__)


# ── Claude conversation system prompt ──────────────────────────────

SYSTEM_PROMPT = """You are a friendly, professional sales follow-up agent for MAC Septic Services. Your name is Sarah. You're calling customers who received a quote for septic services but haven't responded yet.

PERSONALITY:
- Warm, conversational, Southern-friendly (Nashville/SC market)
- Not pushy — you're following up, not hard-selling
- Confident about MAC Septic's quality and pricing
- Brief and respectful of their time

ABOUT MAC SEPTIC:
- Family-owned, 28+ years in business
- Serves Nashville TN and Columbia SC areas
- Services: septic pumping ($595-$825), inspections, repairs, installations
- Licensed, insured, same-day emergency service available
- 3 pricing tiers: Maintenance Plan $595, Standard $625, Real Estate Inspection $825

CALL FLOW:
1. Greet them by name, introduce yourself, reference the quote
2. Ask if they have questions about the estimate
3. Based on their response, either:
   - Book an appointment (use check_availability and book_appointment tools)
   - Answer questions about pricing/service
   - Transfer to the office if they want to talk to someone
   - Schedule a callback if not a good time
   - Thank them and end gracefully if not interested

RULES:
- Keep responses SHORT — 1-2 sentences max. This is a phone call, not an email.
- Never say "I'm an AI" — you're Sarah from MAC Septic
- If they ask a question you can't answer, offer to transfer to the office
- If they sound annoyed or busy, offer to call back at a better time
- Always be polite when ending a call, even if they're not interested
- If you detect voicemail, leave a brief message and hang up

VOICEMAIL DETECTION:
If you hear a beep or "leave a message", use the leave_voicemail tool immediately.

CURRENT PROSPECT INFO:
{prospect_context}
"""


# ── Tool definitions for Claude ────────────────────────────────────

AGENT_TOOLS = [
    {
        "name": "check_availability",
        "description": "Check available appointment slots for the next 7 days in the prospect's service area.",
        "input_schema": {
            "type": "object",
            "properties": {
                "preferred_date": {
                    "type": "string",
                    "description": "Preferred date in YYYY-MM-DD format, or 'next_available'"
                }
            },
            "required": []
        }
    },
    {
        "name": "book_appointment",
        "description": "Book a service appointment for the prospect. Creates a work order in the CRM.",
        "input_schema": {
            "type": "object",
            "properties": {
                "scheduled_date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                "time_window": {"type": "string", "description": "morning, afternoon, or specific time like 10:00"},
                "service_type": {"type": "string", "description": "pumping, inspection, repair, etc."},
                "notes": {"type": "string", "description": "Any special instructions from the customer"}
            },
            "required": ["scheduled_date", "service_type"]
        }
    },
    {
        "name": "transfer_call",
        "description": "Transfer the call to MAC Septic office for human assistance.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Why the customer wants to talk to someone"}
            },
            "required": ["reason"]
        }
    },
    {
        "name": "create_callback",
        "description": "Schedule a callback at a specific time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "callback_time": {"type": "string", "description": "When to call back, e.g. 'tomorrow morning' or '2026-04-03 14:00'"},
                "notes": {"type": "string", "description": "Context for the callback"}
            },
            "required": ["callback_time"]
        }
    },
    {
        "name": "set_disposition",
        "description": "Set the call outcome/disposition. Call this before ending the conversation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "disposition": {
                    "type": "string",
                    "enum": ["appointment_set", "callback_requested", "transferred_to_sales",
                             "not_interested", "service_completed_elsewhere", "voicemail_left",
                             "no_answer", "wrong_number", "do_not_call"]
                },
                "notes": {"type": "string", "description": "Brief summary of the call"}
            },
            "required": ["disposition"]
        }
    },
    {
        "name": "leave_voicemail",
        "description": "Leave a voicemail message. Use when you detect voicemail/answering machine.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "end_call",
        "description": "End the phone call. Always set_disposition before calling this.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "send_followup_sms",
        "description": "Send a follow-up text message to the prospect after the call.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Text message content"}
            },
            "required": ["message"]
        }
    },
]


# ── Outbound Agent Session ─────────────────────────────────────────

class OutboundAgentSession:
    """Manages a single AI-driven outbound call."""

    def __init__(
        self,
        call_sid: str,
        prospect: dict,
        quote: dict,
        on_speak: Any = None,  # async callback(text) to play TTS
        on_end_call: Any = None,  # async callback() to hang up
        on_transfer: Any = None,  # async callback(number) to transfer
    ):
        self.call_sid = call_sid
        self.prospect = prospect
        self.quote = quote
        self.on_speak = on_speak
        self.on_end_call = on_end_call
        self.on_transfer = on_transfer

        self.conversation: list[dict] = []
        self.transcript: list[dict] = []  # Full transcript for logging
        self.disposition: Optional[str] = None
        self.disposition_notes: Optional[str] = None
        self.started_at = datetime.utcnow()
        self.ended = False
        self._greeting_sent = False
        self._processing = False

    def _build_context(self) -> str:
        """Build prospect context for the system prompt."""
        p = self.prospect
        q = self.quote

        # Calculate quote age
        sent_at = q.get("sent_at") or q.get("created_at", "")
        if sent_at:
            try:
                sent_date = datetime.fromisoformat(sent_at.replace("Z", "+00:00"))
                days_ago = (datetime.utcnow() - sent_date.replace(tzinfo=None)).days
                quote_age = f"{days_ago} days ago"
            except (ValueError, TypeError):
                quote_age = "recently"
        else:
            quote_age = "recently"

        # Service type from line items
        line_items = q.get("line_items", [])
        services = [item.get("service", "septic service") for item in line_items] if line_items else ["septic service"]
        service_desc = ", ".join(services[:2])

        return f"""
Customer: {p.get('first_name', '')} {p.get('last_name', '')}
Phone: {p.get('phone', '')}
Address: {p.get('address_line1', '')} {p.get('city', '')}, {p.get('state', '')}
Quote #{q.get('quote_number', 'N/A')} — sent {quote_age}
Service: {service_desc}
Quote Total: ${float(q.get('total', 0)):,.2f}
Property Type: {p.get('customer_type', 'residential')}
System Type: {p.get('system_type', 'conventional')}
Previous Service: {p.get('last_service_date', 'None on file')}
"""

    async def start_greeting(self):
        """Send the opening greeting."""
        if self._greeting_sent:
            return
        self._greeting_sent = True

        p = self.prospect
        q = self.quote
        first_name = p.get("first_name", "")

        # Service description
        line_items = q.get("line_items", [])
        if line_items:
            service = line_items[0].get("service", "septic service")
        else:
            service = "septic service"

        greeting = (
            f"Hi, {first_name}? This is Sarah calling from MAC Septic. "
            f"We sent you an estimate for {service} and I just wanted to follow up "
            f"to see if you had any questions about it."
        )

        if self.on_speak:
            await self.on_speak(greeting)

        self.transcript.append({"speaker": "agent", "text": greeting, "timestamp": datetime.utcnow().isoformat()})
        self.conversation.append({"role": "assistant", "content": greeting})

    async def handle_speech(self, text: str):
        """Process customer speech and generate a response."""
        if self.ended or self._processing or not text.strip():
            return

        self._processing = True
        try:
            logger.info(f"[Agent:{self.call_sid[:8]}] Customer: {text}")
            self.transcript.append({"speaker": "customer", "text": text, "timestamp": datetime.utcnow().isoformat()})
            self.conversation.append({"role": "user", "content": text})

            # Call Claude for response
            response = await self._call_claude()

            if response:
                logger.info(f"[Agent:{self.call_sid[:8]}] Agent: {response}")
                self.transcript.append({"speaker": "agent", "text": response, "timestamp": datetime.utcnow().isoformat()})
                self.conversation.append({"role": "assistant", "content": response})

                if self.on_speak:
                    await self.on_speak(response)
        finally:
            self._processing = False

    async def _call_claude(self) -> Optional[str]:
        """Call Claude API for conversation response."""
        if not settings.ANTHROPIC_API_KEY:
            logger.error("ANTHROPIC_API_KEY not set")
            return "I'm having a technical issue. Let me transfer you to the office."

        context = self._build_context()
        system = SYSTEM_PROMPT.replace("{prospect_context}", context)

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 300,
                    "system": system,
                    "messages": self.conversation,
                    "tools": AGENT_TOOLS,
                },
            )

            if resp.status_code != 200:
                logger.error(f"Claude API error: {resp.status_code} {resp.text[:200]}")
                return None

            data = resp.json()
            text_parts = []
            tool_calls = []

            for block in data.get("content", []):
                if block["type"] == "text":
                    text_parts.append(block["text"])
                elif block["type"] == "tool_use":
                    tool_calls.append(block)

            # Handle tool calls
            for tool in tool_calls:
                await self._handle_tool_call(tool["name"], tool.get("input", {}))

            return " ".join(text_parts) if text_parts else None

    async def _handle_tool_call(self, name: str, args: dict):
        """Execute a tool call from Claude."""
        logger.info(f"[Agent:{self.call_sid[:8]}] Tool: {name}({json.dumps(args)[:100]})")

        if name == "set_disposition":
            self.disposition = args.get("disposition", "unknown")
            self.disposition_notes = args.get("notes", "")

        elif name == "end_call":
            self.ended = True
            if self.on_end_call:
                await self.on_end_call()

        elif name == "transfer_call":
            if self.on_transfer:
                await self.on_transfer(settings.OUTBOUND_AGENT_TRANSFER_NUMBER)

        elif name == "leave_voicemail":
            # Generate voicemail message
            p = self.prospect
            q = self.quote
            line_items = q.get("line_items", [])
            service = line_items[0].get("service", "septic service") if line_items else "septic service"
            vm = (
                f"Hi {p.get('first_name', '')}, this is MAC Septic following up "
                f"on the estimate we sent for {service} at your property. "
                f"Give us a call back at 615-345-2544 when you get a chance. Thanks!"
            )
            if self.on_speak:
                await self.on_speak(vm)
            self.disposition = "voicemail_left"
            self.transcript.append({"speaker": "agent", "text": f"[Voicemail] {vm}", "timestamp": datetime.utcnow().isoformat()})
            # Wait for voicemail to play, then hang up
            await asyncio.sleep(8)
            self.ended = True
            if self.on_end_call:
                await self.on_end_call()

        elif name == "book_appointment":
            # This would create a work order via the CRM API
            logger.info(f"[Agent:{self.call_sid[:8]}] Booking: {args}")
            # Tool result will be added to conversation by Claude

        elif name == "check_availability":
            # Return some available slots
            today = date.today()
            slots = []
            for i in range(1, 8):
                d = today + timedelta(days=i)
                if d.weekday() < 5:  # Mon-Fri
                    slots.append(f"{d.strftime('%A %B %d')}: morning (8-12) or afternoon (12-5)")
            # Add to conversation as tool result
            self.conversation.append({
                "role": "user",
                "content": f"[Available slots: {'; '.join(slots[:5])}]"
            })

        elif name == "create_callback":
            logger.info(f"[Agent:{self.call_sid[:8]}] Callback: {args}")

        elif name == "send_followup_sms":
            logger.info(f"[Agent:{self.call_sid[:8]}] SMS: {args.get('message', '')[:50]}")

    def get_summary(self) -> dict:
        """Get call summary for logging."""
        return {
            "call_sid": self.call_sid,
            "prospect_id": str(self.prospect.get("id", "")),
            "prospect_name": f"{self.prospect.get('first_name', '')} {self.prospect.get('last_name', '')}",
            "quote_number": self.quote.get("quote_number", ""),
            "disposition": self.disposition,
            "disposition_notes": self.disposition_notes,
            "duration_seconds": (datetime.utcnow() - self.started_at).total_seconds(),
            "transcript": self.transcript,
        }
