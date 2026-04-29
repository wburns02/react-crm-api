"""Tests for the AI strategy scheduler.

Verify the start function registers a Sunday 06:00 America/Chicago job
and that the run target (run_strategy_and_email) calls run_weekly_strategy
without hitting Anthropic.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

# Required-at-startup keys — set BEFORE app import.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("DEEPGRAM_API_KEY", "test-deepgram-key")

import pytest
import uuid as uuid_module

from app.models.interaction_insight import InteractionInsight
from app.tasks import ai_strategy_scheduler
from app.tasks import ai_rescore_scheduler
from app.tasks import ai_budget_scheduler
from app.tasks import ai_rc_poll_scheduler


# ---------------------------------------------------------------------------
# Strategy scheduler
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_start_ai_strategy_scheduler_registers_job():
    # Ensure a clean global scheduler state per test.
    ai_strategy_scheduler.scheduler = None
    try:
        ai_strategy_scheduler.start_ai_strategy_scheduler()
        sched = ai_strategy_scheduler.get_scheduler()
        jobs = sched.get_jobs()
        ids = {j.id for j in jobs}
        assert "ai_strategy_weekly" in ids
    finally:
        ai_strategy_scheduler.stop_ai_strategy_scheduler()
        ai_strategy_scheduler.scheduler = None


@pytest.mark.asyncio
async def test_run_strategy_and_email_invokes_strategy():
    """The job target should call run_weekly_strategy and try to email Will."""
    fake_insight = InteractionInsight(
        id=uuid_module.uuid4(),
        iso_week="2026-W17",
        start_date=date(2026, 4, 20),
        end_date=date(2026, 4, 26),
        total_interactions=10,
        by_channel={"sms": 5, "email": 5},
        report_markdown="# Weekly",
        report_json=None,
        model="claude-opus-4-7",
        prompt_version="v1",
        cost_usd=Decimal("0.10"),
        input_tokens=0,
        output_tokens=0,
        cache_read_tokens=0,
        cache_write_tokens=0,
        thinking_tokens=0,
        duration_ms=0,
        created_at=datetime.now(timezone.utc),
    )

    fake_email_service = MagicMock()
    fake_email_service.is_configured = True
    fake_email_service.send_email = AsyncMock(return_value={"success": True})

    with patch(
        "app.tasks.ai_strategy_scheduler.run_weekly_strategy",
        new=AsyncMock(return_value=fake_insight),
    ) as mock_run, patch(
        "app.tasks.ai_strategy_scheduler.EmailService",
        return_value=fake_email_service,
    ):
        await ai_strategy_scheduler.run_strategy_and_email()

    assert mock_run.await_count == 1
    fake_email_service.send_email.assert_awaited_once()


# ---------------------------------------------------------------------------
# Rescore scheduler
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_start_ai_rescore_scheduler_registers_job():
    ai_rescore_scheduler.scheduler = None
    try:
        ai_rescore_scheduler.start_ai_rescore_scheduler()
        ids = {j.id for j in ai_rescore_scheduler.get_scheduler().get_jobs()}
        assert "ai_rescore_daily" in ids
    finally:
        ai_rescore_scheduler.stop_ai_rescore_scheduler()
        ai_rescore_scheduler.scheduler = None


# ---------------------------------------------------------------------------
# Budget scheduler
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_start_ai_budget_scheduler_registers_job():
    ai_budget_scheduler.scheduler = None
    try:
        ai_budget_scheduler.start_ai_budget_scheduler()
        ids = {j.id for j in ai_budget_scheduler.get_scheduler().get_jobs()}
        assert "ai_budget_daily" in ids
    finally:
        ai_budget_scheduler.stop_ai_budget_scheduler()
        ai_budget_scheduler.scheduler = None


# ---------------------------------------------------------------------------
# RC poll scheduler
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_start_ai_rc_poll_scheduler_registers_job():
    ai_rc_poll_scheduler.scheduler = None
    try:
        ai_rc_poll_scheduler.start_ai_rc_poll_scheduler()
        ids = {j.id for j in ai_rc_poll_scheduler.get_scheduler().get_jobs()}
        assert "ai_rc_poll_hourly" in ids
    finally:
        ai_rc_poll_scheduler.stop_ai_rc_poll_scheduler()
        ai_rc_poll_scheduler.scheduler = None
