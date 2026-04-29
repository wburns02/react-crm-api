"""Daily 08:00 America/Chicago — re-score open hot leads.

Looks at every interaction with hot_lead_score >= 70 that has NOT been
dismissed and that we have not followed up on in the last 24 hours, and
bumps the priority by writing a `priority_bump_at` flag into raw_payload.
This is a lightweight signal the Hot Leads inbox can use to re-rank stale
items above newer-but-quieter leads.

We deliberately do not re-call any LLM here — re-scoring is a stale-flag
nudge, not a re-analysis. (POST /ai/interactions/{id}/reanalyze is the
hook for full re-analysis.)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.database import async_session_maker
from app.models.customer_interaction import CustomerInteraction

logger = logging.getLogger(__name__)


scheduler: Optional[AsyncIOScheduler] = None
HOT_THRESHOLD = 70
STALE_HOURS = 24


def get_scheduler() -> AsyncIOScheduler:
    global scheduler
    if scheduler is None:
        scheduler = AsyncIOScheduler()
    return scheduler


async def rescore_stale_hot_leads() -> None:
    """Job target: bump priority on stale (>24h, no follow-up) hot leads."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=STALE_HOURS)
    bumped = 0

    try:
        async with async_session_maker() as db:
            stmt = (
                select(CustomerInteraction)
                .where(CustomerInteraction.hot_lead_score >= HOT_THRESHOLD)
                .where(CustomerInteraction.do_not_contact == False)  # noqa: E712
                .where(CustomerInteraction.occurred_at <= cutoff)
            )
            rows = (await db.execute(stmt)).scalars().all()

            for row in rows:
                raw = dict(row.raw_payload or {})
                # Skip already-dismissed leads
                if raw.get("dismissed_at"):
                    continue
                last_bump_iso = raw.get("priority_bump_at")
                if last_bump_iso:
                    try:
                        last_bump = datetime.fromisoformat(last_bump_iso)
                        if last_bump.tzinfo is None:
                            last_bump = last_bump.replace(tzinfo=timezone.utc)
                        if datetime.now(timezone.utc) - last_bump < timedelta(
                            hours=STALE_HOURS
                        ):
                            continue
                    except (ValueError, TypeError):
                        pass

                raw["priority_bump_at"] = datetime.now(timezone.utc).isoformat()
                row.raw_payload = raw
                # Soft tag (CSV) so the UI can show "stale" badges.
                bumps = int(raw.get("priority_bumps", 0) or 0) + 1
                raw["priority_bumps"] = bumps
                bumped += 1
                logger.info(
                    "ai_rescore: bumped stale hot lead %s (score=%s bumps=%d)",
                    row.id,
                    row.hot_lead_score,
                    bumps,
                )

            await db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("ai_rescore: job failed")
        return

    logger.info("ai_rescore: completed — %d hot leads bumped", bumped)


def start_ai_rescore_scheduler() -> None:
    sched = get_scheduler()
    sched.add_job(
        rescore_stale_hot_leads,
        CronTrigger(
            hour=8,
            minute=0,
            timezone="America/Chicago",
        ),
        id="ai_rescore_daily",
        name="AI daily hot-lead re-score",
        replace_existing=True,
    )
    if not sched.running:
        sched.start()
        logger.info("ai_rescore_scheduler started — daily 08:00 America/Chicago")


def stop_ai_rescore_scheduler() -> None:
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("ai_rescore_scheduler stopped")


__all__ = [
    "start_ai_rescore_scheduler",
    "stop_ai_rescore_scheduler",
    "rescore_stale_hot_leads",
]
