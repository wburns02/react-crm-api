"""Tests for the AI Interaction Analyzer read endpoints (Stage 4).

Endpoints under test:
  GET  /api/v2/customers/{customer_id}/interactions
  GET  /api/v2/ai/interactions/hot                    (static)
  GET  /api/v2/ai/budget                              (static)
  GET  /api/v2/ai/interactions/{interaction_id}       (dynamic)
  POST /api/v2/ai/interactions/{interaction_id}/dismiss-hot
  POST /api/v2/ai/interactions/{interaction_id}/reanalyze

Test isolation: builds an in-memory SQLite engine with ONLY the tables this
suite touches and overrides the FastAPI `get_db` dependency for the duration
of each test. Postgres-only types (JSONB / UUID / ENUM) are shimmed at the
SQLite type-compiler level (test-only monkey patches).
"""
from __future__ import annotations

import os
import uuid as uuid_module
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

# Stage 1 required-at-startup keys — set BEFORE app import.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("DEEPGRAM_API_KEY", "test-deepgram-key")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# SQLite type shims (test-only): JSONB / UUID / ENUM rendered to SQLite-safe.
# Must run BEFORE Base.metadata.create_all is invoked on a SQLite engine.
# ---------------------------------------------------------------------------
if not hasattr(SQLiteTypeCompiler, "_ai_interactions_shim_installed"):
    def visit_JSONB(self, type_, **kw):  # noqa: N802
        return "JSON"

    def visit_UUID(self, type_, **kw):  # noqa: N802
        return "CHAR(36)"

    def visit_ENUM(self, type_, **kw):  # noqa: N802
        return "VARCHAR(50)"

    SQLiteTypeCompiler.visit_JSONB = visit_JSONB
    SQLiteTypeCompiler.visit_UUID = visit_UUID
    SQLiteTypeCompiler.visit_ENUM = visit_ENUM
    SQLiteTypeCompiler._ai_interactions_shim_installed = True  # type: ignore[attr-defined]

# Coerce SQLAlchemy Uuid bind processor to accept str inputs from path params.
import uuid as _uuid_for_patch
from sqlalchemy.sql import sqltypes as _sqltypes

if not getattr(_sqltypes.Uuid, "_ai_interactions_str_patch", False):
    _orig_uuid_bind = _sqltypes.Uuid.bind_processor

    def _patched_uuid_bind(self, dialect):
        original = _orig_uuid_bind(self, dialect)
        if original is None:
            return None

        def _process(value):
            if isinstance(value, str):
                try:
                    value = _uuid_for_patch.UUID(value)
                except ValueError:
                    pass
            return original(value)

        return _process

    _sqltypes.Uuid.bind_processor = _patched_uuid_bind
    _sqltypes.Uuid._ai_interactions_str_patch = True  # type: ignore[attr-defined]

from app.api.deps import create_access_token, get_password_hash
from app.database import Base, get_db
from app.main import app as fastapi_app
from app.models.customer import Customer
from app.models.customer_interaction import (
    CustomerInteraction,
    InteractionActionItem,
    InteractionAnalysisRun,
)
from app.models.user import User


PREFIX = "/api/v2"


_TABLES = [
    Customer.__table__,
    User.__table__,
    CustomerInteraction.__table__,
    InteractionActionItem.__table__,
    InteractionAnalysisRun.__table__,
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def test_db():
    """In-memory SQLite engine with just the tables our endpoints touch."""
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


@pytest_asyncio.fixture
async def test_user(test_db: AsyncSession) -> User:
    user = User(
        email="ai-tester@example.com",
        hashed_password=get_password_hash("testpassword123"),
        first_name="AI",
        last_name="Tester",
        is_active=True,
    )
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)
    return user


@pytest_asyncio.fixture
async def client(test_db: AsyncSession):
    async def override_get_db():
        yield test_db

    fastapi_app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(
        transport=transport, base_url="http://test", follow_redirects=True
    ) as ac:
        yield ac
    fastapi_app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def authed(client: AsyncClient, test_user: User) -> AsyncClient:
    token = create_access_token(
        data={"sub": str(test_user.id), "email": test_user.email}
    )
    client.headers["Authorization"] = f"Bearer {token}"
    return client


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------
async def _seed_customer(db: AsyncSession, **overrides) -> Customer:
    defaults = {
        "id": uuid_module.uuid4(),
        "first_name": "Hot",
        "last_name": "Lead",
        "email": "hot.lead@example.com",
        "phone": "5125550100",
        "is_active": True,
        "is_archived": False,
    }
    defaults.update(overrides)
    cust = Customer(**defaults)
    db.add(cust)
    await db.commit()
    await db.refresh(cust)
    return cust


async def _seed_interaction(
    db: AsyncSession,
    *,
    customer_id: uuid_module.UUID | None = None,
    channel: str = "sms",
    direction: str = "inbound",
    provider: str = "twilio",
    score: int = 0,
    occurred_at: datetime | None = None,
    content: str = "Hello there",
    suggested_reply: str | None = None,
    intent: str | None = None,
    urgency: str | None = None,
    do_not_contact: bool = False,
) -> CustomerInteraction:
    occ = occurred_at or datetime.now(timezone.utc)
    inter = CustomerInteraction(
        id=uuid_module.uuid4(),
        customer_id=customer_id,
        external_id=f"ext-{uuid_module.uuid4()}",
        channel=channel,
        direction=direction,
        provider=provider,
        occurred_at=occ,
        from_address="+15125550100",
        to_address="+15125550199",
        subject=None,
        content=content,
        raw_payload={},
        analysis={},
        suggested_reply=suggested_reply,
        analysis_cost_usd=Decimal("0.0123"),
        hot_lead_score=score,
        intent=intent,
        sentiment=None,
        urgency=urgency,
        do_not_contact=do_not_contact,
    )
    db.add(inter)
    await db.commit()
    await db.refresh(inter)
    return inter


async def _seed_run(
    db: AsyncSession,
    interaction_id: uuid_module.UUID,
    *,
    cost_usd: Decimal = Decimal("0.05"),
    tier: str = "triage",
    status_: str = "ok",
    created_at: datetime | None = None,
) -> InteractionAnalysisRun:
    run = InteractionAnalysisRun(
        id=uuid_module.uuid4(),
        interaction_id=interaction_id,
        tier=tier,
        model="claude-test",
        input_tokens=100,
        output_tokens=50,
        cache_read_tokens=0,
        cache_write_tokens=0,
        cost_usd=cost_usd,
        duration_ms=120,
        prompt_version="v1",
        status=status_,
    )
    if created_at is not None:
        run.created_at = created_at
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


# ---------------------------------------------------------------------------
# Tests — Authorization
# ---------------------------------------------------------------------------
class TestAuth:
    @pytest.mark.asyncio
    async def test_hot_requires_auth(self, client: AsyncClient):
        r = await client.get(f"{PREFIX}/ai/interactions/hot")
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_budget_requires_auth(self, client: AsyncClient):
        r = await client.get(f"{PREFIX}/ai/budget")
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_customer_history_requires_auth(self, client: AsyncClient):
        r = await client.get(
            f"{PREFIX}/customers/{uuid_module.uuid4()}/interactions"
        )
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# Tests — GET /customers/{id}/interactions
# ---------------------------------------------------------------------------
class TestCustomerHistory:
    @pytest.mark.asyncio
    async def test_returns_list_with_limit_applied(
        self, authed: AsyncClient, test_db: AsyncSession
    ):
        cust = await _seed_customer(test_db)
        # Seed five interactions across two days.
        base = datetime.now(timezone.utc).replace(microsecond=0)
        for i in range(5):
            await _seed_interaction(
                test_db,
                customer_id=cust.id,
                occurred_at=base - timedelta(hours=i),
                content=f"msg {i}",
            )

        r = await authed.get(
            f"{PREFIX}/customers/{cust.id}/interactions", params={"limit": 3}
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        assert len(data) == 3
        # Newest first.
        timestamps = [row["occurred_at"] for row in data]
        assert timestamps == sorted(timestamps, reverse=True)

    @pytest.mark.asyncio
    async def test_channel_filter(
        self, authed: AsyncClient, test_db: AsyncSession
    ):
        cust = await _seed_customer(test_db)
        await _seed_interaction(test_db, customer_id=cust.id, channel="sms")
        await _seed_interaction(
            test_db, customer_id=cust.id, channel="email", provider="brevo"
        )
        r = await authed.get(
            f"{PREFIX}/customers/{cust.id}/interactions",
            params={"channel": "email"},
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["channel"] == "email"


# ---------------------------------------------------------------------------
# Tests — GET /ai/interactions/hot (static route)
# ---------------------------------------------------------------------------
class TestHotInbox:
    @pytest.mark.asyncio
    async def test_sorted_by_score_desc(
        self, authed: AsyncClient, test_db: AsyncSession
    ):
        cust = await _seed_customer(test_db)
        await _seed_interaction(test_db, customer_id=cust.id, score=72)
        await _seed_interaction(test_db, customer_id=cust.id, score=95)
        await _seed_interaction(test_db, customer_id=cust.id, score=85)
        # Below threshold — should be excluded.
        await _seed_interaction(test_db, customer_id=cust.id, score=10)

        r = await authed.get(f"{PREFIX}/ai/interactions/hot")
        assert r.status_code == 200, r.text
        data = r.json()
        assert len(data) == 3
        scores = [row["hot_lead_score"] for row in data]
        assert scores == sorted(scores, reverse=True)
        assert min(scores) >= 70
        # customer_name comes from joined Customer row.
        assert all(row.get("customer_name") for row in data)

    @pytest.mark.asyncio
    async def test_static_route_does_not_match_dynamic(
        self, authed: AsyncClient, test_db: AsyncSession
    ):
        """Verify /ai/interactions/hot is matched as the static route, not
        as /ai/interactions/{interaction_id}. We pass it a request that would
        404 if it routed to the dynamic handler (since 'hot' isn't a UUID).
        """
        # Seed at least one hot row so we get a non-empty list.
        cust = await _seed_customer(test_db)
        await _seed_interaction(test_db, customer_id=cust.id, score=88)

        r = await authed.get(f"{PREFIX}/ai/interactions/hot")
        # Static route returns a list (200). If it hit the dynamic /{id} route,
        # the 'hot' string would 404 (UUID parse failure).
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---------------------------------------------------------------------------
# Tests — GET /ai/interactions/{id}
# ---------------------------------------------------------------------------
class TestInteractionDetail:
    @pytest.mark.asyncio
    async def test_returns_detail_with_action_items_and_latest_run(
        self, authed: AsyncClient, test_db: AsyncSession
    ):
        cust = await _seed_customer(test_db)
        inter = await _seed_interaction(
            test_db, customer_id=cust.id, score=88, content="emergency overflow"
        )
        # Two action items
        ai1 = InteractionActionItem(
            id=uuid_module.uuid4(),
            interaction_id=inter.id,
            action="Call customer back",
            owner="dannia",
            status="open",
        )
        ai2 = InteractionActionItem(
            id=uuid_module.uuid4(),
            interaction_id=inter.id,
            action="Quote pump-out",
            owner="dispatch",
            status="open",
        )
        test_db.add_all([ai1, ai2])
        await test_db.commit()

        # Two runs — newer should be returned as latest
        old = await _seed_run(
            test_db,
            inter.id,
            tier="triage",
            cost_usd=Decimal("0.01"),
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        new = await _seed_run(
            test_db,
            inter.id,
            tier="reply",
            cost_usd=Decimal("0.04"),
            created_at=datetime.now(timezone.utc),
        )

        r = await authed.get(f"{PREFIX}/ai/interactions/{inter.id}")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["id"] == str(inter.id)
        assert data["content"] == "emergency overflow"
        assert len(data["action_items"]) == 2
        assert data["latest_analysis_run"] is not None
        assert data["latest_analysis_run"]["tier"] == "reply"
        # IDs serialized as strings
        assert data["latest_analysis_run"]["id"] == str(new.id)

    @pytest.mark.asyncio
    async def test_404_on_unknown(self, authed: AsyncClient):
        r = await authed.get(
            f"{PREFIX}/ai/interactions/{uuid_module.uuid4()}"
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Tests — POST /ai/interactions/{id}/dismiss-hot
# ---------------------------------------------------------------------------
class TestDismissHot:
    @pytest.mark.asyncio
    async def test_clears_score_and_marks_dismissed(
        self, authed: AsyncClient, test_db: AsyncSession
    ):
        cust = await _seed_customer(test_db)
        inter = await _seed_interaction(
            test_db, customer_id=cust.id, score=92
        )

        r = await authed.post(
            f"{PREFIX}/ai/interactions/{inter.id}/dismiss-hot"
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["hot_lead_score"] == 0
        assert "dismissed_at" in data["raw_payload"]
        assert data["raw_payload"].get("dismissed_by_user_id") is not None

        # Subsequent GET reflects persistence
        r2 = await authed.get(f"{PREFIX}/ai/interactions/{inter.id}")
        assert r2.status_code == 200
        assert r2.json()["hot_lead_score"] == 0


# ---------------------------------------------------------------------------
# Tests — POST /ai/interactions/{id}/reanalyze
# ---------------------------------------------------------------------------
class TestReanalyze:
    @pytest.mark.asyncio
    async def test_reanalyze_enqueues_worker(
        self, authed: AsyncClient, test_db: AsyncSession
    ):
        cust = await _seed_customer(test_db)
        inter = await _seed_interaction(
            test_db, customer_id=cust.id, score=88, content="follow up please"
        )
        # Pretend it was already analyzed.
        inter.analysis_at = datetime.now(timezone.utc)
        await test_db.commit()

        with patch(
            "app.services.ai.queue.enqueue_interaction_analysis",
            new=AsyncMock(return_value=None),
        ) as mock_enqueue:
            r = await authed.post(
                f"{PREFIX}/ai/interactions/{inter.id}/reanalyze"
            )

        assert r.status_code in (200, 202), r.text
        body = r.json()
        assert body["status"] == "queued"
        assert body["interaction_id"] == str(inter.id)
        assert body["channel"] == inter.channel
        assert mock_enqueue.await_count == 1

        # analysis_at should be cleared so the worker freshness check fails.
        await test_db.refresh(inter)
        assert inter.analysis_at is None

    @pytest.mark.asyncio
    async def test_reanalyze_404_unknown(self, authed: AsyncClient):
        r = await authed.post(
            f"{PREFIX}/ai/interactions/{uuid_module.uuid4()}/reanalyze"
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Tests — GET /ai/budget
# ---------------------------------------------------------------------------
class TestBudget:
    @pytest.mark.asyncio
    async def test_returns_budget_summary_shape(
        self, authed: AsyncClient, test_db: AsyncSession
    ):
        cust = await _seed_customer(test_db)
        inter = await _seed_interaction(test_db, customer_id=cust.id, score=72)
        # One run today, ~$0.10
        await _seed_run(test_db, inter.id, cost_usd=Decimal("0.10"))

        r = await authed.get(f"{PREFIX}/ai/budget")
        assert r.status_code == 200, r.text
        data = r.json()
        # Required keys
        assert set(data.keys()) >= {
            "today_usd",
            "this_month_usd",
            "daily_cap_usd",
            "paused",
        }
        assert isinstance(data["today_usd"], (int, float))
        assert isinstance(data["this_month_usd"], (int, float))
        assert isinstance(data["daily_cap_usd"], (int, float))
        assert isinstance(data["paused"], bool)
        # Today's spend should reflect the seeded run.
        assert data["today_usd"] >= 0.10 - 1e-6
        assert data["this_month_usd"] >= 0.10 - 1e-6
