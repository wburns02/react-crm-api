"""AI Interaction Analyzer worker — orchestrates the per-interaction pipeline.

Entry point: ``process_interaction(source_id, channel)``.

Per-channel flow:
  - call/voicemail: download recording → Deepgram transcribe → triage
  - sms/chat:        triage on stored content
  - email:           fetch full body via MS365 Graph → triage

Always after triage:
  - Persist analysis to ``customer_interactions`` and denormalize key fields
    (intent, sentiment, hot_lead_score, urgency, do_not_contact)
  - Write an ``InteractionAnalysisRun`` row (audit + cost ledger)
  - If ``hot_lead_score >= 70``: run the reply tier (Sonnet 4.6) and persist
    ``suggested_reply``
  - If ``do_not_contact_signal=True``: invoke ``suppression.suppress``
  - Persist the ``action_items`` array as ``InteractionActionItem`` rows
  - For ``call`` channel: denormalize back to ``call_logs`` so the existing
    Call Intelligence dashboard keeps working
  - For ``hot_lead_score >= 70`` AND a phone number is known: push to Dannia's
    outbound campaign queue

Idempotent at the source-row level: a CustomerInteraction row keyed by
``external_id`` is upserted; a re-run on a row that already has analysis
(within the last hour) skips early.

Retry: Anthropic 429s and 529s are retried with exponential backoff
(2s/4s/8s, max 3 attempts). On final failure an InteractionAnalysisRun
with status="error" is persisted.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable, Awaitable
from uuid import UUID

import httpx

from sqlalchemy import select

from app.config import settings
from app.database import async_session_maker
from app.models.call_log import CallLog
from app.models.customer import Customer
from app.models.customer_interaction import (
    CustomerInteraction,
    InteractionActionItem,
    InteractionAnalysisRun,
)
from app.models.inbound_email import InboundEmail
from app.models.message import Message
from app.models.outbound_campaign import OutboundCampaignContact
from app.services.ai import budget as budget_module
from app.services.ai import suppression as suppression_module
from app.services.ai.anthropic_client import (
    AnthropicClient,
    REPLY_MODEL,
    ReplyResult,
    TRIAGE_MODEL,
    TriageResult,
)
from app.services.ai.deepgram_client import (
    DeepgramTranscriptionClient,
    TranscriptResult,
)
from app.services.ai.prompts import (
    REPLY_VERSION,
    TRIAGE_VERSION,
    render_reply_user_message,
    render_triage_user_message,
)
from app.services.ms365_email_service import MS365EmailService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
HOT_LEAD_THRESHOLD = 70
ANALYSIS_FRESH_WINDOW = timedelta(hours=1)
RETRY_MAX_ATTEMPTS = 3
RETRY_BASE_DELAY_SECONDS = 2.0


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
async def process_interaction(source_id: UUID, channel: str) -> None:
    """Main worker entry. Pulls source row, runs analysis, persists results.

    Idempotent: re-running on a recently-analyzed CustomerInteraction is a no-op.
    Errors are logged + dead-lettered into ``interaction_analysis_runs``;
    they never bubble back to the caller.
    """
    channel = (channel or "").lower()
    logger.info(
        "AI worker start: channel=%s source_id=%s", channel, source_id
    )

    async with async_session_maker() as db:
        try:
            # 1. Build/load the customer_interactions row -------------------
            built = await _build_interaction(db, source_id, channel)
            if built is None:
                logger.warning(
                    "AI worker: source row not found channel=%s id=%s — skipping",
                    channel,
                    source_id,
                )
                return
            interaction, customer, source_row = built

            # 2. Idempotency: skip if recent analysis exists ---------------
            if _has_fresh_analysis(interaction):
                logger.info(
                    "AI worker: interaction %s already analyzed within %s — skipping",
                    interaction.id,
                    ANALYSIS_FRESH_WINDOW,
                )
                return

            # 3. Budget check ---------------------------------------------
            paused, today_spend = await budget_module.is_paused(db)
            if paused:
                cap = budget_module.get_cap_usd()
                logger.warning(
                    "AI worker: budget cap hit (spend=%s, cap=%s) — pausing",
                    today_spend,
                    cap,
                )
                # Best-effort alert; don't crash worker on email failure.
                try:
                    await budget_module.alert_will(today_spend, cap)
                except Exception:  # noqa: BLE001
                    logger.exception("Budget alert email failed")
                return

            # 4. Optional transcription (call/voicemail with audio) -------
            await _maybe_transcribe(db, interaction, source_row, channel)

            # 5. Triage ----------------------------------------------------
            triage_payload = _build_triage_payload(interaction, customer)
            try:
                triage = await _with_retry(
                    _call_triage_once, triage_payload
                )
            except Exception as exc:  # noqa: BLE001
                await _record_run_error(db, interaction, "triage", TRIAGE_MODEL, TRIAGE_VERSION, exc)
                await db.commit()
                return

            await _persist_triage(db, interaction, triage)

            # 6. Reply tier (only if hot) ---------------------------------
            triage_data = triage.tool_input if triage and triage.tool_input else {}
            score = int(triage_data.get("hot_lead_score") or 0)
            do_not_contact = bool(triage_data.get("do_not_contact_signal"))

            if score >= HOT_LEAD_THRESHOLD and not do_not_contact:
                try:
                    reply = await _with_retry(
                        _call_reply_once, triage_payload, triage_data
                    )
                    await _persist_reply(db, interaction, reply)
                except Exception as exc:  # noqa: BLE001
                    await _record_run_error(
                        db, interaction, "reply", REPLY_MODEL, REPLY_VERSION, exc
                    )

            # 7. Suppression ----------------------------------------------
            if do_not_contact:
                try:
                    await suppression_module.suppress(db, interaction, customer)
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "Suppression failed for interaction %s", interaction.id
                    )

            # 8. Action items ---------------------------------------------
            await _persist_action_items(db, interaction, triage_data)

            # 9. Push to Dannia's outbound queue (hot + phone) ------------
            if score >= HOT_LEAD_THRESHOLD and not do_not_contact:
                try:
                    await _push_to_outbound_queue(db, interaction, customer)
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "Outbound queue push failed for interaction %s",
                        interaction.id,
                    )

            # 10. Denormalize triage onto call_logs (call channel only) ---
            if channel in ("call", "voicemail") and isinstance(source_row, CallLog):
                _denormalize_to_call_log(source_row, interaction, triage_data)

            await db.commit()
            logger.info(
                "AI worker done: interaction=%s score=%d intent=%s",
                interaction.id,
                score,
                triage_data.get("intent"),
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "AI worker fatal error channel=%s source_id=%s",
                channel,
                source_id,
            )
            try:
                await db.rollback()
            except Exception:  # noqa: BLE001
                pass


# ---------------------------------------------------------------------------
# Build / load the customer_interactions row
# ---------------------------------------------------------------------------
async def _build_interaction(
    db, source_id: UUID, channel: str
) -> tuple[CustomerInteraction, Customer | None, Any] | None:
    """Resolve the source row and return (interaction, customer, source_row).

    Idempotent: if a CustomerInteraction with the source's external_id
    already exists, it is loaded; otherwise it is created (without commit).
    """
    if channel in ("call", "voicemail"):
        source = await db.get(CallLog, source_id)
        if source is None:
            return None
        external_id, factory = _interaction_from_call(source)
    elif channel == "sms":
        source = await db.get(Message, source_id)
        if source is None:
            return None
        external_id, factory = _interaction_from_sms(source)
    elif channel == "email":
        source = await db.get(InboundEmail, source_id)
        if source is None:
            return None
        external_id, factory = await _interaction_from_email(source)
    elif channel == "chat":
        source = await db.get(Message, source_id)
        if source is None:
            return None
        external_id, factory = _interaction_from_chat(source)
    else:
        logger.warning("Unknown channel: %s", channel)
        return None

    # Idempotent fetch by external_id
    existing = (
        await db.execute(
            select(CustomerInteraction).where(
                CustomerInteraction.external_id == external_id
            )
        )
    ).scalars().first()

    if existing is not None:
        interaction = existing
    else:
        interaction = factory()
        db.add(interaction)
        await db.flush()  # need interaction.id for FK rows later

    customer = None
    if interaction.customer_id:
        customer = await db.get(Customer, interaction.customer_id)

    return interaction, customer, source


def _interaction_from_call(call: CallLog) -> tuple[str, Callable[[], CustomerInteraction]]:
    """Return (external_id, factory) for a call log row."""
    external_id = call.ringcentral_call_id or f"call:{call.id}"
    provider = (
        "ringcentral"
        if (call.external_system or "").lower() == "ringcentral"
        else "twilio"
    )
    direction = (call.direction or "inbound").lower()
    if direction not in ("inbound", "outbound"):
        direction = "inbound"

    occurred_at = call.start_time or call.created_at or datetime.now(timezone.utc)
    if isinstance(occurred_at, datetime) and occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)

    def factory() -> CustomerInteraction:
        return CustomerInteraction(
            customer_id=call.customer_id,
            external_id=external_id,
            channel="call",
            direction=direction,
            provider=provider,
            occurred_at=occurred_at,
            duration_seconds=call.duration_seconds,
            from_address=call.caller_number or "",
            to_address=call.called_number or "",
            subject=None,
            content=call.transcription or "",
            content_uri=call.recording_url,
            raw_payload={},
        )

    return external_id, factory


def _interaction_from_sms(msg: Message) -> tuple[str, Callable[[], CustomerInteraction]]:
    external_id = msg.external_id or f"sms:{msg.id}"
    provider = "twilio"
    if external_id and not str(external_id).startswith("SM"):
        # RC SMS IDs are typically numeric or alpha; Twilio is "SM..."
        # Best-effort heuristic.
        if not re.match(r"^SM[A-Za-z0-9]+$", str(external_id)):
            provider = "ringcentral"

    direction = (msg.direction.value if hasattr(msg.direction, "value") else str(msg.direction or "inbound")).lower()
    if direction not in ("inbound", "outbound"):
        direction = "inbound"

    occurred_at = msg.created_at or datetime.now(timezone.utc)
    if isinstance(occurred_at, datetime) and occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)

    def factory() -> CustomerInteraction:
        return CustomerInteraction(
            customer_id=msg.customer_id,
            external_id=external_id,
            channel="sms",
            direction=direction,
            provider=provider,
            occurred_at=occurred_at,
            duration_seconds=None,
            from_address=msg.from_number or msg.from_email or "",
            to_address=msg.to_number or msg.to_email or "",
            subject=None,
            content=msg.content or "",
            content_uri=None,
            raw_payload={},
        )

    return external_id, factory


async def _interaction_from_email(email: InboundEmail) -> tuple[str, Callable[[], CustomerInteraction]]:
    """Build an interaction row from an InboundEmail; fetches the full body."""
    external_id = email.message_id or f"email:{email.id}"

    body_text = email.body_preview or ""
    try:
        msg_data = await MS365EmailService.get_message_by_id(email.message_id)
    except Exception:  # noqa: BLE001
        msg_data = None
        logger.exception(
            "MS365 get_message_by_id failed for email %s", email.id
        )
    if msg_data:
        body = msg_data.get("body") or {}
        content_text = body.get("content") if isinstance(body, dict) else None
        if content_text:
            body_text = content_text

    occurred_at = email.received_at or email.created_at or datetime.now(timezone.utc)
    if isinstance(occurred_at, datetime) and occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)

    to_address = settings.MS365_MONITORED_MAILBOX or "inbox@macseptic.com"

    def factory() -> CustomerInteraction:
        return CustomerInteraction(
            customer_id=email.customer_id,
            external_id=external_id,
            channel="email",
            direction="inbound",
            provider="microsoft365",
            occurred_at=occurred_at,
            duration_seconds=None,
            from_address=(email.sender_email or "").lower(),
            to_address=to_address,
            subject=email.subject,
            content=body_text or "",
            content_uri=None,
            raw_payload={},
        )

    return external_id, factory


def _interaction_from_chat(msg: Message) -> tuple[str, Callable[[], CustomerInteraction]]:
    external_id = msg.external_id or f"chat:{msg.id}"
    direction = (msg.direction.value if hasattr(msg.direction, "value") else str(msg.direction or "inbound")).lower()
    if direction not in ("inbound", "outbound"):
        direction = "inbound"

    occurred_at = msg.created_at or datetime.now(timezone.utc)
    if isinstance(occurred_at, datetime) and occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)

    def factory() -> CustomerInteraction:
        return CustomerInteraction(
            customer_id=msg.customer_id,
            external_id=external_id,
            channel="chat",
            direction=direction,
            provider="brevo",
            occurred_at=occurred_at,
            duration_seconds=None,
            from_address=msg.from_email or msg.from_number or "",
            to_address=msg.to_email or msg.to_number or "",
            subject=None,
            content=msg.content or "",
            content_uri=None,
            raw_payload={},
        )

    return external_id, factory


def _has_fresh_analysis(interaction: CustomerInteraction) -> bool:
    """Return True if interaction was analyzed within ANALYSIS_FRESH_WINDOW."""
    if not interaction.analysis_at:
        return False
    if not interaction.analysis:
        return False
    now = datetime.now(timezone.utc)
    last = interaction.analysis_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return (now - last) < ANALYSIS_FRESH_WINDOW


# ---------------------------------------------------------------------------
# Audio download + transcription
# ---------------------------------------------------------------------------
async def _maybe_transcribe(
    db,
    interaction: CustomerInteraction,
    source_row: Any,
    channel: str,
) -> None:
    """If channel is call/voicemail and has a recording_url, transcribe."""
    if channel not in ("call", "voicemail"):
        return
    if not interaction.content_uri:
        return
    if interaction.content and len(interaction.content.strip()) > 20:
        # Already have a transcript (e.g. webhook supplied it).
        return

    try:
        client = DeepgramTranscriptionClient(settings.DEEPGRAM_API_KEY)
        result: TranscriptResult = await client.transcribe_url(interaction.content_uri)
    except Exception:  # noqa: BLE001
        logger.exception(
            "Deepgram transcription failed for interaction %s", interaction.id
        )
        if not interaction.content:
            interaction.content = "[transcription unavailable]"
        return

    transcript = (result.transcript or "").strip()
    if not transcript:
        if not interaction.content:
            interaction.content = "[transcription unavailable]"
        return

    interaction.content = transcript
    if result.duration_seconds and not interaction.duration_seconds:
        interaction.duration_seconds = result.duration_seconds

    # Denormalize back to call_logs for the legacy dashboard.
    if isinstance(source_row, CallLog):
        source_row.transcription = transcript
        source_row.transcription_status = "completed"


# ---------------------------------------------------------------------------
# Triage / Reply call wrappers (with retry)
# ---------------------------------------------------------------------------
def _build_triage_payload(
    interaction: CustomerInteraction, customer: Customer | None
) -> dict[str, Any]:
    """Build the dict consumed by ``render_triage_user_message``."""
    contact: dict[str, Any] = {
        "name": None,
        "email": None,
        "phone": None,
        "city_state": None,
        "customer_id": str(customer.id) if customer else None,
        "prior_jobs": 0,
        "lead_source": getattr(customer, "lead_source", None) if customer else None,
        "tags": getattr(customer, "tags", None) if customer else None,
    }
    if customer is not None:
        first = (customer.first_name or "").strip()
        last = (customer.last_name or "").strip()
        if first or last:
            contact["name"] = f"{first} {last}".strip()
        contact["email"] = customer.email
        contact["phone"] = customer.phone
        city = (customer.city or "").strip()
        state = (customer.state or "").strip()
        if city or state:
            contact["city_state"] = ", ".join(p for p in (city, state) if p)

    return {
        "channel": interaction.channel,
        "direction": interaction.direction,
        "occurred_at": interaction.occurred_at.isoformat()
        if interaction.occurred_at
        else None,
        "contact": contact,
        "content": interaction.content or "",
    }


async def _call_triage_once(payload: dict[str, Any]) -> TriageResult:
    client = AnthropicClient(settings.ANTHROPIC_API_KEY)
    user_msg = render_triage_user_message(payload)
    return await client.call_triage(user_msg)


async def _call_reply_once(
    payload: dict[str, Any], triage_analysis: dict[str, Any]
) -> ReplyResult:
    client = AnthropicClient(settings.ANTHROPIC_API_KEY)
    user_msg = render_reply_user_message(payload, triage_analysis)
    return await client.call_reply(user_msg)


async def _with_retry(
    fn: Callable[..., Awaitable[Any]],
    *args: Any,
    max_attempts: int = RETRY_MAX_ATTEMPTS,
    base_delay: float = RETRY_BASE_DELAY_SECONDS,
) -> Any:
    """Retry on Anthropic 429 / 529 with exponential backoff."""
    import anthropic

    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return await fn(*args)
        except anthropic.RateLimitError as exc:
            last_exc = exc
            wait = base_delay * (2 ** attempt)
            logger.warning(
                "Anthropic 429 (attempt %d/%d) — sleeping %.1fs",
                attempt + 1,
                max_attempts,
                wait,
            )
            if attempt + 1 >= max_attempts:
                break
            await asyncio.sleep(wait)
        except anthropic.APIStatusError as exc:
            status = getattr(exc, "status_code", None)
            if status not in (429, 529, 500, 502, 503, 504):
                raise
            last_exc = exc
            wait = base_delay * (2 ** attempt)
            logger.warning(
                "Anthropic %s (attempt %d/%d) — sleeping %.1fs",
                status,
                attempt + 1,
                max_attempts,
                wait,
            )
            if attempt + 1 >= max_attempts:
                break
            await asyncio.sleep(wait)
    assert last_exc is not None
    raise last_exc


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------
async def _persist_triage(
    db, interaction: CustomerInteraction, triage: TriageResult
) -> None:
    """Write triage results onto the interaction + log a run row."""
    data = triage.tool_input or {}
    interaction.analysis = data
    interaction.analysis_model = triage.model
    interaction.analysis_at = datetime.now(timezone.utc)
    interaction.analysis_cost_usd = (
        Decimal(interaction.analysis_cost_usd or 0) + (triage.cost_usd or Decimal("0"))
    )

    interaction.intent = data.get("intent")
    interaction.sentiment = data.get("sentiment")
    interaction.urgency = data.get("urgency")
    interaction.hot_lead_score = int(data.get("hot_lead_score") or 0)
    interaction.do_not_contact = bool(data.get("do_not_contact_signal"))

    db.add(
        InteractionAnalysisRun(
            interaction_id=interaction.id,
            tier="triage",
            model=triage.model,
            input_tokens=triage.input_tokens,
            output_tokens=triage.output_tokens,
            cache_read_tokens=triage.cache_read_tokens,
            cache_write_tokens=triage.cache_write_tokens,
            cost_usd=triage.cost_usd,
            duration_ms=triage.duration_ms,
            prompt_version=triage.prompt_version or TRIAGE_VERSION,
            status="ok",
        )
    )
    await db.flush()


async def _persist_reply(
    db, interaction: CustomerInteraction, reply: ReplyResult
) -> None:
    """Write reply results onto the interaction + log a run row."""
    data = reply.tool_input or {}
    reply_text = (data.get("reply") or "").strip()
    if reply_text:
        interaction.suggested_reply = reply_text
    interaction.analysis_cost_usd = (
        Decimal(interaction.analysis_cost_usd or 0) + (reply.cost_usd or Decimal("0"))
    )

    db.add(
        InteractionAnalysisRun(
            interaction_id=interaction.id,
            tier="reply",
            model=reply.model,
            input_tokens=reply.input_tokens,
            output_tokens=reply.output_tokens,
            cache_read_tokens=reply.cache_read_tokens,
            cache_write_tokens=reply.cache_write_tokens,
            cost_usd=reply.cost_usd,
            duration_ms=reply.duration_ms,
            prompt_version=reply.prompt_version or REPLY_VERSION,
            status="ok",
        )
    )
    await db.flush()


async def _persist_action_items(
    db,
    interaction: CustomerInteraction,
    triage_data: dict[str, Any],
) -> None:
    """Insert InteractionActionItem rows from the triage tool output."""
    items = triage_data.get("action_items") or []
    if not isinstance(items, list):
        return
    now = datetime.now(timezone.utc)
    for item in items:
        if not isinstance(item, dict):
            continue
        action = (item.get("action") or "").strip()
        if not action:
            continue
        owner = (item.get("owner") or "none").strip().lower()
        if owner not in ("dannia", "will", "dispatch", "none"):
            owner = "none"
        deadline_hours = item.get("deadline_hours")
        deadline_at = None
        if isinstance(deadline_hours, (int, float)) and deadline_hours > 0:
            deadline_at = now + timedelta(hours=int(deadline_hours))
        db.add(
            InteractionActionItem(
                interaction_id=interaction.id,
                action=action[:120],
                owner=owner,
                deadline_at=deadline_at,
                status="open",
            )
        )
    await db.flush()


async def _record_run_error(
    db,
    interaction: CustomerInteraction,
    tier: str,
    model: str,
    prompt_version: str,
    exc: Exception,
) -> None:
    """Insert a dead-letter InteractionAnalysisRun on terminal failure."""
    detail = f"{type(exc).__name__}: {exc}"[:500]
    logger.error(
        "AI run error tier=%s interaction=%s — %s",
        tier,
        interaction.id,
        detail,
    )
    db.add(
        InteractionAnalysisRun(
            interaction_id=interaction.id,
            tier=tier,
            model=model,
            input_tokens=0,
            output_tokens=0,
            cache_read_tokens=0,
            cache_write_tokens=0,
            cost_usd=Decimal("0"),
            duration_ms=0,
            prompt_version=prompt_version,
            status="error",
            error_detail=detail,
        )
    )
    await db.flush()


# ---------------------------------------------------------------------------
# Outbound queue push
# ---------------------------------------------------------------------------
async def _push_to_outbound_queue(
    db,
    interaction: CustomerInteraction,
    customer: Customer | None,
) -> None:
    """Insert (or skip duplicate) an OutboundCampaignContact for Dannia.

    Direct DB write — no HTTP roundtrip / auth needed since we're already in
    the worker session. Idempotent by (campaign_id, phone).
    """
    campaign_id = settings.DANNIA_OUTBOUND_CAMPAIGN_ID

    phone = ""
    if customer and customer.phone:
        phone = customer.phone.strip()
    elif interaction.from_address and re.match(r"^\+?[\d\s()\-]{7,}$", interaction.from_address):
        phone = interaction.from_address.strip()
    if not phone:
        logger.info(
            "Skipping outbound queue push for interaction %s — no phone",
            interaction.id,
        )
        return

    # Idempotency: skip if a contact with this phone is already queued.
    existing = (
        await db.execute(
            select(OutboundCampaignContact).where(
                OutboundCampaignContact.campaign_id == campaign_id,
                OutboundCampaignContact.phone == phone,
            )
        )
    ).scalars().first()
    if existing is not None:
        logger.info(
            "Outbound queue: phone %s already queued for campaign %s — skipping",
            phone,
            campaign_id,
        )
        return

    name_parts = []
    email = None
    address = None
    city = None
    state = None
    zip_code = None
    if customer is not None:
        if customer.first_name:
            name_parts.append(str(customer.first_name).strip())
        if customer.last_name:
            name_parts.append(str(customer.last_name).strip())
        email = customer.email
        address = customer.address_line1
        city = customer.city
        state = customer.state
        zip_code = customer.postal_code
    if not name_parts:
        name_parts.append(phone)
    account_name = " ".join(p for p in name_parts if p) or phone

    import uuid as _uuid

    db.add(
        OutboundCampaignContact(
            id=str(_uuid.uuid4()),
            campaign_id=campaign_id,
            account_name=account_name[:255],
            phone=phone[:32],
            email=email[:255] if email else None,
            address=address,
            city=city[:100] if city else None,
            state=state[:8] if state else None,
            zip_code=zip_code[:16] if zip_code else None,
            customer_type=None,
            call_priority_label="ai_hot_lead",
            call_status="pending",
            priority=int(interaction.hot_lead_score or 0),
            notes=(
                f"AI hot lead from {interaction.channel} on "
                f"{interaction.occurred_at.isoformat() if interaction.occurred_at else ''}"
            )[:1000],
        )
    )
    await db.flush()


# ---------------------------------------------------------------------------
# call_logs denormalization
# ---------------------------------------------------------------------------
def _denormalize_to_call_log(
    call: CallLog,
    interaction: CustomerInteraction,
    triage_data: dict[str, Any],
) -> None:
    """Mirror new analysis back onto call_logs so legacy CallIntelligenceDashboard keeps working."""
    summary = triage_data.get("summary")
    if summary:
        call.ai_summary = str(summary)[:2000]
    sentiment = triage_data.get("sentiment")
    if sentiment:
        call.sentiment = str(sentiment)[:20]
        # Map sentiment → numeric score on the existing -100..100 axis.
        score_map = {"positive": 60.0, "neutral": 0.0, "negative": -60.0, "hostile": -90.0}
        if sentiment in score_map:
            call.sentiment_score = score_map[sentiment]
    urgency = triage_data.get("urgency")
    if urgency in ("emergency",):
        call.escalation_risk = "high"
    elif urgency in ("this_week",):
        call.escalation_risk = "medium"
    else:
        call.escalation_risk = "low"
    # Topics: rough free-form list of service signals that fired True.
    signals = triage_data.get("service_signals") or {}
    if isinstance(signals, dict):
        topics = [k for k, v in signals.items() if v]
        if topics:
            call.topics = topics
    if interaction.content and not call.transcription:
        call.transcription = interaction.content
        call.transcription_status = "completed"
    call.analyzed_at = datetime.now(timezone.utc)


__all__ = ["process_interaction"]
