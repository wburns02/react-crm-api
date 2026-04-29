"""OutboundAgentSession v2 — Pipecat-friendly session holder.

Re-uses the existing tool-call helpers from app/services/outbound_agent.py
to avoid duplicating Twilio/DB code. The new responsibilities are:
  - HallucinationGuard wrapping every LLM completion before TTS
  - SessionStateMachine driving forced actions
  - FragmentMerger filtering Deepgram output for short fragments
  - Anthropic context with prompt-cache markers on system + tools

All persistence and Twilio SMS/transfer side-effects come from the legacy
helpers; nothing in this file talks to Twilio or the DB directly.
"""
import time

from app.services.outbound_agent import OutboundAgentSession as LegacySession
from app.services.voice_agent.aggregators import FragmentMerger
from app.services.voice_agent.hallucination_guard import HallucinationGuard
from app.services.voice_agent.state_machine import (
    ForcedAction,
    SessionStateMachine,
)
from app.services.voice_agent.system_prompt import render as render_system_prompt
from app.services.voice_agent.tools import AGENT_TOOLS


class OutboundAgentSession:
    """Pipecat-flavored session. Delegates tool side-effects to legacy."""

    def __init__(
        self,
        call_sid: str,
        prospect: dict,
        quote: dict,
        stream_sid: str | None = None,
    ):
        self.call_sid = call_sid
        self.prospect = prospect
        self.quote = quote
        self.stream_sid = stream_sid

        # Re-use the legacy helper class for tool side-effects only.
        # We don't drive its conversation loop — Pipecat owns that now.
        self._legacy_helpers = LegacySession(
            call_sid=call_sid,
            prospect=prospect,
            quote=quote,
        )

        self.guard = HallucinationGuard()
        self.state = SessionStateMachine()
        self.fragment_merger = FragmentMerger()

        self.start_time = time.monotonic()
        self.last_user_speech_at = self.start_time
        self.agent_speaking = False

        self.disposition: str | None = None
        self.disposition_notes: str = ""
        self.hallucinations_log: list[dict] = []
        self.amd_result: str | None = None
        # Set by review_assistant_message when Sarah says goodbye after a
        # disposition has been set. The WS handler polls this each tick and
        # shuts the pipeline down when it flips True.
        self.should_end_call: bool = False
        # Set True by the WS handler when the pipeline finishes; campaign_dialer
        # polls this to decide when to dial the next prospect.
        self.ended: bool = False

        self.system_prompt = render_system_prompt(self._build_prospect_context())
        self.tools = AGENT_TOOLS  # passed to AnthropicLLMService

    def _build_prospect_context(self) -> str:
        p = self.prospect
        q = self.quote
        total = q.get("total", 0) or 0
        return (
            f"Name: {p.get('first_name', '')} {p.get('last_name', '')}\n"
            f"Phone: {p.get('phone', '')}\n"
            f"City/State: {p.get('city', '')}, {p.get('state', '')}\n"
            f"Quote: {q.get('quote_number', '')} — {q.get('title', '')} — ${float(total):.2f}\n"
            f"Sent: {q.get('sent_at', 'recently')}\n"
        )

    async def _handle_tool_call(self, name: str, tool_id: str, args: dict) -> dict:
        """Forward to legacy helpers and update state machine."""
        result = await self._legacy_helpers._handle_tool_call(name, tool_id, args)
        ok = bool(result.get("ok", False)) if isinstance(result, dict) else False
        self.state.note_tool_call_result(success=ok)

        # Progress signals so time-hangup picks the right disposition
        if name == "book_appointment" and ok:
            self.state.note_progress_signal("appointment_booked")
            # Auto-set disposition if the LLM didn't explicitly call set_disposition.
            # Without this, the goodbye-detector + auto-end-call watcher never fires
            # because it requires self.disposition to be set. Observed on call #9:
            # booking succeeded, Sarah said "have a good one", but pipeline didn't
            # close because no disposition was on the session.
            if not self.disposition:
                self.disposition = "appointment_set"
                self.disposition_notes = (
                    f"Auto-set after book_appointment succeeded "
                    f"(work_order={result.get('work_order_number', '?')})"
                )
        elif name == "create_callback" and ok:
            self.state.note_progress_signal("callback_discussed")
            if not self.disposition:
                self.disposition = "callback_requested"
                self.disposition_notes = "Auto-set after create_callback succeeded"
        elif name == "transfer_call":
            self.state.note_progress_signal("transfer_mentioned")
            if not self.disposition:
                self.disposition = "transferred_to_sales"
                self.disposition_notes = (
                    f"Auto-set after transfer_call: {args.get('reason', '')}"
                )
        elif name == "set_disposition":
            self.disposition = args.get("disposition")
            self.disposition_notes = args.get("notes", "")
        return result

    def review_assistant_message(self, *, text: str, tool_calls: list[dict]) -> str:
        """Run the hallucination guard. Returns rewritten text for TTS."""
        result = self.guard.check(text=text, tool_calls=tool_calls)
        if result.hallucinations:
            self.hallucinations_log.extend(result.hallucinations)

        # Detect goodbye-style closers. If Sarah is wrapping up AND we've
        # already set a disposition, mark the session for auto-end-call so the
        # WS handler shuts down the pipeline. The LLM repeatedly fails to
        # call end_call itself even when prompted, so we enforce it here.
        import re as _re
        lowered = result.rewritten_text.lower()
        goodbye_patterns = (
            r"\b(have a (great|good) (day|one))\b",
            r"\bbye\b",
            r"\btake care\b",
            r"\btalk to you (later|soon)\b",
            r"\bgood talking with you\b",
            r"\bappreciate (it|your time)\b",
            r"\byou're all set\b",
            r"\bthat's all (i|we) need(ed)?\b",
            r"\bthanks (so much|again)\b",
        )
        said_goodbye = any(_re.search(p, lowered) for p in goodbye_patterns)
        if said_goodbye and self.disposition:
            self.should_end_call = True
        return result.rewritten_text

    def note_user_turn(self, text: str) -> None:
        self.last_user_speech_at = time.monotonic()
        # Heuristic: any mention of audio/quality/delay/scripted/AI from the customer
        lowered = text.lower()
        triggers = (
            "delay", "delayed", "took.*second", "long.*wait",
            "voice quality", "audio quality", "quality is",
            "robot", "robotic", "sound.*robot",
            "script", "scripted", "reading.*off",
            "are you ai", "are you a real", "are you a person",
            "not responding", "not listening",
        )
        import re as _re
        if any(_re.search(t, lowered) for t in triggers):
            self.state.note_audio_quality_complaint()

    def tick(self) -> ForcedAction | None:
        return self.state.tick(
            now_seconds=time.monotonic() - self.start_time,
            last_user_speech_at=self.last_user_speech_at - self.start_time,
            agent_speaking=self.agent_speaking,
        )
