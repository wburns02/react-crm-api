"""Hourly RingCentral missed-recording poller.

RingCentral webhooks occasionally drop call.recording.completed events.
This job polls the RC call-log API for the last ~90 minutes of recordings
and enqueues analysis for any whose recording is not yet linked to a
``customer_interactions`` row (matched by ``external_id``).

The existing RC client lives at ``app.services.ringcentral_service`` —
``RingCentralService.get_call_log()`` returns recordings inline.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from app.database import async_session_maker
from app.models.call_log import CallLog
from app.models.customer_interaction import CustomerInteraction
from app.services.ai.queue import enqueue_interaction_analysis
from app.services.ringcentral_service import RingCentralService

logger = logging.getLogger(__name__)


scheduler: Optional[AsyncIOScheduler] = None
POLL_LOOKBACK_MINUTES = 90


def get_scheduler() -> AsyncIOScheduler:
    global scheduler
    if scheduler is None:
        scheduler = AsyncIOScheduler()
    return scheduler


async def poll_missed_recordings() -> None:
    """Job target: backstop dropped RC recording webhooks."""
    rc = RingCentralService()
    if not rc.is_configured:
        logger.debug("ai_rc_poll: RC not configured — skipping")
        return

    date_to = datetime.now(timezone.utc)
    date_from = date_to - timedelta(minutes=POLL_LOOKBACK_MINUTES)

    try:
        result = await rc.get_call_log(
            date_from=date_from,
            date_to=date_to,
            call_type="Voice",
            per_page=100,
        )
    except Exception:  # noqa: BLE001
        logger.exception("ai_rc_poll: RC call-log fetch failed")
        return
    finally:
        try:
            await rc.close()
        except Exception:  # noqa: BLE001
            pass

    records = (result or {}).get("records") or []
    if not records:
        logger.debug("ai_rc_poll: no records in last %dm", POLL_LOOKBACK_MINUTES)
        return

    enqueued = 0
    skipped = 0

    async with async_session_maker() as db:
        for record in records:
            recording = (record or {}).get("recording")
            if not recording:
                continue

            rc_call_id = str(record.get("id") or record.get("sessionId") or "")
            if not rc_call_id:
                continue

            external_id = f"call:{rc_call_id}"
            existing = (
                await db.execute(
                    select(CustomerInteraction).where(
                        CustomerInteraction.external_id == external_id
                    )
                )
            ).scalar_one_or_none()
            if existing is not None and existing.analysis_at is not None:
                skipped += 1
                continue

            # Find the corresponding CallLog row (Stage 2A's webhook upserts it).
            call_log = (
                await db.execute(
                    select(CallLog).where(CallLog.ringcentral_call_id == rc_call_id)
                )
            ).scalar_one_or_none()
            if call_log is None:
                logger.info(
                    "ai_rc_poll: RC call %s has recording but no CallLog — skipping",
                    rc_call_id,
                )
                skipped += 1
                continue

            try:
                await enqueue_interaction_analysis(call_log.id, "call")
                enqueued += 1
            except Exception:  # noqa: BLE001
                logger.exception(
                    "ai_rc_poll: enqueue failed for call_log %s", call_log.id
                )

    logger.info(
        "ai_rc_poll: complete — enqueued=%d skipped=%d", enqueued, skipped
    )


def start_ai_rc_poll_scheduler() -> None:
    sched = get_scheduler()
    sched.add_job(
        poll_missed_recordings,
        IntervalTrigger(hours=1),
        id="ai_rc_poll_hourly",
        name="AI RC missed-recording poll",
        replace_existing=True,
    )
    if not sched.running:
        sched.start()
        logger.info("ai_rc_poll_scheduler started — every 1h")


def stop_ai_rc_poll_scheduler() -> None:
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("ai_rc_poll_scheduler stopped")


__all__ = [
    "start_ai_rc_poll_scheduler",
    "stop_ai_rc_poll_scheduler",
    "poll_missed_recordings",
]
