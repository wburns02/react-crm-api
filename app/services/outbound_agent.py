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
import uuid
from datetime import datetime, timedelta, date
from typing import Optional, Any
from uuid import UUID

import httpx
from sqlalchemy import select, func

from app.config import settings
from app.database import async_session_maker
from app.models.work_order import WorkOrder
from app.models.ai_agent import AgentTask

# Sentinel agent_id for tasks created by the outbound calling agent
_OUTBOUND_AGENT_UUID = uuid.UUID("00000000-0000-0000-0000-000000000001")

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
        """Call Claude API for conversation response, handling tool_use/tool_result rounds."""
        if not settings.ANTHROPIC_API_KEY:
            logger.error("ANTHROPIC_API_KEY not set")
            return "I'm having a technical issue. Let me transfer you to the office."

        context = self._build_context()
        system = SYSTEM_PROMPT.replace("{prospect_context}", context)

        # Work on a local copy so we can append tool results without polluting
        # self.conversation mid-turn.  At the end we write the final assistant
        # message back to self.conversation (done in handle_speech).
        working_messages = list(self.conversation)

        for _round in range(3):  # max 3 tool-use rounds to prevent infinite loops
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
                        "messages": working_messages,
                        "tools": AGENT_TOOLS,
                    },
                )

            if resp.status_code != 200:
                logger.error(f"Claude API error: {resp.status_code} {resp.text[:200]}")
                return None

            data = resp.json()
            stop_reason = data.get("stop_reason", "end_turn")
            content_blocks = data.get("content", [])

            if stop_reason == "tool_use":
                # Add Claude's full response (including tool_use blocks) to working messages
                working_messages.append({"role": "assistant", "content": content_blocks})

                # Execute each tool and collect results
                tool_result_content = []
                for block in content_blocks:
                    if block.get("type") == "tool_use":
                        tool_id = block["id"]
                        tool_name = block["name"]
                        tool_args = block.get("input", {})
                        result = await self._handle_tool_call(tool_name, tool_id, tool_args)
                        tool_result_content.append({
                            "type": "tool_result",
                            "tool_use_id": tool_id,
                            "content": json.dumps(result),
                        })

                # Feed results back to Claude
                working_messages.append({"role": "user", "content": tool_result_content})
                # Loop for Claude's next response

            else:
                # end_turn or max_tokens — extract text
                text_parts = [
                    block["text"]
                    for block in content_blocks
                    if block.get("type") == "text"
                ]
                return " ".join(text_parts) if text_parts else None

        # Exhausted rounds without end_turn
        logger.warning(f"[Agent:{self.call_sid[:8]}] Tool-use loop exceeded 3 rounds")
        return None

    async def _handle_tool_call(self, name: str, tool_id: str, args: dict) -> dict:
        """Execute a tool call from Claude and return a result dict."""
        logger.info(f"[Agent:{self.call_sid[:8]}] Tool: {name}({json.dumps(args)[:100]})")

        if name == "set_disposition":
            self.disposition = args.get("disposition", "unknown")
            self.disposition_notes = args.get("notes", "")
            return {"ok": True, "disposition": self.disposition}

        elif name == "end_call":
            self.ended = True
            if self.on_end_call:
                await self.on_end_call()
            return {"ok": True}

        elif name == "transfer_call":
            if self.on_transfer:
                await self.on_transfer(settings.OUTBOUND_AGENT_TRANSFER_NUMBER)
            return {"ok": True, "transferred_to": settings.OUTBOUND_AGENT_TRANSFER_NUMBER}

        elif name == "leave_voicemail":
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
            self.transcript.append({
                "speaker": "agent",
                "text": f"[Voicemail] {vm}",
                "timestamp": datetime.utcnow().isoformat(),
            })
            # Wait for voicemail to play, then hang up
            await asyncio.sleep(8)
            self.ended = True
            if self.on_end_call:
                await self.on_end_call()
            return {"ok": True}

        elif name == "book_appointment":
            return await self._book_appointment(args)

        elif name == "check_availability":
            return await self._check_availability(args)

        elif name == "create_callback":
            return await self._create_callback(args)

        elif name == "send_followup_sms":
            return await self._send_followup_sms(args)

        else:
            logger.warning(f"[Agent:{self.call_sid[:8]}] Unknown tool: {name}")
            return {"ok": False, "error": f"Unknown tool: {name}"}

    # ── Real tool implementations ──────────────────────────────────

    async def _book_appointment(self, args: dict) -> dict:
        """Create a WorkOrder in the CRM for the booked appointment."""
        p = self.prospect
        scheduled_date_str = args.get("scheduled_date", "")
        time_window = args.get("time_window", "morning")
        service_type = args.get("service_type", "pumping")
        extra_notes = args.get("notes", "")

        # Parse and validate the date
        try:
            appt_date = date.fromisoformat(scheduled_date_str)
        except (ValueError, TypeError):
            return {"ok": False, "error": f"Invalid date format: {scheduled_date_str!r}. Use YYYY-MM-DD."}

        customer_id_raw = p.get("id")
        if not customer_id_raw:
            return {"ok": False, "error": "No customer_id on prospect — cannot create work order"}

        try:
            customer_uuid = uuid.UUID(str(customer_id_raw))
        except ValueError:
            return {"ok": False, "error": f"Invalid customer_id: {customer_id_raw}"}

        # Map service_type string to a valid job_type enum value
        job_type_map = {
            "pumping": "pumping",
            "inspection": "inspection",
            "real_estate_inspection": "real_estate_inspection",
            "repair": "repair",
            "installation": "installation",
            "emergency": "emergency",
            "maintenance": "maintenance",
            "grease_trap": "grease_trap",
            "camera_inspection": "camera_inspection",
        }
        job_type = job_type_map.get(service_type.lower().replace(" ", "_"), "pumping")

        # Compose notes
        booked_note = f"[AI Agent] Booked via outbound call on {datetime.utcnow().strftime('%Y-%m-%d')}"
        full_notes = f"{booked_note}. {extra_notes}".strip(". ")

        try:
            async with async_session_maker() as session:
                # Generate sequential WO number
                count_result = await session.execute(select(func.count()).select_from(WorkOrder))
                count = count_result.scalar() or 0
                wo_number = f"WO-{str(count + 1).zfill(6)}"

                wo = WorkOrder(
                    id=uuid.uuid4(),
                    work_order_number=wo_number,
                    customer_id=customer_uuid,
                    job_type=job_type,
                    status="scheduled",
                    priority="normal",
                    scheduled_date=appt_date,
                    notes=full_notes,
                    service_address_line1=p.get("address_line1", ""),
                    service_city=p.get("city", ""),
                    service_state=p.get("state", ""),
                    service_postal_code=p.get("postal_code", ""),
                    source="outbound_campaign",
                    created_by="ai_agent",
                )
                session.add(wo)
                await session.commit()

            self.disposition = "appointment_set"
            logger.info(
                f"[Agent:{self.call_sid[:8]}] Work order {wo_number} created for {appt_date} ({time_window})"
            )
            return {
                "ok": True,
                "work_order_number": wo_number,
                "scheduled_date": str(appt_date),
                "time_window": time_window,
                "service_type": job_type,
            }
        except Exception as exc:
            logger.exception(f"[Agent:{self.call_sid[:8]}] book_appointment DB error: {exc}")
            return {"ok": False, "error": str(exc)}

    async def _check_availability(self, args: dict) -> dict:
        """Check how many jobs are on each of the next 7 business days and return open slots."""
        preferred_date_str = args.get("preferred_date", "next_available")
        today = date.today()

        # Collect the next 7 business days
        business_days: list[date] = []
        d = today + timedelta(days=1)
        while len(business_days) < 7:
            if d.weekday() < 5:  # Mon–Fri
                business_days.append(d)
            d += timedelta(days=1)

        available_slots: list[dict] = []
        try:
            async with async_session_maker() as session:
                for day in business_days:
                    count_result = await session.execute(
                        select(func.count())
                        .select_from(WorkOrder)
                        .where(WorkOrder.scheduled_date == day)
                        .where(WorkOrder.status.not_in(["canceled"]))
                    )
                    job_count = count_result.scalar() or 0

                    if job_count < 6:
                        slots = []
                        if job_count < 4:
                            slots.append("morning (8am–12pm)")
                        if job_count < 6:
                            slots.append("afternoon (12pm–5pm)")
                        available_slots.append({
                            "date": str(day),
                            "label": day.strftime("%A, %B %d"),
                            "slots": slots,
                            "jobs_scheduled": job_count,
                        })
        except Exception as exc:
            logger.exception(f"[Agent:{self.call_sid[:8]}] check_availability DB error: {exc}")
            # Fall back to showing all days as available
            for day in business_days:
                available_slots.append({
                    "date": str(day),
                    "label": day.strftime("%A, %B %d"),
                    "slots": ["morning (8am–12pm)", "afternoon (12pm–5pm)"],
                    "jobs_scheduled": 0,
                })

        # Determine preferred day if given
        preferred_note = ""
        if preferred_date_str and preferred_date_str != "next_available":
            try:
                pref = date.fromisoformat(preferred_date_str)
                preferred_note = f" (Prospect prefers {pref.strftime('%A %B %d')})"
            except (ValueError, TypeError):
                pass

        return {
            "ok": True,
            "available_slots": available_slots[:5],  # Return top 5 days
            "note": f"Next available appointment days{preferred_note}",
        }

    async def _create_callback(self, args: dict) -> dict:
        """Create an AgentTask for a follow-up callback."""
        p = self.prospect
        callback_time = args.get("callback_time", "")
        notes = args.get("notes", "")

        customer_id_raw = p.get("id")
        if not customer_id_raw:
            return {"ok": False, "error": "No customer_id on prospect — cannot create callback task"}

        title = f"Call back {p.get('first_name', '')} {p.get('last_name', '')}".strip()
        description = f"Callback requested during outbound AI call. Requested time: {callback_time}."
        if notes:
            description += f" Notes: {notes}"

        try:
            async with async_session_maker() as session:
                task = AgentTask(
                    id=uuid.uuid4(),
                    agent_id=_OUTBOUND_AGENT_UUID,
                    customer_id=int(str(customer_id_raw)) if str(customer_id_raw).isdigit() else 0,
                    task_type="follow_up_call",
                    title=title,
                    description=description,
                    priority="normal",
                    status="pending",
                )
                session.add(task)
                await session.commit()
                task_id = str(task.id)

            self.disposition = "callback_requested"
            logger.info(f"[Agent:{self.call_sid[:8]}] Callback task {task_id} created for {callback_time!r}")
            return {"ok": True, "task_id": task_id, "callback_time": callback_time}
        except Exception as exc:
            logger.exception(f"[Agent:{self.call_sid[:8]}] create_callback DB error: {exc}")
            return {"ok": False, "error": str(exc)}

    async def _send_followup_sms(self, args: dict) -> dict:
        """Send a follow-up SMS to the prospect via Twilio."""
        message_body = args.get("message", "")
        if not message_body:
            return {"ok": False, "error": "No message text provided"}

        if not (settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN):
            logger.warning(f"[Agent:{self.call_sid[:8]}] Twilio not configured — SMS not sent")
            return {"ok": False, "error": "Twilio not configured"}

        # Determine from/to numbers
        from_number = settings.OUTBOUND_AGENT_FROM_NUMBER or settings.TWILIO_PHONE_NUMBER
        if not from_number:
            return {"ok": False, "error": "No from-number configured for outbound agent SMS"}

        raw_to = self.prospect.get("phone", "")
        to_number = self._normalize_phone(raw_to)
        if not to_number:
            return {"ok": False, "error": f"Invalid or missing prospect phone: {raw_to!r}"}

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json",
                    auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
                    data={
                        "From": from_number,
                        "To": to_number,
                        "Body": message_body,
                    },
                )

            if resp.status_code in (200, 201):
                sid = resp.json().get("sid", "")
                logger.info(f"[Agent:{self.call_sid[:8]}] SMS sent to {to_number}, SID={sid}")
                return {"ok": True, "message_sid": sid, "to": to_number}
            else:
                err = resp.text[:200]
                logger.error(f"[Agent:{self.call_sid[:8]}] Twilio SMS error {resp.status_code}: {err}")
                return {"ok": False, "error": f"Twilio error {resp.status_code}: {err}"}
        except Exception as exc:
            logger.exception(f"[Agent:{self.call_sid[:8]}] send_followup_sms error: {exc}")
            return {"ok": False, "error": str(exc)}

    @staticmethod
    def _normalize_phone(raw: str) -> str:
        """Normalize a phone number to E.164 format (+1XXXXXXXXXX for US numbers)."""
        if not raw:
            return ""
        # Strip everything except digits and leading +
        digits = "".join(c for c in raw if c.isdigit())
        if not digits:
            return ""
        if raw.startswith("+"):
            # Already has country code — keep as-is
            return "+" + digits
        if len(digits) == 10:
            return "+1" + digits
        if len(digits) == 11 and digits.startswith("1"):
            return "+" + digits
        # Return best-effort
        return "+" + digits

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
