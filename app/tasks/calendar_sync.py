"""
Calendar Sync Background Task

Runs every 15 minutes to reconcile work orders with Outlook calendar events.
Follows the reminder_scheduler.py pattern.
"""

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.services.ms365_base import MS365BaseService

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def sync_calendar_events():
    """Reconcile work orders with Outlook events (placeholder for full implementation)."""
    if not MS365BaseService.is_configured():
        return

    logger.debug("Calendar sync tick (reconciliation placeholder)")
    # Full reconciliation would:
    # 1. Query work_orders WHERE outlook_event_id IS NOT NULL AND status NOT IN ('completed', 'canceled')
    # 2. For each, verify the event still exists in Outlook
    # 3. Update event details if WO was modified since last sync
    # This is a placeholder — the primary sync happens inline on WO create/update/delete


def start_calendar_sync():
    """Start the calendar sync scheduler."""
    global _scheduler
    if not MS365BaseService.is_configured():
        logger.info("Calendar sync disabled: MS365 not configured")
        return

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(sync_calendar_events, "interval", minutes=15, id="calendar_sync")
    _scheduler.start()
    logger.info("Calendar sync scheduler started (every 15 min)")


def stop_calendar_sync():
    """Stop the calendar sync scheduler."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Calendar sync scheduler stopped")
