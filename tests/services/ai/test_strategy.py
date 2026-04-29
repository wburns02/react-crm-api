"""Tests for app.services.ai.strategy.run_weekly_strategy.

We mock AnthropicClient.call_strategy so the suite never hits the network
or pays a cent.
"""
from __future__ import annotations

import os
import uuid as uuid_module
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

# Required-at-startup keys — set BEFORE app import.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("DEEPGRAM_API_KEY", "test-deepgram-key")

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool


# SQLite type shims (test-only).
if not hasattr(SQLiteTypeCompiler, "_strategy_shim_installed"):
    def visit_JSONB(self, type_, **kw):  # noqa: N802
        return "JSON"

    def visit_UUID(self, type_, **kw):  # noqa: N802
        return "CHAR(36)"

    def visit_ENUM(self, type_, **kw):  # noqa: N802
        return "VARCHAR(50)"

    SQLiteTypeCompiler.visit_JSONB = visit_JSONB
    SQLiteTypeCompiler.visit_UUID = visit_UUID
    SQLiteTypeCompiler.visit_ENUM = visit_ENUM
    SQLiteTypeCompiler._strategy_shim_installed = True  # type: ignore[attr-defined]


from app.database import Base
from app.models.customer_interaction import (
    CustomerInteraction,
    InteractionAnalysisRun,
)
from app.models.interaction_insight import InteractionInsight
from app.services.ai import strategy as strategy_module
from app.services.ai.strategy import (
    iso_week_to_date_range,
    previous_iso_week,
    run_weekly_strategy,
)


_TABLES = [
    InteractionInsight.__table__,
    CustomerInteraction.__table__,
    InteractionAnalysisRun.__table__,
]


@pytest_asyncio.fixture
async def test_db():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_TABLES)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=_TABLES)
    await engine.dispose()


@dataclass
class _FakeStrategyResult:
    text: str = "# Test report\n\nFake content."
    thinking: str = ""
    thinking_tokens: int = 0
    model: str = "claude-opus-4-7"
    prompt_version: str = "v1"
    input_tokens: int = 1000
    output_tokens: int = 500
    cache_read_tokens: int = 200
    cache_write_tokens: int = 50
    cost_usd: Decimal = Decimal("0.0125")
    duration_ms: int = 1234


def _make_client_mock(text: str = "# Test report\n\nFake content."):
    client = AsyncMock()
    client.call_strategy = AsyncMock(return_value=_FakeStrategyResult(text=text))
    return client


async def _seed_interaction(
    db: AsyncSession,
    *,
    occurred_at: datetime,
    intent: str = "request_quote",
    score: int = 75,
    content: str = "test content",
):
    inter = CustomerInteraction(
        id=uuid_module.uuid4(),
        customer_id=None,
        external_id=f"ext-{uuid_module.uuid4()}",
        channel="sms",
        direction="inbound",
        provider="twilio",
        occurred_at=occurred_at,
        from_address="+15125550100",
        to_address="+15125550199",
        content=content,
        raw_payload={},
        analysis={"intent": intent, "hot_lead_score": score},
        analysis_cost_usd=Decimal("0.001"),
        hot_lead_score=score,
        intent=intent,
        sentiment="neutral",
        urgency="this_week",
        do_not_contact=False,
    )
    db.add(inter)
    await db.commit()
    return inter


# ---------------------------------------------------------------------------
# previous_iso_week / iso_week_to_date_range
# ---------------------------------------------------------------------------
def test_iso_week_to_date_range_returns_monday_sunday():
    monday, sunday = iso_week_to_date_range("2026-W17")
    assert monday.isoweekday() == 1  # Monday
    assert sunday.isoweekday() == 7  # Sunday
    assert (sunday - monday).days == 6


def test_iso_week_to_date_range_invalid():
    import pytest

    with pytest.raises(ValueError):
        iso_week_to_date_range("not-a-week")


def test_previous_iso_week_format():
    week = previous_iso_week()
    assert "-W" in week
    parts = week.split("-W")
    assert len(parts) == 2
    int(parts[0])  # year parses
    int(parts[1])  # week parses


# ---------------------------------------------------------------------------
# run_weekly_strategy
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_run_weekly_strategy_writes_row_with_cost(test_db: AsyncSession):
    iso_week = previous_iso_week()
    start_date, end_date = iso_week_to_date_range(iso_week)
    occurred = datetime.combine(
        start_date, datetime.min.time(), tzinfo=timezone.utc
    ) + timedelta(days=2, hours=10)
    await _seed_interaction(test_db, occurred_at=occurred)

    insight = await run_weekly_strategy(
        test_db,
        iso_week=iso_week,
        client=_make_client_mock(text="# Big findings\n\n- A"),
    )
    assert insight.iso_week == iso_week
    assert insight.total_interactions == 1
    assert insight.cost_usd == Decimal("0.0125")
    assert "Big findings" in insight.report_markdown
    assert insight.model == "claude-opus-4-7"


@pytest.mark.asyncio
async def test_run_weekly_strategy_idempotent_when_not_forced(
    test_db: AsyncSession,
):
    iso_week = previous_iso_week()
    start_date, _ = iso_week_to_date_range(iso_week)
    occurred = datetime.combine(
        start_date, datetime.min.time(), tzinfo=timezone.utc
    ) + timedelta(days=1, hours=8)
    await _seed_interaction(test_db, occurred_at=occurred)

    client1 = _make_client_mock(text="# First")
    insight1 = await run_weekly_strategy(test_db, iso_week=iso_week, client=client1)

    client2 = _make_client_mock(text="# Second")
    insight2 = await run_weekly_strategy(test_db, iso_week=iso_week, client=client2)

    # Cached row, no second call.
    assert client2.call_strategy.await_count == 0
    assert insight1.id == insight2.id
    assert "First" in insight2.report_markdown


@pytest.mark.asyncio
async def test_run_weekly_strategy_force_replaces(test_db: AsyncSession):
    iso_week = previous_iso_week()
    start_date, _ = iso_week_to_date_range(iso_week)
    occurred = datetime.combine(
        start_date, datetime.min.time(), tzinfo=timezone.utc
    ) + timedelta(days=1, hours=8)
    await _seed_interaction(test_db, occurred_at=occurred)

    client1 = _make_client_mock(text="# First")
    insight1 = await run_weekly_strategy(test_db, iso_week=iso_week, client=client1)
    first_id = insight1.id

    client2 = _make_client_mock(text="# Second run")
    insight2 = await run_weekly_strategy(
        test_db, iso_week=iso_week, force=True, client=client2
    )
    assert insight1.id == insight2.id == first_id  # row replaced in place
    assert "Second run" in insight2.report_markdown
    assert client2.call_strategy.await_count == 1


@pytest.mark.asyncio
async def test_run_weekly_strategy_empty_week_no_model_call(
    test_db: AsyncSession,
):
    """An empty week should write a placeholder row and NOT call the model."""
    iso_week = "2024-W01"  # historic empty week
    client = _make_client_mock()
    insight = await run_weekly_strategy(test_db, iso_week=iso_week, client=client)
    assert insight.total_interactions == 0
    assert client.call_strategy.await_count == 0
    assert "No customer interactions" in insight.report_markdown


# ---------------------------------------------------------------------------
# Stratified sampling — protects the 300-cap
# ---------------------------------------------------------------------------
def test_stratified_sample_caps_total_and_keeps_each_intent():
    """If there are 5 intents with 100 rows each (500 total), cap=300 should
    return exactly 300 rows distributed across all 5 intents (≥1 each)."""
    rows = []
    for intent in ("a", "b", "c", "d", "e"):
        for i in range(100):
            row = CustomerInteraction(
                id=uuid_module.uuid4(),
                external_id=f"x-{intent}-{i}",
                channel="sms",
                direction="inbound",
                provider="twilio",
                occurred_at=datetime.now(timezone.utc),
                from_address="x",
                to_address="y",
                hot_lead_score=i,
                intent=intent,
                do_not_contact=False,
                analysis={},
                raw_payload={},
            )
            rows.append(row)

    sampled = strategy_module._stratified_sample(rows, 300)
    assert len(sampled) == 300

    by_intent: dict[str, int] = {}
    for r in sampled:
        by_intent[r.intent] = by_intent.get(r.intent, 0) + 1
    # Every intent represented (proportional → ≈60 each).
    assert set(by_intent.keys()) == {"a", "b", "c", "d", "e"}
    for v in by_intent.values():
        assert v >= 1
