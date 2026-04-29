"""Daily 00:05 UTC — yesterday's AI spend report.

Sums ``interaction_analysis_runs.cost_usd`` from the previous UTC day. If
the total exceeds the alert threshold (default $5), emails Will. The job
is idempotent within a single Python process via an in-memory date guard
(prevents double-send on schedule reload).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import func, select

from app.config import settings
from app.database import async_session_maker
from app.models.customer_interaction import InteractionAnalysisRun
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)


scheduler: Optional[AsyncIOScheduler] = None
ALERT_THRESHOLD_USD_DEFAULT = Decimal("5.00")
_last_alert_date: dict[str, str | None] = {"date": None}


def get_scheduler() -> AsyncIOScheduler:
    global scheduler
    if scheduler is None:
        scheduler = AsyncIOScheduler()
    return scheduler


def _alert_threshold_usd() -> Decimal:
    raw = getattr(settings, "AI_DAILY_ALERT_USD", None)
    if raw is None:
        return ALERT_THRESHOLD_USD_DEFAULT
    try:
        return Decimal(str(raw))
    except Exception:  # noqa: BLE001
        return ALERT_THRESHOLD_USD_DEFAULT


async def report_yesterday_spend() -> None:
    """Job target: report yesterday's AI spend to Will if over threshold."""
    today_utc = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    yesterday_start = today_utc - timedelta(days=1)
    yesterday_end = today_utc
    yesterday_iso = yesterday_start.date().isoformat()

    if _last_alert_date["date"] == yesterday_iso:
        logger.info(
            "ai_budget: already reported for %s — skipping", yesterday_iso
        )
        return

    try:
        async with async_session_maker() as db:
            stmt = select(
                func.coalesce(func.sum(InteractionAnalysisRun.cost_usd), 0)
            ).where(
                InteractionAnalysisRun.created_at >= yesterday_start,
                InteractionAnalysisRun.created_at < yesterday_end,
            )
            raw = (await db.execute(stmt)).scalar() or 0
            spend = Decimal(str(raw))
    except Exception:  # noqa: BLE001
        logger.exception("ai_budget: failed to compute yesterday's spend")
        return

    threshold = _alert_threshold_usd()
    logger.info(
        "ai_budget: yesterday=%s spend=$%.4f threshold=$%.2f",
        yesterday_iso,
        float(spend),
        float(threshold),
    )

    if spend <= threshold:
        return

    recipient = (
        getattr(settings, "AI_BUDGET_ALERT_RECIPIENT", None)
        or getattr(settings, "EMAIL_FROM_ADDRESS", None)
        or "willwalterburns@gmail.com"
    )
    subject = f"MAC Septic AI: yesterday's spend ${float(spend):.4f} exceeded ${float(threshold):.2f}"
    body = (
        f"AI Interaction Analyzer spent ${float(spend):.6f} on {yesterday_iso} (UTC).\n"
        f"Alert threshold: ${float(threshold):.2f}.\n\n"
        "Daily cap (worker pause point): $25.00 by default. To change either, set "
        "AI_DAILY_ALERT_USD or AI_DAILY_BUDGET_USD on Railway."
    )

    try:
        service = EmailService()
        if service.is_configured:
            await service.send_email(to=recipient, subject=subject, body=body)
            logger.info("ai_budget: alert email sent to %s", recipient)
            _last_alert_date["date"] = yesterday_iso
        else:
            logger.warning("ai_budget: email service not configured — skipping mail")
    except Exception:  # noqa: BLE001
        logger.exception("ai_budget: email send failed")


def start_ai_budget_scheduler() -> None:
    sched = get_scheduler()
    sched.add_job(
        report_yesterday_spend,
        CronTrigger(
            hour=0,
            minute=5,
            timezone="UTC",
        ),
        id="ai_budget_daily",
        name="AI daily spend report",
        replace_existing=True,
    )
    if not sched.running:
        sched.start()
        logger.info("ai_budget_scheduler started — daily 00:05 UTC")


def stop_ai_budget_scheduler() -> None:
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("ai_budget_scheduler stopped")


def reset_alert_state_for_tests() -> None:
    _last_alert_date["date"] = None


__all__ = [
    "start_ai_budget_scheduler",
    "stop_ai_budget_scheduler",
    "report_yesterday_spend",
    "reset_alert_state_for_tests",
]
