"""Weekly AI Strategist scheduler — Sunday 06:00 America/Chicago.

Runs `app.services.ai.strategy.run_weekly_strategy()` for the previous
calendar week and emails Will a summary on success. Runs in the same
APScheduler instance pattern as `app.tasks.reminder_scheduler`.
"""
from __future__ import annotations

import logging
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.database import async_session_maker
from app.services.ai.strategy import previous_iso_week, run_weekly_strategy
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)


scheduler: Optional[AsyncIOScheduler] = None


def get_scheduler() -> AsyncIOScheduler:
    global scheduler
    if scheduler is None:
        scheduler = AsyncIOScheduler()
    return scheduler


async def run_strategy_and_email() -> None:
    """Job target: regenerate previous week's insight, then email Will."""
    iso_week = previous_iso_week()
    logger.info("ai_strategy_scheduler: running weekly strategy for %s", iso_week)

    try:
        async with async_session_maker() as db:
            insight = await run_weekly_strategy(db, iso_week=iso_week, force=True)
    except Exception:  # noqa: BLE001
        logger.exception(
            "ai_strategy_scheduler: run_weekly_strategy failed for %s", iso_week
        )
        return

    # Send the email summary to Will. Best-effort.
    recipient = (
        getattr(settings, "AI_BUDGET_ALERT_RECIPIENT", None)
        or getattr(settings, "EMAIL_FROM_ADDRESS", None)
        or "willwalterburns@gmail.com"
    )
    subject = f"MAC Septic AI: weekly insights for {iso_week}"
    body = (
        f"Weekly insights for {iso_week} ({insight.start_date} to {insight.end_date}).\n\n"
        f"Total interactions: {insight.total_interactions}\n"
        f"Cost: ${float(insight.cost_usd or 0):.4f}\n\n"
        "----- Report -----\n\n"
        f"{insight.report_markdown}\n\n"
        "----- End report -----\n\n"
        "Open the Weekly Insights page in the CRM to interact with this report."
    )

    try:
        service = EmailService()
        if service.is_configured:
            await service.send_email(to=recipient, subject=subject, body=body)
            logger.info(
                "ai_strategy_scheduler: emailed weekly insight (%s) to %s",
                iso_week,
                recipient,
            )
        else:
            logger.warning(
                "ai_strategy_scheduler: email service not configured — skipping mail"
            )
    except Exception:  # noqa: BLE001
        logger.exception("ai_strategy_scheduler: email send failed")


def start_ai_strategy_scheduler() -> None:
    """Register the Sunday 06:00 America/Chicago job."""
    sched = get_scheduler()

    sched.add_job(
        run_strategy_and_email,
        CronTrigger(
            day_of_week="sun",
            hour=6,
            minute=0,
            timezone="America/Chicago",
        ),
        id="ai_strategy_weekly",
        name="AI weekly strategist (Opus 4.7)",
        replace_existing=True,
    )

    if not sched.running:
        sched.start()
        logger.info(
            "ai_strategy_scheduler started — Sundays 06:00 America/Chicago"
        )


def stop_ai_strategy_scheduler() -> None:
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("ai_strategy_scheduler stopped")


__all__ = [
    "start_ai_strategy_scheduler",
    "stop_ai_strategy_scheduler",
    "run_strategy_and_email",
]
