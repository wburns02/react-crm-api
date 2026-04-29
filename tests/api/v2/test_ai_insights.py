"""Tests for the Weekly AI Insights endpoints (Stage 5).

Endpoints under test:
  GET  /api/v2/ai/insights/recent
  GET  /api/v2/ai/insights/weekly?week=...
  POST /api/v2/ai/insights/weekly/refresh
"""
from __future__ import annotations

import os
import uuid as uuid_module
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

# Required-at-startup keys — set BEFORE app import.
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


# SQLite type shims (test-only).
if not hasattr(SQLiteTypeCompiler, "_ai_insights_shim_installed"):
    def visit_JSONB(self, type_, **kw):  # noqa: N802
        return "JSON"

    def visit_UUID(self, type_, **kw):  # noqa: N802
        return "CHAR(36)"

    def visit_ENUM(self, type_, **kw):  # noqa: N802
        return "VARCHAR(50)"

    SQLiteTypeCompiler.visit_JSONB = visit_JSONB
    SQLiteTypeCompiler.visit_UUID = visit_UUID
    SQLiteTypeCompiler.visit_ENUM = visit_ENUM
    SQLiteTypeCompiler._ai_insights_shim_installed = True  # type: ignore[attr-defined]


# Coerce SQLAlchemy Uuid bind processor to accept str inputs from path params.
import uuid as _uuid_for_patch
from sqlalchemy.sql import sqltypes as _sqltypes

if not getattr(_sqltypes.Uuid, "_ai_insights_str_patch", False):
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
    _sqltypes.Uuid._ai_insights_str_patch = True  # type: ignore[attr-defined]


from app.api.deps import create_access_token, get_password_hash
from app.database import Base, get_db
from app.main import app as fastapi_app
from app.models.customer_interaction import (
    CustomerInteraction,
    InteractionAnalysisRun,
)
from app.models.interaction_insight import InteractionInsight
from app.models.user import User


PREFIX = "/api/v2"

_TABLES = [
    User.__table__,
    CustomerInteraction.__table__,
    InteractionAnalysisRun.__table__,
    InteractionInsight.__table__,
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


@pytest_asyncio.fixture
async def admin_user(test_db: AsyncSession) -> User:
    user = User(
        email="admin@example.com",
        hashed_password=get_password_hash("testpw1234"),
        first_name="Admin",
        last_name="User",
        is_active=True,
        is_admin=True,
    )
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)
    return user


@pytest_asyncio.fixture
async def regular_user(test_db: AsyncSession) -> User:
    user = User(
        email="regular@example.com",
        hashed_password=get_password_hash("testpw1234"),
        first_name="Reg",
        last_name="User",
        is_active=True,
        is_admin=False,
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


def _auth(client: AsyncClient, user: User) -> AsyncClient:
    token = create_access_token(data={"sub": str(user.id), "email": user.email})
    client.headers["Authorization"] = f"Bearer {token}"
    return client


async def _seed_insight(db: AsyncSession, *, iso_week: str = "2026-W17") -> InteractionInsight:
    row = InteractionInsight(
        id=uuid_module.uuid4(),
        iso_week=iso_week,
        start_date=date(2026, 4, 20),
        end_date=date(2026, 4, 26),
        total_interactions=5,
        by_channel={"sms": 3, "email": 2},
        report_markdown="# Test\n\nSomething.",
        report_json=None,
        model="claude-opus-4-7",
        prompt_version="v1",
        cost_usd=Decimal("0.0123"),
        input_tokens=1000,
        output_tokens=400,
        cache_read_tokens=200,
        cache_write_tokens=50,
        thinking_tokens=300,
        duration_ms=1500,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_recent_requires_auth(client: AsyncClient):
    resp = await client.get(f"{PREFIX}/ai/insights/recent")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_weekly_requires_auth(client: AsyncClient):
    resp = await client.get(f"{PREFIX}/ai/insights/weekly")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_requires_auth(client: AsyncClient):
    resp = await client.post(f"{PREFIX}/ai/insights/weekly/refresh", json={})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /weekly
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_weekly_returns_existing(
    client: AsyncClient, regular_user: User, test_db: AsyncSession
):
    await _seed_insight(test_db, iso_week="2026-W17")
    _auth(client, regular_user)

    resp = await client.get(f"{PREFIX}/ai/insights/weekly?week=2026-W17")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["iso_week"] == "2026-W17"
    assert data["total_interactions"] == 5
    assert data["report_markdown"].startswith("# Test")


@pytest.mark.asyncio
async def test_get_weekly_404_when_missing(
    client: AsyncClient, regular_user: User
):
    _auth(client, regular_user)
    resp = await client.get(f"{PREFIX}/ai/insights/weekly?week=2025-W01")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_weekly_400_on_bad_week(
    client: AsyncClient, regular_user: User
):
    _auth(client, regular_user)
    resp = await client.get(f"{PREFIX}/ai/insights/weekly?week=garbage")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /recent
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_recent_returns_list(
    client: AsyncClient, regular_user: User, test_db: AsyncSession
):
    await _seed_insight(test_db, iso_week="2026-W16")
    await _seed_insight(test_db, iso_week="2026-W17")
    _auth(client, regular_user)

    resp = await client.get(f"{PREFIX}/ai/insights/recent")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 2
    weeks = {row["iso_week"] for row in data}
    assert weeks == {"2026-W16", "2026-W17"}


# ---------------------------------------------------------------------------
# POST /weekly/refresh — admin gate
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_refresh_forbidden_for_non_admin(
    client: AsyncClient, regular_user: User
):
    _auth(client, regular_user)
    resp = await client.post(
        f"{PREFIX}/ai/insights/weekly/refresh", json={"week": "2026-W17"}
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_refresh_admin_calls_strategy(
    client: AsyncClient, admin_user: User, test_db: AsyncSession
):
    """The endpoint should invoke run_weekly_strategy with force=True."""
    _auth(client, admin_user)

    fake_insight = InteractionInsight(
        id=uuid_module.uuid4(),
        iso_week="2026-W17",
        start_date=date(2026, 4, 20),
        end_date=date(2026, 4, 26),
        total_interactions=0,
        by_channel={},
        report_markdown="# Refreshed",
        report_json=None,
        model="claude-opus-4-7",
        prompt_version="v1",
        cost_usd=Decimal("0"),
        input_tokens=0,
        output_tokens=0,
        cache_read_tokens=0,
        cache_write_tokens=0,
        thinking_tokens=0,
        duration_ms=0,
        created_at=datetime.now(timezone.utc),
    )

    with patch(
        "app.api.v2.ai_insights.run_weekly_strategy",
        new=AsyncMock(return_value=fake_insight),
    ) as mock_run:
        resp = await client.post(
            f"{PREFIX}/ai/insights/weekly/refresh", json={"week": "2026-W17"}
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "ok"
    assert data["week"] == "2026-W17"
    assert data["insight"]["iso_week"] == "2026-W17"
    assert mock_run.await_count == 1
    # force=True must be passed
    _, kwargs = mock_run.call_args
    assert kwargs.get("force") is True
