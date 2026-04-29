"""Tests for /webhooks/ringcentral/calls — RingCentral call recording handler.

Covers Stage 2 of the AI Interaction Analyzer: webhook ingestion and
fan-out into enqueue_interaction_analysis.

Test isolation note: the project's `test_db` fixture (in conftest.py) calls
`Base.metadata.create_all` against in-memory SQLite, which fails because the
broader model graph contains Postgres-specific types (JSONB) that SQLite
can't render. To avoid that pre-existing infrastructure issue, this test
file builds its own engine with ONLY the two tables we need: `customers`
and `call_logs`. The webhook's `async_session_maker` symbol is patched to
return sessions bound to that engine.
"""

from __future__ import annotations

import os

# Required-at-startup keys for the AI Interaction Analyzer (Stage 1).
# Set BEFORE importing app.config / app.main so Settings validation passes.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("DEEPGRAM_API_KEY", "test-deepgram-key")

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.main import app as fastapi_app
from app.models.call_log import CallLog
from app.models.customer import Customer
from app.webhooks import ringcentral as ringcentral_webhook


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def patched_session_maker():
    """In-memory SQLite engine with ONLY customers + call_logs tables.

    Patches `app.webhooks.ringcentral.async_session_maker` to point at this
    engine for the duration of the test, so the production handler's
    `async with async_session_maker() as db:` block uses our test DB.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[Customer.__table__, CallLog.__table__],
        )

    sessionmaker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    with patch.object(ringcentral_webhook, "async_session_maker", sessionmaker):
        yield sessionmaker

    await engine.dispose()


@pytest_asyncio.fixture
async def http_client():
    """Bare httpx client against the FastAPI app — no auth, no DB override.

    The /calls webhook is unauthenticated (RC handshake + signed body).
    """
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------


def _recording_event(
    rc_id: str = "rc-call-12345",
    *,
    direction: str = "Inbound",
    from_number: str = "+15125551111",
    to_number: str = "+15125559999",
    duration: int = 42,
    start_time: str = "2026-04-27T18:30:00.000Z",
    recording_uri: str = "https://media.ringcentral.com/recording/abc.mp3",
    session_id: str = "rc-sess-99",
) -> dict:
    """Build a synthetic RingCentral call-log recording event payload."""
    return {
        "event": "/restapi/v1.0/account/~/extension/~/call-log",
        "body": {
            "id": rc_id,
            "sessionId": session_id,
            "direction": direction,
            "from": {"phoneNumber": from_number},
            "to": {"phoneNumber": to_number},
            "duration": duration,
            "startTime": start_time,
            "recording": {
                "id": "rec-1",
                "contentUri": recording_uri,
                "type": "Automatic",
            },
        },
    }


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validation_token_handshake(http_client: AsyncClient):
    """Validation-Token header must be echoed in the response."""
    token = "abc123-handshake-token"
    response = await http_client.post(
        "/webhooks/ringcentral/calls",
        headers={"Validation-Token": token},
    )
    assert response.status_code == 200
    assert response.headers.get("Validation-Token") == token


@pytest.mark.asyncio
async def test_recording_event_inserts_call_log_and_enqueues(
    http_client: AsyncClient,
    patched_session_maker,
):
    """A recording-completed event creates a call_logs row and fires the queue."""
    rc_id = "rc-call-INSERT-1"
    payload = _recording_event(rc_id=rc_id)

    with patch.object(
        ringcentral_webhook,
        "enqueue_interaction_analysis",
        new=AsyncMock(),
    ) as mock_enqueue:
        response = await http_client.post(
            "/webhooks/ringcentral/calls", json=payload
        )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "ok"
    assert "call_log_id" in data

    # Row exists in DB
    async with patched_session_maker() as db:
        result = await db.execute(
            select(CallLog).where(CallLog.ringcentral_call_id == rc_id)
        )
        rows = result.scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.external_system == "ringcentral"
    assert row.direction == "inbound"
    assert row.call_type == "voice"
    assert row.caller_number == "+15125551111"
    assert row.called_number == "+15125559999"
    assert row.duration_seconds == 42
    assert row.recording_url == "https://media.ringcentral.com/recording/abc.mp3"
    assert row.transcription_status == "pending"

    # Worker enqueue called exactly once with channel="call"
    assert mock_enqueue.await_count == 1
    args, _kwargs = mock_enqueue.await_args
    assert args[1] == "call"
    assert args[0] == row.id


@pytest.mark.asyncio
async def test_idempotency_same_event_twice_yields_one_row(
    http_client: AsyncClient,
    patched_session_maker,
):
    """Firing the same event twice must not create duplicate call_logs rows."""
    rc_id = "rc-call-IDEMP-2"
    payload = _recording_event(rc_id=rc_id)

    with patch.object(
        ringcentral_webhook,
        "enqueue_interaction_analysis",
        new=AsyncMock(),
    ):
        first = await http_client.post(
            "/webhooks/ringcentral/calls", json=payload
        )
        second = await http_client.post(
            "/webhooks/ringcentral/calls", json=payload
        )

    assert first.status_code == 200
    assert second.status_code == 200

    async with patched_session_maker() as db:
        result = await db.execute(
            select(CallLog).where(CallLog.ringcentral_call_id == rc_id)
        )
        rows = result.scalars().all()
    assert len(rows) == 1, f"Expected exactly one row, got {len(rows)}"

    # Both responses point at the same call_log_id
    assert first.json()["call_log_id"] == second.json()["call_log_id"]


@pytest.mark.asyncio
async def test_customer_match_by_last10_digit_phone(
    http_client: AsyncClient,
    patched_session_maker,
):
    """Customer with stored phone in (XXX) XXX-XXXX format must match
    a RC payload caller in +1XXXXXXXXXX format via last-10-digit normalization."""
    # Insert a customer whose phone matches the inbound caller.
    cust_id = uuid.uuid4()
    async with patched_session_maker() as db:
        cust = Customer(
            id=cust_id,
            first_name="Aria",
            last_name="Tester",
            phone="(512) 555-1111",
        )
        db.add(cust)
        await db.commit()

    rc_id = "rc-call-CUSTMATCH-3"
    payload = _recording_event(
        rc_id=rc_id,
        direction="Inbound",
        from_number="+15125551111",  # last 10 = 5125551111 — matches (512) 555-1111
        to_number="+15125559999",
    )

    with patch.object(
        ringcentral_webhook,
        "enqueue_interaction_analysis",
        new=AsyncMock(),
    ):
        response = await http_client.post(
            "/webhooks/ringcentral/calls", json=payload
        )

    assert response.status_code == 200, response.text

    async with patched_session_maker() as db:
        result = await db.execute(
            select(CallLog).where(CallLog.ringcentral_call_id == rc_id)
        )
        row = result.scalar_one()
    assert row.customer_id == cust_id


@pytest.mark.asyncio
async def test_non_recording_event_returns_ignored(http_client: AsyncClient):
    """Events that aren't call-log/recording payloads are ignored with 200."""
    payload = {
        "event": "/restapi/v1.0/account/~/extension/~/message-store",
        "body": {"id": "irrelevant", "direction": "Inbound", "type": "SMS"},
    }
    response = await http_client.post(
        "/webhooks/ringcentral/calls", json=payload
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ignored"


@pytest.mark.asyncio
async def test_call_log_event_without_recording_block_is_ignored(
    http_client: AsyncClient,
):
    """A call-log event with no recording attached should be ignored, not stored."""
    payload = {
        "event": "/restapi/v1.0/account/~/extension/~/call-log",
        "body": {
            "id": "rc-call-NO-REC",
            "direction": "Inbound",
            "from": {"phoneNumber": "+15125551111"},
            "to": {"phoneNumber": "+15125559999"},
            "duration": 0,
            # no `recording` key
        },
    }
    response = await http_client.post(
        "/webhooks/ringcentral/calls", json=payload
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"
