"""
Stage 2 Builder B — Twilio webhook rewire tests.

Verifies:
1. /recording-status enqueues the new analyzer worker (channel="call") and does
   NOT call the legacy `analyze_call` service.
2. /incoming for an inbound SMS reply creates a Message row, then enqueues the
   new analyzer worker (channel="sms").
3. Bad Twilio signatures on either endpoint return 403.
"""
from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure required-at-startup env vars are set before importing app modules.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("DEEPGRAM_API_KEY", "test-deepgram-key")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test-twilio-auth-token")

import pytest
import pytest_asyncio
from fastapi import HTTPException
from httpx import AsyncClient, ASGITransport

from app.main import app as fastapi_app
from app.security.twilio_validator import validate_twilio_signature


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeSessionCM:
    """Async context manager that yields a mock DB session."""

    def __init__(self, session: MagicMock):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _make_db_session(scalar_one_or_none_returns):
    """Build a mock AsyncSession whose execute().scalar_one_or_none() returns the
    given values (one per call) and supports add/commit/refresh.
    """
    session = MagicMock()

    # Each call to db.execute(...) returns a result whose
    # .scalar_one_or_none() yields the next pre-programmed value.
    results = list(scalar_one_or_none_returns)

    async def _execute(*_args, **_kwargs):
        result = MagicMock()
        if results:
            result.scalar_one_or_none = MagicMock(return_value=results.pop(0))
        else:
            result.scalar_one_or_none = MagicMock(return_value=None)
        # scalars() iterator (used by /voice handler — not needed here, but safe)
        result.scalars = MagicMock(return_value=iter([]))
        return result

    session.execute = AsyncMock(side_effect=_execute)
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _override_signature_valid(value: bool):
    """Build a dependency override for validate_twilio_signature."""
    if value:
        async def ok():
            return True
        return ok

    async def bad():
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    return bad


@pytest_asyncio.fixture
async def http_client():
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    fastapi_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# /recording-status — replaces legacy analyze_call with new enqueue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recording_status_enqueues_new_worker_and_skips_legacy(http_client):
    """POST /recording-status (valid sig) → enqueue_interaction_analysis(channel="call")
    is called, legacy analyze_call is NEVER called."""
    fastapi_app.dependency_overrides[validate_twilio_signature] = _override_signature_valid(True)

    fake_call_log = MagicMock()
    fake_call_log.id = uuid.uuid4()
    fake_call_log.recording_url = None
    fake_call_log.duration_seconds = None
    fake_call_log.transcription_status = None

    db = _make_db_session([fake_call_log])

    enqueue_mock = AsyncMock()
    legacy_mock = AsyncMock()

    with patch("app.webhooks.twilio.async_session_maker", return_value=_FakeSessionCM(db)), \
         patch("app.webhooks.twilio.enqueue_interaction_analysis", new=enqueue_mock), \
         patch("app.services.call_analysis_service.analyze_call", new=legacy_mock), \
         patch("app.webhooks.twilio.settings") as mock_settings:
        mock_settings.VOICE_AI_ENABLED = True

        resp = await http_client.post(
            "/webhooks/twilio/recording-status",
            data={
                "RecordingUrl": "https://api.twilio.com/recording/RE123.mp3",
                "RecordingDuration": "42",
                "CallSid": "CA" + "f" * 32,
            },
        )

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}

    # New worker enqueued exactly once with channel="call" and the call_log UUID
    enqueue_mock.assert_awaited_once()
    args, kwargs = enqueue_mock.call_args
    assert args[0] == fake_call_log.id
    assert args[1] == "call"

    # Legacy analyze_call must NEVER be invoked
    legacy_mock.assert_not_called()
    legacy_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_recording_status_bad_signature_returns_403(http_client):
    """POST /recording-status (bad sig) → 403."""
    fastapi_app.dependency_overrides[validate_twilio_signature] = _override_signature_valid(False)

    resp = await http_client.post(
        "/webhooks/twilio/recording-status",
        data={"RecordingUrl": "x", "CallSid": "CA1"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_recording_status_skips_enqueue_when_voice_ai_disabled(http_client):
    """Sanity: with VOICE_AI_ENABLED=False, neither the new worker nor the
    legacy service should be touched."""
    fastapi_app.dependency_overrides[validate_twilio_signature] = _override_signature_valid(True)

    fake_call_log = MagicMock()
    fake_call_log.id = uuid.uuid4()
    db = _make_db_session([fake_call_log])

    enqueue_mock = AsyncMock()
    legacy_mock = AsyncMock()

    with patch("app.webhooks.twilio.async_session_maker", return_value=_FakeSessionCM(db)), \
         patch("app.webhooks.twilio.enqueue_interaction_analysis", new=enqueue_mock), \
         patch("app.services.call_analysis_service.analyze_call", new=legacy_mock), \
         patch("app.webhooks.twilio.settings") as mock_settings:
        mock_settings.VOICE_AI_ENABLED = False

        resp = await http_client.post(
            "/webhooks/twilio/recording-status",
            data={
                "RecordingUrl": "https://api.twilio.com/recording/RE123.mp3",
                "RecordingDuration": "42",
                "CallSid": "CA" + "f" * 32,
            },
        )

    assert resp.status_code == 200
    enqueue_mock.assert_not_awaited()
    legacy_mock.assert_not_awaited()


# ---------------------------------------------------------------------------
# /incoming — fan-out inbound SMS to new analyzer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_incoming_sms_react_reply_enqueues_analyzer(http_client):
    """POST /incoming with valid sig + inbound SMS that's a reply to a React
    message → Message row is added, committed, and enqueue_interaction_analysis
    is called with channel="sms"."""
    fastapi_app.dependency_overrides[validate_twilio_signature] = _override_signature_valid(True)

    # Last message lookup returns a React-sourced message → triggers the
    # "React reply" branch (which creates the inbound row + enqueues).
    last_msg = MagicMock()
    last_msg.source = "react"
    last_msg.customer_id = uuid.uuid4()

    db = _make_db_session([last_msg])

    # Patch Message.__init__ so we can capture kwargs and inject a real UUID
    # for the new row's id (the rewire passes incoming.id to the analyzer
    # queue, and we don't want SQLAlchemy ORM machinery in this unit test).
    from app.webhooks.twilio import Message as _RealMessage
    from app.models.message import MessageType as _MessageType

    incoming_id = uuid.uuid4()
    captured_kwargs: dict = {}

    def _fake_init(self, **kwargs):
        captured_kwargs.update(kwargs)
        # Bypass SQLAlchemy column descriptor on `id` by writing straight to
        # __dict__. The handler reads incoming.id via attribute access — for a
        # SQLAlchemy column, instance __dict__ takes precedence over the
        # column's default-from-descriptor lookup, so this works.
        self.__dict__["id"] = incoming_id

    # Make db.flush() populate incoming.id (in real code, autogenerate kicks in
    # at flush time; the fake __init__ above already sets it, so flush is a no-op).
    enqueue_mock = AsyncMock()

    with patch("app.webhooks.twilio.async_session_maker", return_value=_FakeSessionCM(db)), \
         patch.object(_RealMessage, "__init__", _fake_init), \
         patch("app.webhooks.twilio.enqueue_interaction_analysis", new=enqueue_mock):
        # db.flush is referenced by the handler post-rewire
        db.flush = AsyncMock()

        resp = await http_client.post(
            "/webhooks/twilio/incoming",
            data={
                "MessageSid": "SM" + "a" * 32,
                "From": "+15551234567",
                "To": "+15559876543",
                "Body": "Hello, this is a reply",
            },
        )

    assert resp.status_code == 200
    # TwiML response (XML)
    assert "Response" in resp.text

    # Message constructor uses real columns (Bug 2 fix): message_type=,
    # to_number=, from_number=, external_id= — NOT the read-only properties.
    assert captured_kwargs.get("direction") == "inbound"
    assert captured_kwargs.get("message_type") == _MessageType.sms
    assert captured_kwargs.get("to_number") == "+15559876543"
    assert captured_kwargs.get("from_number") == "+15551234567"
    assert captured_kwargs.get("external_id") == "SM" + "a" * 32
    # Read-only property kwargs MUST NOT appear (would AttributeError at runtime)
    assert "type" not in captured_kwargs
    assert "to_address" not in captured_kwargs
    assert "from_address" not in captured_kwargs
    assert "twilio_sid" not in captured_kwargs
    assert "source" not in captured_kwargs

    # Row was added + committed (commit MUST happen before enqueue)
    db.add.assert_called_once()
    db.commit.assert_awaited_once()

    # Analyzer was enqueued with the new message's id and channel="sms"
    enqueue_mock.assert_awaited_once()
    args, _kwargs = enqueue_mock.call_args
    assert args[0] == incoming_id
    assert args[1] == "sms"


@pytest.mark.asyncio
async def test_incoming_sms_legacy_branch_does_not_enqueue(http_client):
    """If the inbound SMS is NOT a React reply, the handler forwards to legacy
    and must NOT enqueue the analyzer."""
    fastapi_app.dependency_overrides[validate_twilio_signature] = _override_signature_valid(True)

    # No matching last message → falls into the "forward to legacy" branch.
    db = _make_db_session([None])

    enqueue_mock = AsyncMock()

    # Mock httpx.AsyncClient so we don't hit the network.
    fake_response = MagicMock()
    fake_response.content = b'<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
    fake_response.status_code = 200
    fake_response.headers = {"content-type": "application/xml"}

    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=False)
    fake_client.post = AsyncMock(return_value=fake_response)

    with patch("app.webhooks.twilio.async_session_maker", return_value=_FakeSessionCM(db)), \
         patch("app.webhooks.twilio.httpx.AsyncClient", return_value=fake_client), \
         patch("app.webhooks.twilio.enqueue_interaction_analysis", new=enqueue_mock):
        resp = await http_client.post(
            "/webhooks/twilio/incoming",
            data={
                "MessageSid": "SM" + "b" * 32,
                "From": "+15551234567",
                "To": "+15559876543",
                "Body": "unsolicited",
            },
        )

    assert resp.status_code == 200
    enqueue_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_incoming_sms_bad_signature_returns_403(http_client):
    """POST /incoming with bad sig → 403 and no enqueue."""
    fastapi_app.dependency_overrides[validate_twilio_signature] = _override_signature_valid(False)

    enqueue_mock = AsyncMock()
    with patch("app.webhooks.twilio.enqueue_interaction_analysis", new=enqueue_mock):
        resp = await http_client.post(
            "/webhooks/twilio/incoming",
            data={
                "MessageSid": "SM1",
                "From": "+15551234567",
                "To": "+15559876543",
                "Body": "hi",
            },
        )

    assert resp.status_code == 403
    enqueue_mock.assert_not_awaited()
