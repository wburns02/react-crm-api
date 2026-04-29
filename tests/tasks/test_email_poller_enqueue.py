"""
Tests for Email Poller -> AI Interaction Analyzer enqueue wiring.

Covers Stage 2 Builder D: ensure that for each new InboundEmail row created
by `poll_inbound_emails`, `enqueue_interaction_analysis` is fired with the
row's ID and channel="email"; that already-seen messages do NOT enqueue;
and that an enqueue failure does not crash the poll cycle.
"""

import asyncio
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
# Import only the models the email poller needs. The full app.models package
# pulls in Postgres-specific types (JSONB) that SQLite can't render, so we
# create only the subset of tables we need on the in-memory SQLite engine.
from app.models.inbound_email import InboundEmail
from app.models.customer import Customer  # noqa: F401  registers customers table
from app.tasks import email_poller


def _email_payload(msg_id: str, sender: str = "alice@example.com", name: str = "Alice") -> dict:
    """Build a fake MS365 Graph email payload.

    Note: SQLAlchemy's SQLite DateTime requires real datetime objects, not isoformat
    strings. The poller stores `received_at = email_data.get("receivedDateTime", ...)`
    verbatim, so we hand it a datetime here. Production MS365 returns an ISO string
    (Postgres TIMESTAMPTZ accepts both); this difference doesn't affect the wiring
    we're testing.
    """
    return {
        "id": msg_id,
        "subject": f"Subject for {msg_id}",
        "bodyPreview": f"Preview for {msg_id}",
        "receivedDateTime": datetime.utcnow(),
        "from": {"emailAddress": {"address": sender, "name": name}},
    }


@pytest_asyncio.fixture
async def poller_session_maker():
    """Patch app.tasks.email_poller.async_session_maker with an in-memory SQLite session maker."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Only create the tables relevant to the email poller (inbound_emails,
    # customers). The broader Base.metadata contains tables with PG-specific
    # types (JSONB) that SQLite can't render.
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[
                InboundEmail.__table__,
                Customer.__table__,
            ],
        )

    sessionmaker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    with patch.object(email_poller, "async_session_maker", sessionmaker):
        yield sessionmaker

    await engine.dispose()


async def _drain_pending_tasks():
    """Yield control so any asyncio.create_task() coroutines run to completion."""
    # Two passes: first to schedule, second to drain. Some create_task calls may
    # themselves schedule follow-up work.
    for _ in range(3):
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_enqueue_called_for_each_new_inbound_email(poller_session_maker):
    """For each new InboundEmail row, enqueue_interaction_analysis is called once with channel='email'."""
    emails = [_email_payload("msg-1"), _email_payload("msg-2", "bob@example.com", "Bob")]

    fake_enqueue = AsyncMock()

    with patch.object(email_poller.MS365EmailService, "is_configured", return_value=True), \
         patch.object(email_poller.MS365EmailService, "get_unread_emails", new=AsyncMock(return_value=emails)), \
         patch.object(email_poller.MS365EmailService, "mark_as_read", new=AsyncMock(return_value=True)), \
         patch("app.services.ai.queue.enqueue_interaction_analysis", new=fake_enqueue):

        await email_poller.poll_inbound_emails()
        await _drain_pending_tasks()

    # Verify rows landed in DB
    async with poller_session_maker() as db:
        from sqlalchemy import select
        rows = (await db.execute(select(InboundEmail))).scalars().all()
        assert len(rows) == 2
        row_ids = {r.id for r in rows}

    # Verify enqueue was called once per new row, with channel='email'
    assert fake_enqueue.await_count == 2
    called_ids = {call.args[0] for call in fake_enqueue.await_args_list}
    called_channels = {call.args[1] for call in fake_enqueue.await_args_list}
    assert called_ids == row_ids
    assert called_channels == {"email"}


@pytest.mark.asyncio
async def test_enqueue_not_called_for_duplicate_email(poller_session_maker):
    """Polling a message_id already in inbound_emails should NOT enqueue analysis."""
    # Pre-seed an existing InboundEmail row to trigger the dedup branch.
    existing_msg_id = "already-seen-1"
    async with poller_session_maker() as db:
        existing = InboundEmail(
            id=uuid.uuid4(),
            message_id=existing_msg_id,
            sender_email="seen@example.com",
            sender_name="Seen",
            subject="Old",
            body_preview="Old preview",
            received_at=datetime.utcnow(),
            action_taken="no_match",
        )
        db.add(existing)
        await db.commit()

    emails = [_email_payload(existing_msg_id, "seen@example.com", "Seen")]
    fake_enqueue = AsyncMock()

    with patch.object(email_poller.MS365EmailService, "is_configured", return_value=True), \
         patch.object(email_poller.MS365EmailService, "get_unread_emails", new=AsyncMock(return_value=emails)), \
         patch.object(email_poller.MS365EmailService, "mark_as_read", new=AsyncMock(return_value=True)), \
         patch("app.services.ai.queue.enqueue_interaction_analysis", new=fake_enqueue):

        await email_poller.poll_inbound_emails()
        await _drain_pending_tasks()

    # No new row should have been created (dedup hit)
    async with poller_session_maker() as db:
        from sqlalchemy import select
        rows = (await db.execute(select(InboundEmail))).scalars().all()
        assert len(rows) == 1  # only the pre-seeded one

    assert fake_enqueue.await_count == 0


@pytest.mark.asyncio
async def test_enqueue_failure_does_not_crash_poll_cycle(poller_session_maker):
    """If enqueue_interaction_analysis raises, the poll cycle still completes successfully."""
    emails = [_email_payload("msg-crash-1"), _email_payload("msg-crash-2", "eve@example.com", "Eve")]

    # Raising AsyncMock — every await raises. Wrapped in try/except inside the poller
    # via asyncio.create_task; the create_task call itself succeeds, but the coroutine
    # will raise when awaited. We additionally verify the poller's own try/except path
    # by patching create_task to raise synchronously for one call.
    raising_enqueue = AsyncMock(side_effect=RuntimeError("boom"))

    original_create_task = asyncio.create_task
    call_count = {"n": 0}

    def flaky_create_task(coro, *args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # Close the coroutine so we don't leak it, then raise to exercise
            # the poller's try/except around create_task.
            try:
                coro.close()
            except Exception:
                pass
            raise RuntimeError("create_task failed")
        return original_create_task(coro, *args, **kwargs)

    with patch.object(email_poller.MS365EmailService, "is_configured", return_value=True), \
         patch.object(email_poller.MS365EmailService, "get_unread_emails", new=AsyncMock(return_value=emails)), \
         patch.object(email_poller.MS365EmailService, "mark_as_read", new=AsyncMock(return_value=True)), \
         patch("app.services.ai.queue.enqueue_interaction_analysis", new=raising_enqueue), \
         patch.object(email_poller.asyncio, "create_task", side_effect=flaky_create_task):

        # Should NOT raise
        await email_poller.poll_inbound_emails()
        await _drain_pending_tasks()

    # Both rows should still be persisted — DB commit happens before enqueue
    async with poller_session_maker() as db:
        from sqlalchemy import select
        rows = (await db.execute(select(InboundEmail))).scalars().all()
        assert len(rows) == 2
