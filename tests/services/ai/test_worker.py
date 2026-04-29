"""Worker tests for the AI Interaction Analyzer (Stage 3).

Covers:
  - hot lead end-to-end (triage + reply + outbound queue push)
  - do_not_contact suppression (email DNC + customer archive)
  - emergency urgency
  - auto-reply (no reply tier, no suppression)
  - Scott England competitor referral verbatim
  - daily budget cap pause
  - retry on 429 with exponential backoff
  - idempotency on second invocation

Test isolation: project conftest's `test_db` fixture builds the FULL
metadata against SQLite, which fails because some unrelated tables use
PG-specific JSONB types (the customer_interactions tables themselves use
JSONB columns but SQLAlchemy emulates these as TEXT under SQLite). Each
test fixture builds its own engine with ONLY the tables we need and
patches `async_session_maker` on the worker module.
"""
from __future__ import annotations

import os
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

# Stage 1 required-at-startup keys.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("DEEPGRAM_API_KEY", "test-deepgram-key")

import pytest
import pytest_asyncio
from sqlalchemy import JSON, select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

# SQLite shim — teach the SQLite type compiler how to render JSONB/UUID/ENUM
# so the customer_interactions tables (Postgres-typed) can be created on
# the in-memory test engine. This is test-only monkey-patching.
if not hasattr(SQLiteTypeCompiler, "_ai_shim_installed"):
    def visit_JSONB(self, type_, **kw):  # noqa: N802
        return "JSON"

    def visit_UUID(self, type_, **kw):  # noqa: N802
        return "CHAR(36)"

    def visit_ENUM(self, type_, **kw):  # noqa: N802
        return "VARCHAR(50)"

    SQLiteTypeCompiler.visit_JSONB = visit_JSONB
    SQLiteTypeCompiler.visit_UUID = visit_UUID
    SQLiteTypeCompiler.visit_ENUM = visit_ENUM
    SQLiteTypeCompiler._ai_shim_installed = True  # type: ignore[attr-defined]

from app.database import Base
from app.models.call_log import CallLog
from app.models.customer import Customer
from app.models.customer_interaction import (
    CustomerInteraction,
    InteractionActionItem,
    InteractionAnalysisRun,
)
from app.models.email_list import EmailList, EmailSubscriber
from app.models.inbound_email import InboundEmail
from app.models.message import Message
from app.models.outbound_campaign import OutboundCampaign, OutboundCampaignContact
from app.services.ai import budget as budget_module
from app.services.ai import worker as worker_module
from app.services.ai.suppression import DNC_EMAIL_LIST_ID


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------
TABLES_NEEDED = [
    Customer.__table__,
    CallLog.__table__,
    Message.__table__,
    InboundEmail.__table__,
    EmailList.__table__,
    EmailSubscriber.__table__,
    OutboundCampaign.__table__,
    OutboundCampaignContact.__table__,
    CustomerInteraction.__table__,
    InteractionActionItem.__table__,
    InteractionAnalysisRun.__table__,
]


@pytest_asyncio.fixture
async def patched_session_maker():
    """In-memory SQLite engine with only the tables this worker touches.

    Patches `app.services.ai.worker.async_session_maker` to return sessions
    bound to this engine for the test's duration. Also resets the budget
    alert one-shot guard so each test starts fresh.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=TABLES_NEEDED)

    sessionmaker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    # Seed Dannia's outbound campaign so FK constraints hold.
    async with sessionmaker() as db:
        db.add(
            OutboundCampaign(
                id="email-openers-spring-2026",
                name="Email Openers Spring 2026",
                status="active",
            )
        )
        await db.commit()

    budget_module.reset_alert_state_for_tests()

    with patch.object(worker_module, "async_session_maker", sessionmaker):
        yield sessionmaker

    await engine.dispose()


def _build_triage_result(tool_input: dict) -> MagicMock:
    """Mock TriageResult with the fields the worker reads."""
    r = MagicMock()
    r.tool_name = "record_interaction_analysis"
    r.tool_input = tool_input
    r.model = "claude-haiku-4-5-20251001"
    r.prompt_version = "v1"
    r.input_tokens = 200
    r.output_tokens = 80
    r.cache_read_tokens = 0
    r.cache_write_tokens = 0
    r.cost_usd = Decimal("0.000400")
    r.duration_ms = 250
    return r


def _build_reply_result(reply_text: str, *, tone: str = "warm") -> MagicMock:
    r = MagicMock()
    r.tool_name = "draft_reply"
    r.tool_input = {
        "reply": reply_text,
        "channel_format": "email",
        "tone": tone,
        "reason": "drafted by mock",
    }
    r.model = "claude-sonnet-4-6"
    r.prompt_version = "v1"
    r.input_tokens = 250
    r.output_tokens = 120
    r.cache_read_tokens = 0
    r.cache_write_tokens = 0
    r.cost_usd = Decimal("0.005000")
    r.duration_ms = 600
    return r


async def _seed_inbound_email(
    sessionmaker,
    *,
    sender_email: str,
    subject: str,
    body: str,
    customer: Customer | None = None,
) -> UUID:
    """Insert an InboundEmail and return its UUID."""
    from datetime import datetime, timezone

    msg_id = f"AAMkAD-{uuid4().hex[:12]}"
    async with sessionmaker() as db:
        if customer is not None:
            db.add(customer)
            await db.flush()
        email = InboundEmail(
            message_id=msg_id,
            sender_email=sender_email,
            sender_name=sender_email,
            subject=subject,
            body_preview=body[:200],
            received_at=datetime.now(timezone.utc),
            customer_id=customer.id if customer else None,
        )
        db.add(email)
        await db.commit()
        await db.refresh(email)
        return email.id


def _patch_anthropic_clients(triage_result, reply_result=None):
    """Helper: patch the AnthropicClient instances created inside worker funcs."""
    fake_client_class = MagicMock()
    instance = MagicMock()
    instance.call_triage = AsyncMock(return_value=triage_result)
    instance.call_reply = AsyncMock(
        return_value=reply_result
        if reply_result is not None
        else _build_reply_result("[reply]")
    )
    fake_client_class.return_value = instance
    return patch.object(worker_module, "AnthropicClient", fake_client_class), instance


def _patch_msgraph(body_text: str):
    """Stub MS365 get_message_by_id to return a synthetic Graph payload."""
    body = {"contentType": "text", "content": body_text}
    return patch.object(
        worker_module.MS365EmailService,
        "get_message_by_id",
        new=AsyncMock(return_value={"body": body}),
    )


# ---------------------------------------------------------------------------
# 1. Hot lead path — triage hot, reply drafted, outbound queue populated
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_worker_hot_lead(patched_session_maker):
    sender = "homeowner@example.com"
    subject = "Pump-out next Tuesday?"
    body = "I need a pump-out next Tuesday in Brentwood TN, what's your price for a 1000-gal tank?"
    customer = Customer(
        id=uuid4(),
        first_name="Sara",
        last_name="Homeowner",
        email=sender,
        phone="(615) 555-1212",
        city="Brentwood",
        state="TN",
    )
    email_id = await _seed_inbound_email(
        patched_session_maker,
        sender_email=sender,
        subject=subject,
        body=body,
        customer=customer,
    )

    triage_data = {
        "intent": "request_quote",
        "sentiment": "positive",
        "hot_lead_score": 80,
        "urgency": "this_week",
        "do_not_contact_signal": False,
        "competitor_mentioned": None,
        "service_signals": {
            "tank_overflow": False,
            "schedule_due": True,
            "buying_house": False,
            "selling_house": False,
            "complaint_about_us": False,
            "complaint_about_competitor": False,
            "returning_customer": False,
        },
        "action_items": [
            {
                "action": "Confirm Tuesday slot and quote $625",
                "owner": "dannia",
                "deadline_hours": 4,
            }
        ],
        "summary": "Homeowner wants a 1,000-gallon pump-out next Tuesday in Brentwood.",
        "key_quote": "I need a pump-out next Tuesday",
    }
    reply_text = (
        "Hey, $625 all-in for a 1,000-gal tank. We're usually out within "
        "a week — what day works? — Will"
    )

    patch_anthropic, _ = _patch_anthropic_clients(
        _build_triage_result(triage_data), _build_reply_result(reply_text)
    )
    with patch_anthropic, _patch_msgraph(body):
        await worker_module.process_interaction(email_id, "email")

    async with patched_session_maker() as db:
        ci = (
            await db.execute(select(CustomerInteraction))
        ).scalars().first()
        assert ci is not None
        assert ci.channel == "email"
        assert ci.intent == "request_quote"
        assert ci.hot_lead_score == 80
        assert ci.urgency == "this_week"
        assert ci.do_not_contact is False
        assert ci.suggested_reply and "1,000-gal" in ci.suggested_reply

        # 2 runs (triage + reply), both ok
        runs = (
            await db.execute(
                select(InteractionAnalysisRun).where(
                    InteractionAnalysisRun.interaction_id == ci.id
                )
            )
        ).scalars().all()
        tiers = sorted(r.tier for r in runs)
        assert tiers == ["reply", "triage"]
        assert all(r.status == "ok" for r in runs)

        # Action item persisted
        items = (
            await db.execute(
                select(InteractionActionItem).where(
                    InteractionActionItem.interaction_id == ci.id
                )
            )
        ).scalars().all()
        assert len(items) == 1
        assert items[0].owner == "dannia"

        # Outbound queue push for email-openers-spring-2026
        contacts = (
            await db.execute(
                select(OutboundCampaignContact).where(
                    OutboundCampaignContact.campaign_id
                    == "email-openers-spring-2026"
                )
            )
        ).scalars().all()
        assert len(contacts) == 1
        assert contacts[0].phone == "(615) 555-1212"
        assert contacts[0].priority == 80

        # No suppression list entry
        subs = (
            await db.execute(
                select(EmailSubscriber).where(
                    EmailSubscriber.list_id == DNC_EMAIL_LIST_ID
                )
            )
        ).scalars().all()
        assert subs == []


# ---------------------------------------------------------------------------
# 2. do_not_contact: "Stop. Lose my number."
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_worker_do_not_contact(patched_session_maker):
    sender = "loud@example.com"
    body = "Stop. Lose my number."
    customer = Customer(
        id=uuid4(),
        first_name="Loud",
        last_name="Person",
        email=sender,
        phone="(555) 123-4567",
    )
    email_id = await _seed_inbound_email(
        patched_session_maker,
        sender_email=sender,
        subject="STOP",
        body=body,
        customer=customer,
    )

    triage_data = {
        "intent": "unsubscribe_request",
        "sentiment": "negative",
        "hot_lead_score": 0,
        "urgency": "none",
        "do_not_contact_signal": True,
        "competitor_mentioned": None,
        "service_signals": {
            "tank_overflow": False,
            "schedule_due": False,
            "buying_house": False,
            "selling_house": False,
            "complaint_about_us": False,
            "complaint_about_competitor": False,
            "returning_customer": False,
        },
        "action_items": [],
        "summary": "Recipient demands removal.",
        "key_quote": "Lose my number.",
    }

    patch_anthropic, fake_instance = _patch_anthropic_clients(
        _build_triage_result(triage_data)
    )
    with patch_anthropic, _patch_msgraph(body):
        await worker_module.process_interaction(email_id, "email")

    # Reply should NOT have been called.
    assert fake_instance.call_reply.await_count == 0

    async with patched_session_maker() as db:
        ci = (await db.execute(select(CustomerInteraction))).scalars().first()
        assert ci.do_not_contact is True
        assert ci.suggested_reply is None

        # DNC email list got the row.
        subs = (
            await db.execute(
                select(EmailSubscriber).where(
                    EmailSubscriber.list_id == DNC_EMAIL_LIST_ID,
                    EmailSubscriber.email == sender,
                )
            )
        ).scalars().all()
        assert len(subs) == 1
        assert subs[0].status == "unsubscribed"
        assert subs[0].source == "ai_analyzer"

        # Customer archived + lead_source flipped.
        cust = (
            await db.execute(
                select(Customer).where(Customer.email == sender)
            )
        ).scalar_one()
        assert cust.lead_source == "do_not_email"
        assert cust.is_archived is True
        assert cust.tags is not None
        assert "unsubscribed" in cust.tags
        assert "do_not_email" in cust.tags

        # No outbound queue push.
        contacts = (
            await db.execute(select(OutboundCampaignContact))
        ).scalars().all()
        assert contacts == []


# ---------------------------------------------------------------------------
# 3. Emergency urgency
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_worker_emergency(patched_session_maker):
    sender = "panic@example.com"
    body = "tank is overflowing in my yard, need someone today!"
    customer = Customer(
        id=uuid4(),
        first_name="Panic",
        last_name="Mode",
        email=sender,
        phone="+15125551111",
    )
    email_id = await _seed_inbound_email(
        patched_session_maker,
        sender_email=sender,
        subject="HELP",
        body=body,
        customer=customer,
    )

    triage_data = {
        "intent": "book_service",
        "sentiment": "negative",
        "hot_lead_score": 92,
        "urgency": "emergency",
        "do_not_contact_signal": False,
        "competitor_mentioned": None,
        "service_signals": {
            "tank_overflow": True,
            "schedule_due": False,
            "buying_house": False,
            "selling_house": False,
            "complaint_about_us": False,
            "complaint_about_competitor": False,
            "returning_customer": False,
        },
        "action_items": [
            {"action": "Dispatch today", "owner": "dispatch", "deadline_hours": 4}
        ],
        "summary": "Tank overflowing emergency.",
        "key_quote": "tank is overflowing in my yard",
    }

    patch_anthropic, _ = _patch_anthropic_clients(
        _build_triage_result(triage_data),
        _build_reply_result("I can have someone out today."),
    )
    with patch_anthropic, _patch_msgraph(body):
        await worker_module.process_interaction(email_id, "email")

    async with patched_session_maker() as db:
        ci = (await db.execute(select(CustomerInteraction))).scalars().first()
        assert ci.urgency == "emergency"
        assert ci.hot_lead_score == 92
        assert ci.intent == "book_service"

        contacts = (
            await db.execute(select(OutboundCampaignContact))
        ).scalars().all()
        assert len(contacts) == 1


# ---------------------------------------------------------------------------
# 4. Auto-reply: no reply tier, no suppression
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_worker_auto_reply(patched_session_maker):
    sender = "ooo@example.com"
    body = "I am out of office until next Monday. I will respond when I return."
    email_id = await _seed_inbound_email(
        patched_session_maker,
        sender_email=sender,
        subject="Out of Office",
        body=body,
    )

    triage_data = {
        "intent": "auto_reply",
        "sentiment": "neutral",
        "hot_lead_score": 0,
        "urgency": "none",
        "do_not_contact_signal": False,
        "competitor_mentioned": None,
        "service_signals": {
            "tank_overflow": False,
            "schedule_due": False,
            "buying_house": False,
            "selling_house": False,
            "complaint_about_us": False,
            "complaint_about_competitor": False,
            "returning_customer": False,
        },
        "action_items": [],
        "summary": "Auto-reply: out of office.",
        "key_quote": "out of office",
    }

    patch_anthropic, fake_instance = _patch_anthropic_clients(
        _build_triage_result(triage_data)
    )
    with patch_anthropic, _patch_msgraph(body):
        await worker_module.process_interaction(email_id, "email")

    assert fake_instance.call_reply.await_count == 0

    async with patched_session_maker() as db:
        ci = (await db.execute(select(CustomerInteraction))).scalars().first()
        assert ci.intent == "auto_reply"
        assert ci.do_not_contact is False
        assert ci.suggested_reply is None
        items = (
            await db.execute(select(InteractionActionItem))
        ).scalars().all()
        assert items == []

        subs = (
            await db.execute(select(EmailSubscriber))
        ).scalars().all()
        assert subs == []


# ---------------------------------------------------------------------------
# 5. Scott England competitor referral (Apr 25 verbatim)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_worker_competitor_referral(patched_session_maker):
    sender = "sengland@realtracs.com"
    subject = "Re: Mac Septic Spring Service"
    body = (
        "My brother owns England Septic so I bet you can't beat my free "
        "pump outs but if so please call. lol"
    )
    email_id = await _seed_inbound_email(
        patched_session_maker,
        sender_email=sender,
        subject=subject,
        body=body,
    )

    triage_data = {
        "intent": "competitor_referral",
        "sentiment": "neutral",
        "hot_lead_score": 0,
        "urgency": "none",
        "do_not_contact_signal": True,
        "competitor_mentioned": "England Septic",
        "service_signals": {
            "tank_overflow": False,
            "schedule_due": False,
            "buying_house": False,
            "selling_house": False,
            "complaint_about_us": False,
            "complaint_about_competitor": False,
            "returning_customer": False,
        },
        "action_items": [],
        "summary": "Competitor referral; brother owns England Septic.",
        "key_quote": "My brother owns England Septic",
    }

    patch_anthropic, _ = _patch_anthropic_clients(
        _build_triage_result(triage_data)
    )
    with patch_anthropic, _patch_msgraph(body):
        await worker_module.process_interaction(email_id, "email")

    async with patched_session_maker() as db:
        ci = (await db.execute(select(CustomerInteraction))).scalars().first()
        assert ci.do_not_contact is True
        assert ci.intent == "competitor_referral"
        assert ci.suggested_reply is None
        # competitor_mentioned stored on analysis JSONB
        assert ci.analysis.get("competitor_mentioned") == "England Septic"

        subs = (
            await db.execute(
                select(EmailSubscriber).where(
                    EmailSubscriber.list_id == DNC_EMAIL_LIST_ID,
                    EmailSubscriber.email == sender,
                )
            )
        ).scalars().all()
        assert len(subs) == 1
        assert subs[0].status == "unsubscribed"


# ---------------------------------------------------------------------------
# 6. Daily budget pause
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_worker_budget_pause(patched_session_maker):
    sender = "would-be@example.com"
    body = "I'd like a quote please."
    email_id = await _seed_inbound_email(
        patched_session_maker,
        sender_email=sender,
        subject="Quote",
        body=body,
    )

    # Pre-seed budget overspend for today.
    async with patched_session_maker() as db:
        # Need a placeholder interaction to attach the run to (FK).
        from datetime import datetime, timezone
        ph = CustomerInteraction(
            external_id=f"placeholder:{uuid4()}",
            channel="email",
            direction="inbound",
            provider="microsoft365",
            occurred_at=datetime.now(timezone.utc),
            from_address="x@x",
            to_address="y@y",
            content="seed",
        )
        db.add(ph)
        await db.flush()
        db.add(
            InteractionAnalysisRun(
                interaction_id=ph.id,
                tier="triage",
                model="claude-haiku-4-5-20251001",
                cost_usd=Decimal("26.00"),
                input_tokens=1, output_tokens=1, cache_read_tokens=0, cache_write_tokens=0,
                duration_ms=10,
                prompt_version="v1",
                status="ok",
            )
        )
        await db.commit()

    triage_data = {
        "intent": "request_quote",
        "sentiment": "positive",
        "hot_lead_score": 80,
        "urgency": "this_week",
        "do_not_contact_signal": False,
        "competitor_mentioned": None,
        "service_signals": {
            "tank_overflow": False, "schedule_due": False, "buying_house": False,
            "selling_house": False, "complaint_about_us": False,
            "complaint_about_competitor": False, "returning_customer": False,
        },
        "action_items": [],
        "summary": "Quote.",
        "key_quote": "quote please",
    }

    patch_anthropic, fake_instance = _patch_anthropic_clients(
        _build_triage_result(triage_data)
    )
    fake_email_send = AsyncMock(return_value={"success": True, "message_id": "m1"})

    with patch_anthropic, _patch_msgraph(body), patch(
        "app.services.email_service.EmailService.send_email", new=fake_email_send
    ):
        budget_module.reset_alert_state_for_tests()
        await worker_module.process_interaction(email_id, "email")

    # No Anthropic calls — paused.
    assert fake_instance.call_triage.await_count == 0
    assert fake_instance.call_reply.await_count == 0
    # Alert email sent exactly once.
    assert fake_email_send.await_count == 1


# ---------------------------------------------------------------------------
# 7. Retry on 429
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_worker_retry(patched_session_maker):
    import anthropic

    sender = "retry@example.com"
    body = "asking for a quote"
    email_id = await _seed_inbound_email(
        patched_session_maker,
        sender_email=sender,
        subject="Quote",
        body=body,
    )

    triage_data = {
        "intent": "request_quote",
        "sentiment": "positive",
        "hot_lead_score": 40,
        "urgency": "this_month",
        "do_not_contact_signal": False,
        "competitor_mentioned": None,
        "service_signals": {
            "tank_overflow": False, "schedule_due": False, "buying_house": False,
            "selling_house": False, "complaint_about_us": False,
            "complaint_about_competitor": False, "returning_customer": False,
        },
        "action_items": [],
        "summary": "Quote.", "key_quote": "quote",
    }
    success_result = _build_triage_result(triage_data)

    # First call: 429. Second call: success.
    rate_limit = anthropic.RateLimitError(
        "rate limit",
        response=MagicMock(status_code=429),
        body=None,
    )
    triage_mock = AsyncMock(side_effect=[rate_limit, success_result])

    fake_client_class = MagicMock()
    instance = MagicMock()
    instance.call_triage = triage_mock
    instance.call_reply = AsyncMock()
    fake_client_class.return_value = instance

    sleep_mock = AsyncMock()

    with patch.object(worker_module, "AnthropicClient", fake_client_class), \
         patch.object(worker_module.asyncio, "sleep", new=sleep_mock), \
         _patch_msgraph(body):
        await worker_module.process_interaction(email_id, "email")

    # 2 attempts.
    assert triage_mock.await_count == 2
    # asyncio.sleep called at least once for backoff.
    assert sleep_mock.await_count >= 1

    async with patched_session_maker() as db:
        ci = (await db.execute(select(CustomerInteraction))).scalars().first()
        assert ci is not None
        assert ci.intent == "request_quote"
        runs = (
            await db.execute(
                select(InteractionAnalysisRun).where(
                    InteractionAnalysisRun.interaction_id == ci.id
                )
            )
        ).scalars().all()
        # The final run is "ok"; we don't write a run row mid-retry.
        assert any(r.status == "ok" and r.tier == "triage" for r in runs)


# ---------------------------------------------------------------------------
# 8. Idempotency: same source twice → one CustomerInteraction
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_worker_idempotency(patched_session_maker):
    sender = "twice@example.com"
    body = "I'd like a quote please."
    email_id = await _seed_inbound_email(
        patched_session_maker,
        sender_email=sender,
        subject="Quote",
        body=body,
    )

    triage_data = {
        "intent": "request_quote",
        "sentiment": "neutral",
        "hot_lead_score": 30,
        "urgency": "this_month",
        "do_not_contact_signal": False,
        "competitor_mentioned": None,
        "service_signals": {
            "tank_overflow": False, "schedule_due": False, "buying_house": False,
            "selling_house": False, "complaint_about_us": False,
            "complaint_about_competitor": False, "returning_customer": False,
        },
        "action_items": [],
        "summary": "Quote.", "key_quote": "quote",
    }

    patch_anthropic, fake_instance = _patch_anthropic_clients(
        _build_triage_result(triage_data)
    )
    with patch_anthropic, _patch_msgraph(body):
        await worker_module.process_interaction(email_id, "email")
        await worker_module.process_interaction(email_id, "email")

    async with patched_session_maker() as db:
        cis = (
            await db.execute(select(CustomerInteraction))
        ).scalars().all()
        assert len(cis) == 1
        runs = (await db.execute(select(InteractionAnalysisRun))).scalars().all()
        # Exactly one triage run on the real interaction (no duplicates).
        assert len([r for r in runs if r.tier == "triage"]) == 1

    # Second invocation must not call Anthropic again.
    assert fake_instance.call_triage.await_count == 1
