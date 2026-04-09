"""
MS Forms Inspection Sync Background Task

Runs every 15 minutes to pull new inspection form responses from
the SharePoint Excel workbook and create work orders in the CRM.
"""

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.services.ms365_forms_sync_service import MS365FormsSyncService

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def sync_forms():
    """Pull new inspection form responses from SharePoint and create work orders."""
    if not MS365FormsSyncService.is_configured():
        return

    try:
        result = await MS365FormsSyncService.sync_inspection_forms()
        if result["synced"] > 0 or result["errors"]:
            logger.info(
                "Forms sync: synced=%d, skipped=%d, errors=%d",
                result["synced"], result["skipped"], len(result["errors"]),
            )
    except Exception as e:
        logger.error("Forms sync task error: %s", e)


def start_forms_sync():
    """Start the forms sync scheduler."""
    global _scheduler
    if not MS365FormsSyncService.is_configured():
        logger.info("Forms sync disabled: MS365 not configured")
        return

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(sync_forms, "interval", minutes=15, id="forms_sync")
    _scheduler.start()
    logger.info("Forms sync started (every 15 min)")


def stop_forms_sync():
    """Stop the forms sync scheduler."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Forms sync stopped")
