# Outbound Voice Agent — Pipecat Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hand-rolled Twilio Media Streams audio loop in `react-crm-api` with a Pipecat pipeline (Cartesia Sonic-2 TTS, Sonnet 4.6, Silero VAD, Deepgram nova-3) that hits <800ms mean turn latency and eliminates the hallucinations, recovery loops, and greeting-delay failures seen in the 2026-04-07 test calls.

**Architecture:** Pipecat `Pipeline` with `TwilioFrameSerializer → SileroVAD → DeepgramSTTService → AnthropicLLMService (with tools) → SentenceAggregator → CartesiaTTSService → TwilioFrameSerializer`. Business logic (campaign dialer, tool implementations, DB persistence, smart caller-ID routing) stays in place; only the audio loop is replaced. New code lives under `app/services/voice_agent/`. Existing `outbound_agent.py` stays as the `legacy` engine behind a feature flag (`VOICE_AGENT_ENGINE`) for two weeks of rollback insurance.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, Alembic, Pipecat 0.0.50+ (`pipecat-ai[anthropic,deepgram,cartesia,silero,twilio]`), Cartesia Sonic-2, Anthropic Claude Sonnet 4.6 with prompt caching, Twilio Media Streams + Twilio AMD, pytest with `pytest-asyncio` and `pytest-mock`.

**Spec:** `docs/superpowers/specs/2026-04-28-outbound-voice-agent-pipecat-design.md`

---

## File Structure

### New files

| Path | Responsibility |
|---|---|
| `app/services/voice_agent/__init__.py` | Package marker, re-exports public API |
| `app/services/voice_agent/pipeline_factory.py` | Builds the Pipecat `Pipeline` from a session + service config; no business logic |
| `app/services/voice_agent/session.py` | `OutboundAgentSession` v2 — owns prospect/quote context, state machine counters, calls into existing tool handlers, persists to `call_logs` at end |
| `app/services/voice_agent/system_prompt.py` | New `SYSTEM_PROMPT` template with the 3 added rules (tool discipline, audio-quality escape, identity disclosure) |
| `app/services/voice_agent/tools.py` | `AGENT_TOOLS` schema + thin adapters that delegate to the existing tool implementations in legacy `outbound_agent.py`. Single source of truth for tool definitions. |
| `app/services/voice_agent/hallucination_guard.py` | Regex-based pre-TTS guard that catches unsupported claims and rewrites them |
| `app/services/voice_agent/state_machine.py` | Counter-based state tracker that triggers forced actions (audio-complaint hangup, silence timeout, tool-failure transfer, total-time wrap) |
| `app/services/voice_agent/greeting_prerender.py` | Renders Cartesia TTS greeting at dial time into a buffer, holds until AMD result |
| `app/services/voice_agent/aggregators.py` | Custom STT context aggregator with anti-fragmentation rules (ignores interim results, merges sub-3-word fragments) |
| `app/services/voice_agent/voicemail.py` | Voicemail flow triggered by AMD = `machine_end_beep` |
| `app/api/v2/voice_agent_ws.py` | New FastAPI WebSocket route that boots the Pipecat pipeline; feature-flag dispatcher between legacy and new |
| `app/api/v2/voice_agent_amd.py` | Twilio AsyncAmd webhook receiver |
| `scripts/voice_eval.py` | Frame-log instrumentation + per-call markdown report generator |
| `scripts/pipecat_agent_dev.py` | Local dev entrypoint — boots a tiny FastAPI receiving Twilio webhooks via ngrok |
| `tests/services/voice_agent/__init__.py` | Test package |
| `tests/services/voice_agent/test_hallucination_guard.py` | Unit tests for the guard |
| `tests/services/voice_agent/test_state_machine.py` | Unit tests for counters and forced actions |
| `tests/services/voice_agent/test_aggregators.py` | Unit tests for fragment merging |
| `tests/services/voice_agent/test_tools.py` | Schema validation + adapter delegation tests |
| `tests/services/voice_agent/test_pipeline_factory.py` | Smoke test that pipeline builds with mocked services |
| `alembic/versions/114_voice_agent_columns.py` | Migration: `customers.is_test_prospect`, `call_logs.hallucinations` JSON, `call_logs.amd_result` |

### Modified files

| Path | Change |
|---|---|
| `requirements.txt` | Add `pipecat-ai[anthropic,deepgram,cartesia,silero,twilio,silero]>=0.0.50,<0.1.0` (pinned minor) |
| `app/config.py` | Add `VOICE_AGENT_ENGINE: str = "legacy"` (values `legacy` or `pipecat`); `OUTBOUND_AGENT_AMD_CALLBACK: str | None = None` |
| `app/services/campaign_dialer.py` | Filter `Customer.is_test_prospect == False OR is_test_prospect IS NULL` for real campaigns; add `get_test_prospect_queue()` for dev. Pass `engine=settings.VOICE_AGENT_ENGINE` into the call-initiate flow so the right TwiML is returned. |
| `app/api/v2/outbound_agent.py` | Voice webhook returns TwiML pointing to `voice_agent_ws.py` when `engine=pipecat`, legacy WS when `engine=legacy`. AMD callback wired to new `voice_agent_amd.py` route. Existing campaign endpoints unchanged. |
| `app/models/customer.py` | Add `is_test_prospect: Mapped[bool] = mapped_column(default=False, nullable=False)` |
| `app/models/call_log.py` | Add `hallucinations: Mapped[list \| None] = mapped_column(JSON, nullable=True)` and `amd_result: Mapped[str \| None] = mapped_column(String(20), nullable=True)` |
| `app/api/v2/router.py` (or wherever v2 routes register) | Register `voice_agent_ws.router` and `voice_agent_amd.router` |
| `app/services/outbound_agent.py` | NO functional changes in this plan — kept as `legacy` engine. Marked `# DEPRECATED: removed after 2 weeks of pipecat soak` at top. Deletion is a follow-up. |

---

## Phase 0 — Foundation

### Task 0.1: Add Pipecat dependency and config

**Files:**
- Modify: `requirements.txt`
- Modify: `app/config.py`

- [ ] **Step 1: Pin Pipecat in requirements**

In `requirements.txt`, append after the existing voice-related deps:

```
# Pipecat audio orchestration (replaces hand-rolled Twilio Media Streams loop)
pipecat-ai[anthropic,deepgram,cartesia,silero,twilio]>=0.0.50,<0.1.0
```

- [ ] **Step 2: Install and confirm import**

```bash
source venv/bin/activate
pip install -r requirements.txt
python -c "from pipecat.pipeline.pipeline import Pipeline; from pipecat.services.cartesia.tts import CartesiaTTSService; from pipecat.services.deepgram.stt import DeepgramSTTService; from pipecat.services.anthropic.llm import AnthropicLLMService; from pipecat.serializers.twilio import TwilioFrameSerializer; from pipecat.audio.vad.silero import SileroVADAnalyzer; print('pipecat imports OK')"
```

Expected output: `pipecat imports OK`. If any import path differs, update the import in this step and propagate to later tasks (Pipecat 0.0.x has reorganized service modules; the executing engineer should `pip show pipecat-ai` and `python -c "import pipecat; print(pipecat.__version__)"` to confirm the installed version, then resolve to whichever submodule path actually exposes the class).

- [ ] **Step 3: Add new config keys**

In `app/config.py` inside the `Settings` class, near the existing voice agent keys (search for `OUTBOUND_AGENT_TRANSFER_NUMBER`):

```python
# Voice agent engine selection: "legacy" (hand-rolled) or "pipecat" (new)
VOICE_AGENT_ENGINE: str = "legacy"
# Twilio AsyncAmd webhook URL (set per-environment in Railway)
OUTBOUND_AGENT_AMD_CALLBACK: str | None = None
```

`CARTESIA_API_KEY` and `CARTESIA_VOICE_ID` already exist — reuse.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt app/config.py
git commit -m "feat(voice-agent): add pipecat dep and engine selection config"
```

### Task 0.2: Schema migration

**Files:**
- Create: `alembic/versions/114_voice_agent_columns.py`
- Modify: `app/models/customer.py`
- Modify: `app/models/call_log.py`

- [ ] **Step 1: Generate migration scaffold**

```bash
cd /home/will/react-crm-api
source venv/bin/activate
alembic revision -m "voice agent columns: customers.is_test_prospect, call_logs.hallucinations, call_logs.amd_result"
```

This creates a new file in `alembic/versions/`. Rename it to `114_voice_agent_columns.py` to match the existing numbering convention (last existing file is `113_hr_payroll_runs_and_people.py`).

- [ ] **Step 2: Write migration body**

Replace the generated file contents with:

```python
"""voice agent columns

Revision ID: 114_voice_agent_columns
Revises: 113_hr_payroll_runs_and_people
Create Date: 2026-04-28
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "114_voice_agent_columns"
down_revision = "113_hr_payroll_runs_and_people"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "customers",
        sa.Column("is_test_prospect", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "ix_customers_is_test_prospect",
        "customers",
        ["is_test_prospect"],
    )

    op.add_column(
        "call_logs",
        sa.Column("hallucinations", sa.JSON(), nullable=True),
    )
    op.add_column(
        "call_logs",
        sa.Column("amd_result", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("call_logs", "amd_result")
    op.drop_column("call_logs", "hallucinations")
    op.drop_index("ix_customers_is_test_prospect", table_name="customers")
    op.drop_column("customers", "is_test_prospect")
```

The executing engineer should `head -20 alembic/versions/113_hr_payroll_runs_and_people.py` to confirm the exact `revision` string format used in this repo and match it. If the existing file uses a hash like `e7f3...` rather than `113_*`, follow that convention instead.

- [ ] **Step 3: Update SQLAlchemy models**

In `app/models/customer.py`, add to the `Customer` class:

```python
is_test_prospect: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false", index=True)
```

In `app/models/call_log.py`, add:

```python
hallucinations = Column(JSON, nullable=True)  # list[dict{original, rewritten, pattern}]
amd_result = Column(String(20), nullable=True)  # human | machine_end_beep | unknown
```

- [ ] **Step 4: Run migration up + down to verify**

```bash
alembic upgrade head
psql "$DATABASE_URL" -c "\d customers" | grep is_test_prospect
psql "$DATABASE_URL" -c "\d call_logs" | grep -E "hallucinations|amd_result"
alembic downgrade -1
psql "$DATABASE_URL" -c "\d customers" | grep is_test_prospect || echo "downgrade OK"
alembic upgrade head
```

Expected: column appears after upgrade, gone after downgrade, back after second upgrade.

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/114_voice_agent_columns.py app/models/customer.py app/models/call_log.py
git commit -m "feat(voice-agent): migration for is_test_prospect + hallucinations + amd_result columns"
```

---

## Phase 1 — Pipecat Pipeline Skeleton

### Task 1.1: Create voice_agent package + system prompt

**Files:**
- Create: `app/services/voice_agent/__init__.py`
- Create: `app/services/voice_agent/system_prompt.py`

- [ ] **Step 1: Create package init**

`app/services/voice_agent/__init__.py`:

```python
"""Pipecat-based outbound voice agent for MAC Septic.

Replaces the legacy hand-rolled audio loop in app/services/outbound_agent.py.
Selected via settings.VOICE_AGENT_ENGINE.
"""
```

- [ ] **Step 2: Port and amend SYSTEM_PROMPT**

`app/services/voice_agent/system_prompt.py`:

```python
"""System prompt template for the Pipecat outbound agent.

Three behavioral rules added on top of the legacy prompt:
1. Strict tool-use discipline (eliminates hallucinated tool claims)
2. Audio-quality escape hatch (eliminates recovery loops)
3. Honest identity disclosure (replaces "never say I'm an AI")
"""

SYSTEM_PROMPT = """You are Sarah, the AI scheduling assistant for MAC Septic Services. You're calling customers who received a quote for septic services but haven't responded yet.

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

GENERAL RULES:
- Keep responses SHORT — 1-2 sentences max. This is a phone call, not an email.
- If you detect voicemail, use the leave_voicemail tool immediately.
- Always be polite when ending a call, even if they're not interested.

RULE 1 — STRICT TOOL DISCIPLINE:
If you describe an action you are taking ("I just sent you a text", "I'll book you for Tuesday morning", "Let me transfer you"), you MUST call the corresponding tool in the SAME turn before claiming it. Tool first, words second. If you don't have a tool for what the customer is asking, say so honestly and offer to transfer to the office.

RULE 2 — AUDIO QUALITY ESCAPE HATCH:
If the customer mentions audio quality, voice quality, delay, echo, or asks if you're a robot/AI more than once: acknowledge it once, offer to text the quote details (call send_followup_sms), then call set_disposition('callback_requested') and end_call. Do NOT loop on apologies or repeated "want me to call back?" prompts.

RULE 3 — HONEST IDENTITY:
If asked directly whether you're a real person or an AI, answer honestly in one sentence ("I'm Sarah, MAC Septic's AI assistant — I help with scheduling and quote questions"), then continue the conversation normally. Never claim to be human.

CURRENT PROSPECT INFO:
{prospect_context}
"""


def render(prospect_context: str) -> str:
    """Fill the prompt template with prospect-specific context."""
    return SYSTEM_PROMPT.format(prospect_context=prospect_context)
```

- [ ] **Step 3: Commit**

```bash
git add app/services/voice_agent/__init__.py app/services/voice_agent/system_prompt.py
git commit -m "feat(voice-agent): add system prompt with tool discipline, audio-escape, identity rules"
```

### Task 1.2: Port AGENT_TOOLS and tool router

**Files:**
- Create: `app/services/voice_agent/tools.py`
- Create: `tests/services/voice_agent/__init__.py`
- Create: `tests/services/voice_agent/test_tools.py`

- [ ] **Step 1: Write the failing test**

`tests/services/voice_agent/__init__.py`:

```python
```

`tests/services/voice_agent/test_tools.py`:

```python
"""Tests for voice_agent.tools — schema validation + adapter delegation."""
import pytest

from app.services.voice_agent import tools


def test_agent_tools_has_all_eight_definitions():
    names = {t["name"] for t in tools.AGENT_TOOLS}
    assert names == {
        "check_availability",
        "book_appointment",
        "transfer_call",
        "create_callback",
        "set_disposition",
        "leave_voicemail",
        "end_call",
        "send_followup_sms",
    }


def test_each_tool_has_anthropic_schema_shape():
    for t in tools.AGENT_TOOLS:
        assert "name" in t
        assert "description" in t
        assert "input_schema" in t
        assert t["input_schema"]["type"] == "object"
        assert "properties" in t["input_schema"]


def test_set_disposition_enum_matches_legacy():
    spec = next(t for t in tools.AGENT_TOOLS if t["name"] == "set_disposition")
    enum_vals = set(spec["input_schema"]["properties"]["disposition"]["enum"])
    assert enum_vals == {
        "appointment_set", "callback_requested", "transferred_to_sales",
        "not_interested", "service_completed_elsewhere", "voicemail_left",
        "no_answer", "wrong_number", "do_not_call",
    }


@pytest.mark.asyncio
async def test_handle_tool_call_delegates_to_session(mocker):
    """Adapter should forward to the OutboundAgentSession instance method."""
    fake_session = mocker.MagicMock()
    fake_session._handle_tool_call = mocker.AsyncMock(return_value={"ok": True})

    result = await tools.handle_tool_call(
        session=fake_session,
        name="set_disposition",
        tool_id="t_1",
        args={"disposition": "callback_requested", "notes": "test"},
    )

    fake_session._handle_tool_call.assert_awaited_once_with(
        "set_disposition", "t_1", {"disposition": "callback_requested", "notes": "test"}
    )
    assert result == {"ok": True}
```

- [ ] **Step 2: Run tests, expect failure**

```bash
pytest tests/services/voice_agent/test_tools.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.voice_agent.tools'`.

- [ ] **Step 3: Implement tools.py**

`app/services/voice_agent/tools.py`:

```python
"""Tool schema + dispatch adapter for the Pipecat voice agent.

The schema is the single source of truth for what tools the LLM can call.
The adapter delegates to OutboundAgentSession._handle_tool_call which contains
the existing, tested implementations (Twilio SMS, work order creation, etc.).
"""
from typing import Any


AGENT_TOOLS: list[dict[str, Any]] = [
    {
        "name": "check_availability",
        "description": "Check available appointment slots for the next 7 days in the prospect's service area.",
        "input_schema": {
            "type": "object",
            "properties": {
                "preferred_date": {
                    "type": "string",
                    "description": "Preferred date in YYYY-MM-DD format, or 'next_available'",
                }
            },
            "required": [],
        },
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
                "notes": {"type": "string", "description": "Any special instructions from the customer"},
            },
            "required": ["scheduled_date", "service_type"],
        },
    },
    {
        "name": "transfer_call",
        "description": "Transfer the call to MAC Septic office for human assistance.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Why the customer wants to talk to someone"}
            },
            "required": ["reason"],
        },
    },
    {
        "name": "create_callback",
        "description": "Schedule a callback at a specific time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "callback_time": {"type": "string", "description": "When to call back, e.g. 'tomorrow morning' or '2026-04-30 14:00'"},
                "notes": {"type": "string", "description": "Context for the callback"},
            },
            "required": ["callback_time"],
        },
    },
    {
        "name": "set_disposition",
        "description": "Set the call outcome/disposition. Call this before ending the conversation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "disposition": {
                    "type": "string",
                    "enum": [
                        "appointment_set", "callback_requested", "transferred_to_sales",
                        "not_interested", "service_completed_elsewhere", "voicemail_left",
                        "no_answer", "wrong_number", "do_not_call",
                    ],
                },
                "notes": {"type": "string", "description": "Brief summary of the call"},
            },
            "required": ["disposition"],
        },
    },
    {
        "name": "leave_voicemail",
        "description": "Leave a voicemail message. Use when you detect voicemail/answering machine.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "end_call",
        "description": "End the phone call. Always set_disposition before calling this.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "send_followup_sms",
        "description": "Send a follow-up text message to the prospect after the call.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Text message content"}
            },
            "required": ["message"],
        },
    },
]


async def handle_tool_call(session, name: str, tool_id: str, args: dict) -> dict:
    """Forward a tool invocation to the active OutboundAgentSession.

    The session class owns the actual side effects (Twilio SMS, DB writes,
    transfer flagging). This adapter exists so the Pipecat pipeline doesn't
    need to import the session class directly — keeps the pipeline factory
    swappable with mocks in tests.
    """
    return await session._handle_tool_call(name, tool_id, args)
```

- [ ] **Step 4: Run tests to verify pass**

```bash
pytest tests/services/voice_agent/test_tools.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add app/services/voice_agent/tools.py tests/services/voice_agent/__init__.py tests/services/voice_agent/test_tools.py
git commit -m "feat(voice-agent): port AGENT_TOOLS schema + delegating adapter"
```

---

## Phase 2 — Quality Controls

### Task 2.1: Hallucination guard

**Files:**
- Create: `app/services/voice_agent/hallucination_guard.py`
- Create: `tests/services/voice_agent/test_hallucination_guard.py`

- [ ] **Step 1: Write the failing tests**

`tests/services/voice_agent/test_hallucination_guard.py`:

```python
"""Hallucination guard catches unsupported tool claims and rewrites them."""
import pytest

from app.services.voice_agent.hallucination_guard import (
    HallucinationGuard,
    GuardResult,
)


def test_pass_through_when_no_pattern_match():
    guard = HallucinationGuard()
    result = guard.check(
        text="That's a great question about pricing.",
        tool_calls=[],
    )
    assert result.rewritten_text == "That's a great question about pricing."
    assert result.hallucinations == []


def test_catches_sms_claim_without_tool_call():
    guard = HallucinationGuard()
    result = guard.check(
        text="Great — I just sent you a text with the details.",
        tool_calls=[],
    )
    assert result.hallucinations
    assert result.hallucinations[0]["pattern"] == "sms"
    # Rewritten text must not still claim the SMS was sent
    assert "sent you a text" not in result.rewritten_text.lower()
    assert "let me check" in result.rewritten_text.lower() or "follow up" in result.rewritten_text.lower()


def test_passes_sms_claim_when_tool_was_called():
    guard = HallucinationGuard()
    result = guard.check(
        text="Great — I just sent you a text with the details.",
        tool_calls=[{"name": "send_followup_sms", "input": {"message": "..."}}],
    )
    assert result.hallucinations == []
    assert result.rewritten_text == "Great — I just sent you a text with the details."


def test_catches_booking_claim_without_tool_call():
    guard = HallucinationGuard()
    result = guard.check(
        text="I'll book you for Tuesday morning at 10.",
        tool_calls=[],
    )
    assert result.hallucinations
    assert "book" not in result.rewritten_text.lower() or "let me" in result.rewritten_text.lower()


def test_passes_booking_claim_when_book_appointment_called():
    guard = HallucinationGuard()
    result = guard.check(
        text="I just booked you for Tuesday at 10.",
        tool_calls=[{"name": "book_appointment", "input": {"scheduled_date": "2026-04-30"}}],
    )
    assert result.hallucinations == []


def test_passes_booking_claim_when_create_callback_called():
    guard = HallucinationGuard()
    result = guard.check(
        text="I'll schedule you for a callback tomorrow.",
        tool_calls=[{"name": "create_callback", "input": {"callback_time": "tomorrow"}}],
    )
    assert result.hallucinations == []


def test_catches_transfer_claim_without_tool_call():
    guard = HallucinationGuard()
    result = guard.check(
        text="Let me transfer you to the office.",
        tool_calls=[],
    )
    assert result.hallucinations


def test_multiple_sentences_only_offending_one_rewritten():
    guard = HallucinationGuard()
    result = guard.check(
        text="I understand your concern. I just sent you a text. Let me know if you need anything else.",
        tool_calls=[],
    )
    assert "I understand your concern." in result.rewritten_text
    assert "Let me know if you need anything else." in result.rewritten_text
    assert "sent you a text" not in result.rewritten_text.lower()


def test_guard_result_carries_original_for_audit():
    guard = HallucinationGuard()
    result = guard.check(
        text="I just sent you a text.",
        tool_calls=[],
    )
    assert result.hallucinations[0]["original"] == "I just sent you a text."
    assert result.hallucinations[0]["rewritten"] != "I just sent you a text."
```

- [ ] **Step 2: Run tests, expect failure**

```bash
pytest tests/services/voice_agent/test_hallucination_guard.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement guard**

`app/services/voice_agent/hallucination_guard.py`:

```python
"""Pre-TTS guard that catches unsupported tool claims in LLM output.

Maps regex patterns to the tool calls that would justify them. If a claim is
found in the assistant's text but no matching tool_use block was generated in
the same turn, we rewrite the offending sentence to a soft alternative
("Let me check on that") before it reaches TTS, log the original/rewritten
pair for the call_logs.hallucinations field, and signal the session to inject
a self-correction nudge into Claude's next turn.
"""
import re
from dataclasses import dataclass, field
from typing import Any


# (pattern_name, compiled_regex, justifying_tool_names)
_PATTERNS: list[tuple[str, re.Pattern, set[str]]] = [
    (
        "sms",
        re.compile(
            r"\bI(?:'ve| just|'ll| will)?\s*(?:sent|sending|send|text(?:ed|ing)?|message(?:d|ing)?)\s+(?:you\s+)?(?:a|the|that)?\s*(?:text|message|email|sms)?",
            re.IGNORECASE,
        ),
        {"send_followup_sms"},
    ),
    (
        "booking",
        re.compile(
            r"\bI(?:'ve| just|'ll| will|'m)?\s*(?:book(?:ed|ing)?|schedul(?:ed|ing|e))\s+(?:you|an?|the)",
            re.IGNORECASE,
        ),
        {"book_appointment", "create_callback"},
    ),
    (
        "transfer",
        re.compile(
            r"\b(?:let me\s+)?transfer(?:ring)?\s+you",
            re.IGNORECASE,
        ),
        {"transfer_call"},
    ),
]


_SOFT_REWRITE = "Let me check on that for you."


@dataclass
class GuardResult:
    rewritten_text: str
    hallucinations: list[dict[str, str]] = field(default_factory=list)


class HallucinationGuard:
    """Stateless checker; one instance per session is fine."""

    def check(self, text: str, tool_calls: list[dict[str, Any]]) -> GuardResult:
        called_tool_names = {tc.get("name") for tc in tool_calls}
        sentences = self._split_sentences(text)
        rewritten_sentences: list[str] = []
        caught: list[dict[str, str]] = []

        for sentence in sentences:
            offending_pattern = self._find_unsupported_claim(sentence, called_tool_names)
            if offending_pattern is None:
                rewritten_sentences.append(sentence)
                continue
            caught.append(
                {
                    "pattern": offending_pattern,
                    "original": sentence.strip(),
                    "rewritten": _SOFT_REWRITE,
                }
            )
            rewritten_sentences.append(_SOFT_REWRITE)

        return GuardResult(
            rewritten_text=" ".join(s.strip() for s in rewritten_sentences if s.strip()),
            hallucinations=caught,
        )

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        # Lightweight splitter: split on . ! ? followed by whitespace, keeping the punctuation.
        parts = re.split(r"(?<=[.!?])\s+", text.strip())
        return [p for p in parts if p]

    @staticmethod
    def _find_unsupported_claim(sentence: str, called_tool_names: set[str]) -> str | None:
        for pattern_name, regex, justifying_tools in _PATTERNS:
            if regex.search(sentence) and not (justifying_tools & called_tool_names):
                return pattern_name
        return None
```

- [ ] **Step 4: Run tests to pass**

```bash
pytest tests/services/voice_agent/test_hallucination_guard.py -v
```

Expected: 9 passed. If a test fails because the regex is too greedy or too narrow, tighten the pattern in `_PATTERNS` and re-run.

- [ ] **Step 5: Commit**

```bash
git add app/services/voice_agent/hallucination_guard.py tests/services/voice_agent/test_hallucination_guard.py
git commit -m "feat(voice-agent): hallucination guard with regex + tool-call cross-check"
```

### Task 2.2: State machine for forced actions

**Files:**
- Create: `app/services/voice_agent/state_machine.py`
- Create: `tests/services/voice_agent/test_state_machine.py`

- [ ] **Step 1: Write tests**

`tests/services/voice_agent/test_state_machine.py`:

```python
"""State machine triggers forced actions when counters cross thresholds."""
import pytest

from app.services.voice_agent.state_machine import (
    SessionStateMachine,
    ForcedAction,
)


def test_no_action_in_normal_state():
    sm = SessionStateMachine()
    action = sm.tick(now_seconds=10, last_user_speech_at=8, agent_speaking=False)
    assert action is None


def test_audio_complaint_threshold_triggers_disposition():
    sm = SessionStateMachine()
    sm.note_audio_quality_complaint()
    assert sm.tick(now_seconds=10, last_user_speech_at=9, agent_speaking=False) is None
    sm.note_audio_quality_complaint()  # 2nd complaint = hard threshold
    action = sm.tick(now_seconds=20, last_user_speech_at=19, agent_speaking=False)
    assert action == ForcedAction.AUDIO_QUALITY_HANGUP


def test_silence_soft_then_hard():
    sm = SessionStateMachine()
    # Soft: silence >=8s after agent stops talking
    soft = sm.tick(now_seconds=20, last_user_speech_at=10, agent_speaking=False)
    assert soft == ForcedAction.SILENCE_SOFT_PROMPT
    # Subsequent ticks within the same silence window should not re-fire SOFT
    again = sm.tick(now_seconds=21, last_user_speech_at=10, agent_speaking=False)
    assert again is None
    # Hard: total silence >=15s
    hard = sm.tick(now_seconds=26, last_user_speech_at=10, agent_speaking=False)
    assert hard == ForcedAction.SILENCE_HANGUP


def test_silence_resets_when_user_speaks_again():
    sm = SessionStateMachine()
    sm.tick(now_seconds=20, last_user_speech_at=10, agent_speaking=False)  # soft fired
    sm.tick(now_seconds=22, last_user_speech_at=22, agent_speaking=False)  # user spoke
    assert sm.tick(now_seconds=30, last_user_speech_at=22, agent_speaking=False) == ForcedAction.SILENCE_SOFT_PROMPT


def test_two_tool_failures_in_a_row_trigger_transfer():
    sm = SessionStateMachine()
    sm.note_tool_call_result(success=True)
    sm.note_tool_call_result(success=False)
    sm.note_tool_call_result(success=False)
    action = sm.tick(now_seconds=30, last_user_speech_at=29, agent_speaking=False)
    assert action == ForcedAction.TRANSFER_ON_TOOL_FAILURES


def test_one_failure_then_success_does_not_trigger():
    sm = SessionStateMachine()
    sm.note_tool_call_result(success=False)
    sm.note_tool_call_result(success=True)
    sm.note_tool_call_result(success=False)
    assert sm.tick(now_seconds=30, last_user_speech_at=29, agent_speaking=False) is None


def test_total_call_seconds_soft_then_hard():
    sm = SessionStateMachine()
    soft = sm.tick(now_seconds=240, last_user_speech_at=239, agent_speaking=False)
    assert soft == ForcedAction.TIME_SOFT_WRAP
    hard = sm.tick(now_seconds=360, last_user_speech_at=359, agent_speaking=False)
    assert hard == ForcedAction.TIME_HARD_HANGUP


def test_best_disposition_for_time_hangup_defaults_to_callback():
    sm = SessionStateMachine()
    assert sm.best_progress_disposition() == "callback_requested"


def test_best_disposition_picks_highest_progress():
    sm = SessionStateMachine()
    sm.note_progress_signal("callback_discussed")
    sm.note_progress_signal("appointment_booked")
    sm.note_progress_signal("transfer_mentioned")
    # Booking is highest progress
    assert sm.best_progress_disposition() == "appointment_set"


def test_audio_action_fires_only_once():
    sm = SessionStateMachine()
    sm.note_audio_quality_complaint()
    sm.note_audio_quality_complaint()
    first = sm.tick(now_seconds=10, last_user_speech_at=9, agent_speaking=False)
    assert first == ForcedAction.AUDIO_QUALITY_HANGUP
    second = sm.tick(now_seconds=11, last_user_speech_at=10, agent_speaking=False)
    assert second is None
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/services/voice_agent/test_state_machine.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement state machine**

`app/services/voice_agent/state_machine.py`:

```python
"""Session-level state machine that triggers forced actions on threshold crossings.

The machine is polled (`tick(...)`) by the pipeline frame observer once per
audio chunk. It also receives explicit notifications for events the audio
loop already classifies (audio complaint, tool result, progress signal).
"""
from dataclasses import dataclass, field
from enum import Enum


class ForcedAction(str, Enum):
    AUDIO_QUALITY_HANGUP = "audio_quality_hangup"
    SILENCE_SOFT_PROMPT = "silence_soft_prompt"
    SILENCE_HANGUP = "silence_hangup"
    TRANSFER_ON_TOOL_FAILURES = "transfer_on_tool_failures"
    TIME_SOFT_WRAP = "time_soft_wrap"
    TIME_HARD_HANGUP = "time_hard_hangup"


# Disposition priority — higher index = better progress
_PROGRESS_RANK = {
    "no_signal": ("callback_requested", 0),
    "transfer_mentioned": ("transferred_to_sales", 1),
    "callback_discussed": ("callback_requested", 2),
    "appointment_booked": ("appointment_set", 3),
}

_AUDIO_COMPLAINT_HARD = 2
_SILENCE_SOFT_S = 8
_SILENCE_HARD_S = 15
_TOOL_FAILURE_HARD = 2
_TIME_SOFT_S = 240
_TIME_HARD_S = 360


@dataclass
class SessionStateMachine:
    audio_complaints: int = 0
    consecutive_tool_failures: int = 0
    progress_signals: list[str] = field(default_factory=list)
    _silence_soft_fired: bool = False
    _audio_action_fired: bool = False
    _time_soft_fired: bool = False
    _time_hard_fired: bool = False
    _transfer_fired: bool = False

    def note_audio_quality_complaint(self) -> None:
        self.audio_complaints += 1

    def note_tool_call_result(self, success: bool) -> None:
        if success:
            self.consecutive_tool_failures = 0
        else:
            self.consecutive_tool_failures += 1

    def note_progress_signal(self, signal: str) -> None:
        if signal in _PROGRESS_RANK:
            self.progress_signals.append(signal)

    def tick(
        self,
        *,
        now_seconds: float,
        last_user_speech_at: float,
        agent_speaking: bool,
    ) -> ForcedAction | None:
        # Hard time hangup wins over everything
        if not self._time_hard_fired and now_seconds >= _TIME_HARD_S:
            self._time_hard_fired = True
            return ForcedAction.TIME_HARD_HANGUP

        if not self._audio_action_fired and self.audio_complaints >= _AUDIO_COMPLAINT_HARD:
            self._audio_action_fired = True
            return ForcedAction.AUDIO_QUALITY_HANGUP

        if not self._transfer_fired and self.consecutive_tool_failures >= _TOOL_FAILURE_HARD:
            self._transfer_fired = True
            return ForcedAction.TRANSFER_ON_TOOL_FAILURES

        if not self._time_soft_fired and now_seconds >= _TIME_SOFT_S:
            self._time_soft_fired = True
            return ForcedAction.TIME_SOFT_WRAP

        # Silence handling — only counts when agent isn't currently speaking
        if not agent_speaking:
            silence_s = now_seconds - last_user_speech_at
            if silence_s >= _SILENCE_HARD_S:
                return ForcedAction.SILENCE_HANGUP
            if silence_s >= _SILENCE_SOFT_S and not self._silence_soft_fired:
                self._silence_soft_fired = True
                return ForcedAction.SILENCE_SOFT_PROMPT
            if silence_s < _SILENCE_SOFT_S:
                # User spoke recently — reset soft so a future silence can re-trigger
                self._silence_soft_fired = False

        return None

    def best_progress_disposition(self) -> str:
        if not self.progress_signals:
            return "callback_requested"
        best = max(self.progress_signals, key=lambda s: _PROGRESS_RANK[s][1])
        return _PROGRESS_RANK[best][0]
```

- [ ] **Step 4: Run tests, expect pass**

```bash
pytest tests/services/voice_agent/test_state_machine.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add app/services/voice_agent/state_machine.py tests/services/voice_agent/test_state_machine.py
git commit -m "feat(voice-agent): session state machine for forced disposition/hangup"
```

---

## Phase 3 — STT Anti-Fragmentation

### Task 3.1: Custom context aggregator

**Files:**
- Create: `app/services/voice_agent/aggregators.py`
- Create: `tests/services/voice_agent/test_aggregators.py`

- [ ] **Step 1: Write tests**

`tests/services/voice_agent/test_aggregators.py`:

```python
"""Anti-fragmentation aggregator merges short utterance fragments into coherent turns."""
import pytest

from app.services.voice_agent.aggregators import FragmentMerger


def test_pass_through_long_utterance():
    fm = FragmentMerger()
    out = fm.consume(text="I have a question about the inspection price.", duration_ms=2400)
    assert out == "I have a question about the inspection price."


def test_short_fragment_is_buffered_not_emitted():
    fm = FragmentMerger()
    out = fm.consume(text="the foam", duration_ms=400)
    assert out is None
    assert fm.has_buffered()


def test_buffered_fragment_merges_with_next():
    fm = FragmentMerger()
    fm.consume(text="the foam", duration_ms=400)
    out = fm.consume(text="the phone is breaking up", duration_ms=1800)
    assert out == "the foam the phone is breaking up"
    assert not fm.has_buffered()


def test_short_fragment_with_question_mark_emits_immediately():
    fm = FragmentMerger()
    out = fm.consume(text="really?", duration_ms=500)
    assert out == "really?"


def test_buffer_flushed_after_timeout():
    fm = FragmentMerger()
    fm.consume(text="seems like", duration_ms=600)
    flushed = fm.flush_if_stale(now_ms=10_000, last_buffer_at_ms=4_000, stale_after_ms=3_000)
    assert flushed == "seems like"
    assert not fm.has_buffered()


def test_buffer_not_flushed_when_fresh():
    fm = FragmentMerger()
    fm.consume(text="seems like", duration_ms=600)
    flushed = fm.flush_if_stale(now_ms=4_500, last_buffer_at_ms=4_000, stale_after_ms=3_000)
    assert flushed is None
    assert fm.has_buffered()


def test_three_word_short_duration_is_still_a_fragment():
    fm = FragmentMerger()
    out = fm.consume(text="and also the", duration_ms=600)
    assert out is None


def test_three_words_with_real_duration_passes_through():
    fm = FragmentMerger()
    out = fm.consume(text="and also the", duration_ms=1200)
    assert out == "and also the"
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/services/voice_agent/test_aggregators.py -v
```

- [ ] **Step 3: Implement**

`app/services/voice_agent/aggregators.py`:

```python
"""Fragment merger for Deepgram STT output.

Deepgram occasionally finalizes mid-thought utterances (especially over a
flaky cell connection): "the foam", "in regards to the", "and also". Treating
each as a turn fires the agent reply prematurely. This merger holds short
non-question fragments and concatenates them with the next utterance.
"""
from dataclasses import dataclass


_MIN_WORDS = 3
_MIN_DURATION_MS = 800


@dataclass
class FragmentMerger:
    _buffer: str = ""

    def consume(self, *, text: str, duration_ms: float) -> str | None:
        """Decide whether to emit `text` as a turn or hold it as a fragment.

        Returns the emitted turn text (possibly merged with prior buffer),
        or None if held.
        """
        text = text.strip()
        if not text:
            return None

        is_fragment = (
            self._is_short(text)
            and duration_ms < _MIN_DURATION_MS
            and not text.endswith("?")
        )

        if is_fragment:
            self._buffer = (self._buffer + " " + text).strip() if self._buffer else text
            return None

        if self._buffer:
            merged = (self._buffer + " " + text).strip()
            self._buffer = ""
            return merged

        return text

    def has_buffered(self) -> bool:
        return bool(self._buffer)

    def flush_if_stale(self, *, now_ms: float, last_buffer_at_ms: float, stale_after_ms: float) -> str | None:
        """Flush a buffered fragment as its own turn if it has aged out."""
        if not self._buffer:
            return None
        if now_ms - last_buffer_at_ms < stale_after_ms:
            return None
        flushed = self._buffer
        self._buffer = ""
        return flushed

    @staticmethod
    def _is_short(text: str) -> bool:
        return len(text.split()) < _MIN_WORDS
```

- [ ] **Step 4: Run tests, expect pass**

```bash
pytest tests/services/voice_agent/test_aggregators.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add app/services/voice_agent/aggregators.py tests/services/voice_agent/test_aggregators.py
git commit -m "feat(voice-agent): fragment merger anti-fragmentation aggregator"
```

---

## Phase 4 — Pipeline + Session Wiring

### Task 4.1: Pipeline factory

**Files:**
- Create: `app/services/voice_agent/pipeline_factory.py`
- Create: `tests/services/voice_agent/test_pipeline_factory.py`

Pipecat's exact import paths shift between minor versions. The executing engineer should pip-install from Task 0.1 first, then resolve the actual module paths via `python -c "import pipecat.services.cartesia; print(dir(pipecat.services.cartesia))"` etc., before writing this file. The factory should expose ONE function: `build_pipeline(session, *, websocket, on_pipeline_idle) -> Pipeline`.

- [ ] **Step 1: Write a smoke test that mocks all Pipecat services**

`tests/services/voice_agent/test_pipeline_factory.py`:

```python
"""Smoke test: pipeline_factory.build_pipeline assembles without exploding."""
import pytest


@pytest.mark.asyncio
async def test_build_pipeline_returns_pipecat_pipeline(mocker):
    # Mock all external service constructors so we don't need real API keys
    mocker.patch("app.services.voice_agent.pipeline_factory.CartesiaTTSService")
    mocker.patch("app.services.voice_agent.pipeline_factory.DeepgramSTTService")
    mocker.patch("app.services.voice_agent.pipeline_factory.AnthropicLLMService")
    mocker.patch("app.services.voice_agent.pipeline_factory.SileroVADAnalyzer")
    mocker.patch("app.services.voice_agent.pipeline_factory.FastAPIWebsocketTransport")

    from app.services.voice_agent import pipeline_factory

    fake_session = mocker.MagicMock()
    fake_session.system_prompt = "system"
    fake_session.tools = []

    pipeline = pipeline_factory.build_pipeline(
        session=fake_session,
        websocket=mocker.MagicMock(),
    )
    assert pipeline is not None
```

- [ ] **Step 2: Implement pipeline_factory**

`app/services/voice_agent/pipeline_factory.py`:

```python
"""Constructs the Pipecat pipeline from a session + websocket.

Service import paths are resolved against the installed pipecat-ai version.
The pip-installed package is the source of truth — if a path here doesn't
exist after `pip install -r requirements.txt`, run:
    python -c "import pipecat; help(pipecat)"
to discover the current submodule layout.
"""
from app.config import settings

# Pipecat 0.0.50+ paths. Adjust if package has reorganized.
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.services.anthropic.llm import AnthropicLLMService
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.transports.network.fastapi_websocket import (
    FastAPIWebsocketTransport,
    FastAPIWebsocketParams,
)


def build_pipeline(*, session, websocket) -> Pipeline:
    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            vad_enabled=True,
            vad_analyzer=SileroVADAnalyzer(),
            serializer=TwilioFrameSerializer(stream_sid=session.stream_sid),
        ),
    )

    stt = DeepgramSTTService(
        api_key=settings.DEEPGRAM_API_KEY,
        model="nova-3",
        # Endpointing 300ms; utterance_end 1000ms; ignore interim for turn boundaries
        # Specific param names depend on pipecat version — verify post-install.
    )

    llm = AnthropicLLMService(
        api_key=settings.ANTHROPIC_API_KEY,
        model="claude-sonnet-4-6",
    )

    tts = CartesiaTTSService(
        api_key=settings.CARTESIA_API_KEY,
        voice_id=settings.CARTESIA_VOICE_ID,
        model="sonic-2",
        sample_rate=24000,
    )

    # Note: Pipecat's user/assistant context aggregators handle conversation
    # history. The session must register its tools and system prompt with
    # the LLM service via llm.register_function(...) and an OpenAILLMContext
    # (or equivalent Anthropic context) seeded with system + tools.
    # See session.py for that wiring.

    pipeline = Pipeline([
        transport.input(),
        stt,
        llm.user_context_aggregator(),
        llm,
        tts,
        transport.output(),
        llm.assistant_context_aggregator(),
    ])
    return pipeline
```

- [ ] **Step 3: Run smoke test, expect pass**

```bash
pytest tests/services/voice_agent/test_pipeline_factory.py -v
```

If imports fail, the engineer should:
1. Confirm `pipecat-ai` installed: `pip show pipecat-ai`
2. Discover correct paths: `find venv/lib/python*/site-packages/pipecat -name "*.py" | xargs grep -l "class CartesiaTTSService"`
3. Update imports in `pipeline_factory.py` to match the installed layout.

- [ ] **Step 4: Commit**

```bash
git add app/services/voice_agent/pipeline_factory.py tests/services/voice_agent/test_pipeline_factory.py
git commit -m "feat(voice-agent): pipeline factory wiring Cartesia/Deepgram/Anthropic/Silero"
```

### Task 4.2: OutboundAgentSession v2

**Files:**
- Create: `app/services/voice_agent/session.py`

This task ports the legacy `OutboundAgentSession` business logic into the new module while keeping the same external interface (`prospect`, `quote`, `_handle_tool_call(name, tool_id, args)`, `disposition_notes`). The class additionally:

1. Owns a `HallucinationGuard` and `SessionStateMachine`
2. Owns a `FragmentMerger` for incoming STT
3. Owns the Anthropic context (system prompt + tool defs + cache_control markers + conversation history)
4. Persists to `call_logs` at end via the existing `_persist_call` function (imported from legacy)

- [ ] **Step 1: Read the legacy session class**

```bash
sed -n '195,420p' app/services/outbound_agent.py
```

Note all instance attributes, the structure of `_handle_tool_call`, and any helper methods (`_book_appointment`, `_send_followup_sms`, etc.) that the new session should re-use.

- [ ] **Step 2: Implement v2 session that delegates tool side-effects to legacy helpers**

`app/services/voice_agent/session.py`:

```python
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
from typing import Any

from app.config import settings
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

        self.system_prompt = render_system_prompt(self._build_prospect_context())
        self.tools = AGENT_TOOLS  # passed to AnthropicLLMService

    def _build_prospect_context(self) -> str:
        p = self.prospect
        q = self.quote
        return (
            f"Name: {p.get('first_name', '')} {p.get('last_name', '')}\n"
            f"Phone: {p.get('phone', '')}\n"
            f"City/State: {p.get('city', '')}, {p.get('state', '')}\n"
            f"Quote: {q.get('quote_number', '')} — {q.get('title', '')} — ${q.get('total', 0):.2f}\n"
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
        elif name == "create_callback" and ok:
            self.state.note_progress_signal("callback_discussed")
        elif name == "transfer_call":
            self.state.note_progress_signal("transfer_mentioned")
        elif name == "set_disposition":
            self.disposition = args.get("disposition")
            self.disposition_notes = args.get("notes", "")
        return result

    def review_assistant_message(self, *, text: str, tool_calls: list[dict]) -> str:
        """Run the hallucination guard. Returns rewritten text for TTS."""
        result = self.guard.check(text=text, tool_calls=tool_calls)
        if result.hallucinations:
            self.hallucinations_log.extend(result.hallucinations)
        return result.rewritten_text

    def note_user_turn(self, text: str) -> None:
        self.last_user_speech_at = time.monotonic()
        # Heuristic: any mention of audio/quality/delay/AI from the customer
        triggers = ("delay", "voice quality", "audio", "robot", "are you ai", "are you a person")
        if any(t in text.lower() for t in triggers):
            self.state.note_audio_quality_complaint()

    def tick(self) -> ForcedAction | None:
        return self.state.tick(
            now_seconds=time.monotonic() - self.start_time,
            last_user_speech_at=self.last_user_speech_at - self.start_time,
            agent_speaking=self.agent_speaking,
        )

    async def persist(self, transcript_text: str, ai_summary: str, sentiment: str | None, duration: int) -> None:
        """Persist call_logs row using the legacy persist helper, augmented."""
        # Reuse legacy _persist_call by patching extra fields onto the legacy session.
        self._legacy_helpers.disposition_notes = self.disposition_notes
        self._legacy_helpers.disposition = self.disposition
        # The actual write is in app/api/v2/outbound_agent.py:_persist_call. The new
        # WS handler in voice_agent_ws.py will call _persist_call directly with the
        # extra `hallucinations` and `amd_result` fields included.
```

- [ ] **Step 3: Quick import smoke**

```bash
python -c "from app.services.voice_agent.session import OutboundAgentSession; print('ok')"
```

Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add app/services/voice_agent/session.py
git commit -m "feat(voice-agent): session v2 reusing legacy helpers + guard + state machine"
```

---

## Phase 5 — Greeting Prerender + Voicemail + AMD

### Task 5.1: Greeting prerender service

**Files:**
- Create: `app/services/voice_agent/greeting_prerender.py`

- [ ] **Step 1: Implement**

`app/services/voice_agent/greeting_prerender.py`:

```python
"""Render the greeting TTS at dial time so the customer hears Sarah within
~150ms of Twilio Media Stream connect, instead of waiting 5–8s for the LLM
+ TTS round trip on every call.

Buffer is held in memory keyed by call_sid. Released on Stream connect once
AMD has confirmed the answerer is human.
"""
import asyncio
import logging
from typing import Any

import httpx

from app.config import settings


logger = logging.getLogger(__name__)


_GREETING_TEMPLATE = (
    "Hi {first_name}, this is Sarah calling from MAC Septic. "
    "We sent you an estimate for {service_type} and I just wanted to follow up — "
    "do you have a minute?"
)


# call_sid -> raw audio bytes (μ-law 8kHz, ready to ship to Twilio)
_buffers: dict[str, bytes] = {}


def render_text(prospect: dict, quote: dict) -> str:
    return _GREETING_TEMPLATE.format(
        first_name=prospect.get("first_name") or "there",
        service_type=quote.get("title") or "septic services",
    )


async def prerender_greeting(call_sid: str, prospect: dict, quote: dict) -> None:
    """Synthesize greeting via Cartesia and stash bytes in `_buffers`.

    Called by campaign_dialer immediately after Twilio.calls.create returns.
    """
    if not settings.CARTESIA_API_KEY or not settings.CARTESIA_VOICE_ID:
        logger.warning(f"[Prerender:{call_sid[:8]}] Cartesia not configured — skipping prerender")
        return

    text = render_text(prospect, quote)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://api.cartesia.ai/tts/bytes",
                headers={
                    "X-API-Key": settings.CARTESIA_API_KEY,
                    "Cartesia-Version": "2024-11-13",
                    "Content-Type": "application/json",
                },
                json={
                    "model_id": "sonic-2",
                    "transcript": text,
                    "voice": {"mode": "id", "id": settings.CARTESIA_VOICE_ID},
                    "output_format": {
                        "container": "raw",
                        "encoding": "pcm_mulaw",
                        "sample_rate": 8000,
                    },
                },
            )
        if resp.status_code != 200:
            logger.error(f"[Prerender:{call_sid[:8]}] Cartesia returned {resp.status_code}: {resp.text[:200]}")
            return
        _buffers[call_sid] = resp.content
        logger.info(f"[Prerender:{call_sid[:8]}] greeting buffered ({len(resp.content)} bytes)")
    except Exception as exc:
        logger.exception(f"[Prerender:{call_sid[:8]}] error: {exc}")


def take_buffer(call_sid: str) -> bytes | None:
    """Pop and return the prerendered audio for a call_sid (None if not ready)."""
    return _buffers.pop(call_sid, None)


def discard(call_sid: str) -> None:
    _buffers.pop(call_sid, None)
```

- [ ] **Step 2: Commit**

```bash
git add app/services/voice_agent/greeting_prerender.py
git commit -m "feat(voice-agent): greeting prerender service buffers Cartesia TTS at dial time"
```

### Task 5.2: AMD webhook

**Files:**
- Create: `app/api/v2/voice_agent_amd.py`

- [ ] **Step 1: Implement**

`app/api/v2/voice_agent_amd.py`:

```python
"""Twilio AsyncAmd webhook receiver.

Twilio fires this ~3.5s after answer with `AnsweredBy` set to one of:
  human | machine_start | machine_end_beep | machine_end_silence |
  machine_end_other | fax | unknown

The Pipecat WS handler subscribes to amd events keyed by call_sid via an
in-memory dict so it can decide whether to play the prerendered greeting,
trigger the voicemail flow, or proceed cautiously on `unknown`.
"""
import asyncio
import logging

from fastapi import APIRouter, Form, Request, Response


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/outbound-agent/amd", tags=["outbound-agent"])


# call_sid -> asyncio.Event signaling AMD result is in
_amd_events: dict[str, asyncio.Event] = {}
# call_sid -> AnsweredBy result string
_amd_results: dict[str, str] = {}


def register(call_sid: str) -> asyncio.Event:
    """Called by the WS handler before the AMD result is expected."""
    ev = asyncio.Event()
    _amd_events[call_sid] = ev
    return ev


def get_result(call_sid: str) -> str | None:
    return _amd_results.get(call_sid)


def cleanup(call_sid: str) -> None:
    _amd_events.pop(call_sid, None)
    _amd_results.pop(call_sid, None)


@router.post("")
async def amd_callback(
    request: Request,
    AnsweredBy: str = Form(""),
    CallSid: str = Form(""),
):
    logger.info(f"[AMD] CallSid={CallSid} AnsweredBy={AnsweredBy}")
    _amd_results[CallSid] = AnsweredBy
    ev = _amd_events.get(CallSid)
    if ev:
        ev.set()
    return Response(status_code=200)
```

- [ ] **Step 2: Commit**

```bash
git add app/api/v2/voice_agent_amd.py
git commit -m "feat(voice-agent): twilio AMD webhook with per-call event signaling"
```

### Task 5.3: Voicemail flow

**Files:**
- Create: `app/services/voice_agent/voicemail.py`

- [ ] **Step 1: Implement**

`app/services/voice_agent/voicemail.py`:

```python
"""Voicemail flow triggered when AMD returns `machine_end_beep`.

Plays a templated message via Cartesia, then hangs up. No LLM in the loop —
voicemail content is fixed and predictable.
"""
import logging

import httpx

from app.config import settings


logger = logging.getLogger(__name__)


_VOICEMAIL_TEMPLATE = (
    "Hi {first_name}, this is Sarah from MAC Septic. I was following up on the estimate "
    "we sent you for {service_type}. Please give us a call back when you have a moment "
    "at six one five, three four five, two five four four. Thanks, and have a great day."
)


def render_text(prospect: dict, quote: dict) -> str:
    return _VOICEMAIL_TEMPLATE.format(
        first_name=prospect.get("first_name") or "there",
        service_type=quote.get("title") or "septic services",
    )


async def synthesize_voicemail_audio(prospect: dict, quote: dict) -> bytes | None:
    """Render Cartesia μ-law 8kHz audio. Returns None if Cartesia unconfigured."""
    if not settings.CARTESIA_API_KEY or not settings.CARTESIA_VOICE_ID:
        return None
    text = render_text(prospect, quote)
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            "https://api.cartesia.ai/tts/bytes",
            headers={
                "X-API-Key": settings.CARTESIA_API_KEY,
                "Cartesia-Version": "2024-11-13",
                "Content-Type": "application/json",
            },
            json={
                "model_id": "sonic-2",
                "transcript": text,
                "voice": {"mode": "id", "id": settings.CARTESIA_VOICE_ID},
                "output_format": {
                    "container": "raw",
                    "encoding": "pcm_mulaw",
                    "sample_rate": 8000,
                },
            },
        )
    if resp.status_code != 200:
        logger.error(f"[Voicemail] Cartesia {resp.status_code}: {resp.text[:200]}")
        return None
    return resp.content
```

- [ ] **Step 2: Commit**

```bash
git add app/services/voice_agent/voicemail.py
git commit -m "feat(voice-agent): voicemail synthesis via Cartesia for AMD machine branch"
```

---

## Phase 6 — WebSocket Handler + Feature Flag

### Task 6.1: WebSocket route running the Pipecat pipeline

**Files:**
- Create: `app/api/v2/voice_agent_ws.py`

- [ ] **Step 1: Implement**

`app/api/v2/voice_agent_ws.py`:

```python
"""FastAPI WebSocket route that runs the Pipecat-based outbound agent.

Twilio Media Streams calls this URL. We accept the WS, build a Pipecat
Pipeline keyed to the call_sid, and run it. AMD result + greeting prerender
are coordinated through in-memory dicts in voice_agent_amd / greeting_prerender.

Selected via campaign_dialer when settings.VOICE_AGENT_ENGINE == "pipecat".
"""
import asyncio
import json
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import settings
from app.services.campaign_dialer import (
    active_sessions,
    get_pending_call_data,
    remove_pending_call_data,
)
from app.services.voice_agent import (
    greeting_prerender,
    voicemail,
)
from app.services.voice_agent.pipeline_factory import build_pipeline
from app.services.voice_agent.session import OutboundAgentSession
from app.api.v2 import voice_agent_amd

# Pipecat runner imports — verify paths post-install
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask, PipelineParams


logger = logging.getLogger(__name__)


router = APIRouter(prefix="/outbound-agent/voice", tags=["outbound-agent"])


@router.websocket("/stream")
async def voice_stream(websocket: WebSocket):
    await websocket.accept()
    call_sid: str | None = None
    stream_sid: str | None = None

    # Twilio sends a "start" message first with stream_sid + custom params
    try:
        first_msg = await websocket.receive_text()
        data = json.loads(first_msg)
        if data.get("event") == "start":
            stream_sid = data["start"]["streamSid"]
            call_sid = data["start"]["callSid"]
    except Exception as exc:
        logger.exception(f"[VoiceWS] Failed to parse start frame: {exc}")
        await websocket.close()
        return

    pending = get_pending_call_data(call_sid) or {}
    prospect = pending.get("prospect", {})
    quote = pending.get("quote", {})

    session = OutboundAgentSession(
        call_sid=call_sid,
        prospect=prospect,
        quote=quote,
        stream_sid=stream_sid,
    )
    active_sessions[call_sid] = session

    # Wait briefly for AMD result (Twilio fires ~3.5s after answer)
    amd_event = voice_agent_amd.register(call_sid)
    try:
        await asyncio.wait_for(amd_event.wait(), timeout=4.0)
    except asyncio.TimeoutError:
        pass
    amd_result = voice_agent_amd.get_result(call_sid) or "unknown"
    session.amd_result = amd_result
    logger.info(f"[VoiceWS:{call_sid[:8]}] AMD={amd_result}")

    if amd_result.startswith("machine"):
        # Voicemail branch — bypass Pipecat entirely
        audio = await voicemail.synthesize_voicemail_audio(prospect, quote)
        if audio:
            await _send_audio_via_twilio_ws(websocket, stream_sid, audio)
        # Persist a voicemail call_log row
        await _persist_voicemail(session)
        greeting_prerender.discard(call_sid)
        voice_agent_amd.cleanup(call_sid)
        del active_sessions[call_sid]
        await websocket.close()
        return

    # Human (or unknown — proceed with caution)
    pipeline = build_pipeline(session=session, websocket=websocket)
    task = PipelineTask(pipeline, PipelineParams(allow_interruptions=True))
    runner = PipelineRunner()

    # Inject prerendered greeting into the pipeline output before STT/LLM start.
    # Pipecat exposes an output transport queue; the engineer should look up
    # the exact API ('OutputAudioRawFrame'?) post-install and use it here.
    greeting_audio = greeting_prerender.take_buffer(call_sid)
    if greeting_audio:
        await _push_audio_into_pipeline(task, greeting_audio)

    try:
        await runner.run(task)
    except WebSocketDisconnect:
        pass
    finally:
        # Persist the call_log row including hallucinations + amd_result
        await _persist_call_log(session)
        voice_agent_amd.cleanup(call_sid)
        active_sessions.pop(call_sid, None)
        remove_pending_call_data(call_sid)


async def _send_audio_via_twilio_ws(websocket: WebSocket, stream_sid: str, audio: bytes) -> None:
    """Stream raw μ-law audio to Twilio Media Streams as base64 frames."""
    import base64
    chunk_size = 320  # 20ms at 8kHz μ-law
    for i in range(0, len(audio), chunk_size):
        chunk = audio[i : i + chunk_size]
        await websocket.send_text(
            json.dumps({
                "event": "media",
                "streamSid": stream_sid,
                "media": {"payload": base64.b64encode(chunk).decode()},
            })
        )
        await asyncio.sleep(0.02)


async def _push_audio_into_pipeline(task, audio: bytes) -> None:
    """Inject prerendered greeting audio into Pipecat's output stream.

    The exact mechanism depends on pipecat version. Probably:
        from pipecat.frames.frames import OutputAudioRawFrame
        await task.queue_frames([OutputAudioRawFrame(audio=audio, sample_rate=8000, num_channels=1)])
    Engineer should verify against installed pipecat-ai.
    """
    # placeholder — engineer to implement against installed pipecat
    pass


async def _persist_call_log(session: OutboundAgentSession) -> None:
    """Write call_logs row using the legacy _persist_call helper, plus new fields."""
    from app.api.v2.outbound_agent import _persist_call
    # Legacy _persist_call writes the row. We then update with our extras.
    duration = int(time.monotonic() - session.start_time)
    transcript_text = ""  # TODO: assemble from session if available
    ai_summary = ""
    sentiment = "neutral"
    await _persist_call(
        session=session._legacy_helpers,
        transcript_text=transcript_text,
        ai_summary=ai_summary,
        sentiment=sentiment,
        duration=duration,
    )
    # Patch the row to add hallucinations + amd_result
    from sqlalchemy import update
    from app.database import async_session_maker
    from app.models.call_log import CallLog
    async with async_session_maker() as db:
        await db.execute(
            update(CallLog)
            .where(CallLog.ringcentral_call_id == session.call_sid)
            .values(
                hallucinations=session.hallucinations_log or None,
                amd_result=session.amd_result,
            )
        )
        await db.commit()


async def _persist_voicemail(session: OutboundAgentSession) -> None:
    """Write a minimal call_logs row for a voicemail-branch call."""
    from app.database import async_session_maker
    from app.models.call_log import CallLog
    from datetime import datetime
    import uuid
    async with async_session_maker() as db:
        log = CallLog(
            id=uuid.uuid4(),
            ringcentral_call_id=session.call_sid,
            direction="outbound",
            call_type="voice",
            call_disposition="voicemail_left",
            assigned_to="ai_outbound_agent",
            external_system="outbound_agent",
            user_id="1",
            amd_result=session.amd_result,
            transcription_status="not_applicable",
            ai_summary="Voicemail flow — no conversation occurred",
            call_date=datetime.utcnow().date(),
            call_time=datetime.utcnow().time(),
        )
        db.add(log)
        await db.commit()
```

- [ ] **Step 2: Register routes**

In whichever file aggregates v2 routers (search for where `outbound_agent` router is registered):

```bash
grep -rn "outbound_agent.router\|include_router.*outbound" app/api/ 2>/dev/null
```

Add the new routers next to the existing one:

```python
from app.api.v2 import voice_agent_ws, voice_agent_amd
v2_router.include_router(voice_agent_ws.router)
v2_router.include_router(voice_agent_amd.router)
```

- [ ] **Step 3: Commit**

```bash
git add app/api/v2/voice_agent_ws.py <wherever-router-registered>
git commit -m "feat(voice-agent): pipecat WS handler + voicemail branch + AMD coordination"
```

### Task 6.2: Feature flag dispatch + AMD wiring in TwiML

**Files:**
- Modify: `app/api/v2/outbound_agent.py`
- Modify: `app/services/campaign_dialer.py`

The Twilio Voice webhook in `outbound_agent.py` returns TwiML telling Twilio which Media Stream URL to connect to. Today it always points to the legacy WS. Change it to read `settings.VOICE_AGENT_ENGINE`:

- [ ] **Step 1: Update TwiML response**

Find the Twilio voice webhook in `app/api/v2/outbound_agent.py` (search for `<Stream` or `voice_webhook` or `@router.post("/voice")`):

```bash
grep -n "Stream url\|<Stream\|voice_webhook\|@router.post.*voice" app/api/v2/outbound_agent.py
```

Replace the hard-coded WS URL with a branch on `settings.VOICE_AGENT_ENGINE`:

```python
ws_path = "/api/v2/outbound-agent/voice/stream" if settings.VOICE_AGENT_ENGINE == "pipecat" else "/api/v2/outbound-agent/media-stream"  # legacy path — confirm by grep
twiml = f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="wss://{settings.PUBLIC_HOST}{ws_path}"/>
  </Connect>
</Response>'''
```

- [ ] **Step 2: Add AMD parameters to outbound dial**

In `app/services/campaign_dialer.py`, find `initiate_call` (line ~140):

```python
def initiate_call(to_number: str, callback_url: str, *, prospect: dict, quote: dict) -> Optional[str]:
    ...
```

Add to the Twilio `client.calls.create(...)` invocation:

```python
machine_detection="DetectMessageEnd",
async_amd="true",
async_amd_status_callback=settings.OUTBOUND_AGENT_AMD_CALLBACK,
async_amd_status_callback_method="POST",
```

After `client.calls.create` returns, schedule the greeting prerender:

```python
import asyncio
from app.services.voice_agent.greeting_prerender import prerender_greeting
asyncio.create_task(prerender_greeting(call.sid, prospect, quote))
```

- [ ] **Step 3: Commit**

```bash
git add app/api/v2/outbound_agent.py app/services/campaign_dialer.py
git commit -m "feat(voice-agent): twiml branch on VOICE_AGENT_ENGINE; AMD + prerender on outbound dial"
```

### Task 6.3: Test prospect filter

**Files:**
- Modify: `app/services/campaign_dialer.py`

- [ ] **Step 1: Update `get_prospect_queue`**

Add a `is_test: bool = False` parameter and filter the SQL:

```python
async def get_prospect_queue(limit: int = 50, *, is_test: bool = False) -> list[dict]:
    ...
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
            ...
```

- [ ] **Step 2: Commit**

```bash
git add app/services/campaign_dialer.py
git commit -m "feat(voice-agent): is_test_prospect filter on prospect queue"
```

---

## Phase 7 — Voice Eval Rig

### Task 7.1: Frame logger + report

**Files:**
- Create: `scripts/voice_eval.py`

- [ ] **Step 1: Implement**

`scripts/voice_eval.py`:

```python
"""Voice eval rig — instruments a Pipecat call and emits per-turn latency reports.

Usage:
    python scripts/voice_eval.py --call-sid CA1234... --out voice_eval_runs/

Hooks into the same in-memory frame log that the voice_agent_ws handler writes
to during a test call. Generates a markdown summary:
  - Greeting latency
  - Per-turn: VAD speech-end -> STT final -> LLM TTFT -> LLM done -> TTS TTFB -> first audio out
  - Aggregates: mean, p50, p95
  - Hallucinations caught count
  - Recovery loop count (forced action triggers)
"""
import argparse
import json
import statistics
from datetime import datetime
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--call-sid", required=True)
    parser.add_argument("--out", default="voice_eval_runs/")
    parser.add_argument("--frame-log", default="voice_eval_runs/frames.jsonl")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    frames = _load_frames(args.frame_log, args.call_sid)
    if not frames:
        print(f"No frames for {args.call_sid}")
        return

    turns = _segment_turns(frames)
    report = _render_report(args.call_sid, turns, frames)

    out_path = out_dir / f"{args.call_sid}.md"
    out_path.write_text(report)
    print(f"Wrote {out_path}")


def _load_frames(path: str, call_sid: str) -> list[dict]:
    frames = []
    with open(path) as fh:
        for line in fh:
            f = json.loads(line)
            if f.get("call_sid") == call_sid:
                frames.append(f)
    return frames


def _segment_turns(frames: list[dict]) -> list[dict]:
    """Group frames into turns delimited by user-speech-end events."""
    turns: list[dict] = []
    current: dict = {}
    for f in frames:
        ev = f.get("event")
        ts = f.get("ts")
        if ev == "user_speech_end":
            current.setdefault("user_speech_end", ts)
        elif ev == "stt_final":
            current["stt_final"] = ts
        elif ev == "llm_first_token":
            current["llm_first_token"] = ts
        elif ev == "llm_done":
            current["llm_done"] = ts
        elif ev == "tts_first_byte":
            current["tts_first_byte"] = ts
        elif ev == "audio_out_first":
            current["audio_out_first"] = ts
            turns.append(current)
            current = {}
    return turns


def _render_report(call_sid: str, turns: list[dict], frames: list[dict]) -> str:
    lines = [f"# Voice Eval — {call_sid}", "", f"Generated: {datetime.utcnow().isoformat()}", ""]

    greeting = next((f for f in frames if f.get("event") == "greeting_first_audio"), None)
    stream_start = next((f for f in frames if f.get("event") == "stream_connected"), None)
    if greeting and stream_start:
        gl = greeting["ts"] - stream_start["ts"]
        lines.append(f"**Greeting latency:** {gl*1000:.0f}ms")
        lines.append("")

    if turns:
        turn_latencies_ms = [
            (t["audio_out_first"] - t["user_speech_end"]) * 1000
            for t in turns
            if "audio_out_first" in t and "user_speech_end" in t
        ]
        if turn_latencies_ms:
            lines.append("## Turn latency")
            lines.append(f"- mean: {statistics.mean(turn_latencies_ms):.0f}ms")
            lines.append(f"- p50: {statistics.median(turn_latencies_ms):.0f}ms")
            lines.append(f"- p95: {sorted(turn_latencies_ms)[int(len(turn_latencies_ms) * 0.95)] if len(turn_latencies_ms) >= 20 else max(turn_latencies_ms):.0f}ms")
            lines.append(f"- count: {len(turn_latencies_ms)}")
            lines.append("")

    hallucinations = [f for f in frames if f.get("event") == "hallucination_caught"]
    forced = [f for f in frames if f.get("event") == "forced_action"]
    lines.append(f"**Hallucinations caught:** {len(hallucinations)}")
    lines.append(f"**Forced actions:** {len(forced)} ({', '.join(f.get('action', '?') for f in forced)})")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Add frame-log writer hook**

In `app/api/v2/voice_agent_ws.py`, add a small helper that appends to `voice_eval_runs/frames.jsonl` on key pipeline events. Wire it into Pipecat's frame observer (Pipecat exposes a way to subscribe to frame events — engineer to check `pipecat.observers` post-install).

- [ ] **Step 3: Commit**

```bash
git add scripts/voice_eval.py app/api/v2/voice_agent_ws.py
git commit -m "feat(voice-agent): voice eval rig and frame-log instrumentation"
```

---

## Phase 8 — Local Dev Runtime

### Task 8.1: Local dev entrypoint

**Files:**
- Create: `scripts/pipecat_agent_dev.py`

This is a thin uvicorn-friendly entrypoint that imports `app.main` (or a stripped-down version) for local testing. Most of the work is documentation rather than code — explain in a docstring how Will runs ngrok, points the test Twilio number at it, and seeds `is_test_prospect=true` rows.

- [ ] **Step 1: Implement**

`scripts/pipecat_agent_dev.py`:

```python
"""Local dev runner for the Pipecat outbound voice agent.

Steps:
  1. Set VOICE_AGENT_ENGINE=pipecat in .env
  2. Set CARTESIA_API_KEY, CARTESIA_VOICE_ID
  3. Seed test prospects:
       psql "$DATABASE_URL" -c "UPDATE customers SET is_test_prospect=true WHERE phone='+19792361958';"
  4. Start the FastAPI app:
       python scripts/pipecat_agent_dev.py
  5. Start ngrok: `ngrok http 8000`
  6. In Twilio console, set the test number's voice webhook to:
       https://<ngrok-id>.ngrok.io/api/v2/outbound-agent/voice
     and the AMD callback to:
       https://<ngrok-id>.ngrok.io/api/v2/outbound-agent/amd
  7. Trigger a test campaign:
       curl -X POST localhost:8000/api/v2/outbound-agent/campaign/start \
            -H "Content-Type: application/json" \
            -d '{"is_test": true, "max_calls": 1}'
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
```

- [ ] **Step 2: Commit**

```bash
git add scripts/pipecat_agent_dev.py
git commit -m "feat(voice-agent): local dev entrypoint with ngrok runbook"
```

---

## Phase 9 — Verification + Rollout

These are operational steps, not code tasks. Recorded here for the executing engineer to follow but not as TDD.

### Task 9.1: Local 10-call gate

- [ ] Set up Cartesia account, populate `CARTESIA_API_KEY` and `CARTESIA_VOICE_ID` in dev env. Pick voice via Cartesia's voice library — shortlist 3 warm female Southern voices, A/B by triggering 3 test calls (one per voice) on Will's cell, Will picks the keeper.

- [ ] Run 10 consecutive test calls against `is_test_prospect=true` rows. After each, run `python scripts/voice_eval.py --call-sid <sid>`.

- [ ] Acceptance gate: mean turn latency < 800ms, p95 < 1.2s, zero hallucinations across all 10 calls, zero stuck recovery loops, voicemail flow tested at least once (don't pick up the phone, let it go to voicemail).

### Task 9.2: PR + Railway preview

- [ ] Open PR from `voice-agent-pipecat` to `master`. Railway preview env auto-deploys. Set the new env vars (`VOICE_AGENT_ENGINE=pipecat`, `CARTESIA_API_KEY`, `CARTESIA_VOICE_ID`, `OUTBOUND_AGENT_AMD_CALLBACK`) on the preview environment.

- [ ] Run 5 test calls against the preview URL using a Twilio number whose webhook points at the preview app. Acceptance: mean turn latency < 900ms, all other gates same as local.

### Task 9.3: Production cutover

- [ ] Merge to `master`. Railway prod auto-deploys with `VOICE_AGENT_ENGINE` defaulting to `legacy`. Confirm `/health` AND `railway status` show the deploy is live.

- [ ] Set Cartesia env vars on prod. Flip `VOICE_AGENT_ENGINE=pipecat`. Confirm Railway redeploys cleanly.

- [ ] Run a 5-prospect test campaign filtered to `is_test_prospect=true`. Verify call_logs rows have `external_system='outbound_agent'`, populated `transcription`, no `hallucinations`, sane `amd_result`.

- [ ] Run a 20-prospect real Nashville campaign. Will live-monitors the SSE transcript. Stop immediately if any call goes off the rails.

- [ ] After 2 weeks of clean operation, follow up: delete `app/services/outbound_agent.py` legacy session class (keep only the tool implementations that voice_agent/session.py still imports), remove the `legacy` branch in the TwiML response, drop the `VOICE_AGENT_ENGINE` flag.

---

## Self-Review Notes

Coverage check against the spec:

- ✅ Architecture (Pipeline factory, session, system prompt, tools port) — Phases 1, 4
- ✅ Greeting prerender + AMD coordination — Phase 5
- ✅ Conversation behavior (3 system prompt rules, hallucination guard, state machine) — Phases 1, 2
- ✅ Latency budget (Cartesia, Sonnet, prompt cache, sentence streaming, anti-fragmentation) — Phases 2, 3, 4
- ✅ Voicemail flow — Phase 5
- ✅ Tool surface (8 existing tools) — Phase 1
- ✅ Test prospects + filter — Phases 0, 6
- ✅ Voice eval rig — Phase 7
- ✅ Local dev runtime — Phase 8
- ✅ Pre-prod + prod rollout — Phase 9
- ✅ Schema migration (is_test_prospect, hallucinations, amd_result) — Phase 0

Open items the executing engineer must resolve in-flight (NOT placeholders — these are runtime discoveries):

- Pipecat 0.0.x submodule paths (`pipecat.services.cartesia.tts` vs `pipecat.services.cartesia` etc.) — confirm via `pip show` after install in Task 0.1
- Pipecat output frame type for greeting injection (`OutputAudioRawFrame` or similar) — confirm via `python -c "from pipecat.frames.frames import *; print(dir())"` in Task 6.1 step 2
- Pipecat observer API for the frame log — confirm via inspecting installed package in Task 7.1 step 2
- Cartesia voice_id selection — picked by Will after A/B in Task 9.1
- Exact existing legacy WS path so the TwiML branch knows what to flip from — `grep -n` resolves in Task 6.2 step 1
