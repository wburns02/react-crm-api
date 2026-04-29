"""Fan-out queue for the AI Interaction Analyzer.

Stage 2 webhooks/pollers call ``enqueue_interaction_analysis(source_id, channel)``
with the just-written source row's ID. We schedule the worker on the asyncio
event loop and return immediately so the caller (webhook handler / poller)
isn't blocked by transcription + Anthropic + DB writes.

The worker itself is in ``app.services.ai.worker.process_interaction``.
This module is intentionally thin so it can be safely imported from any
context (request handler, background task, scheduler).
"""
from __future__ import annotations

import asyncio
import logging
from uuid import UUID

logger = logging.getLogger(__name__)


async def enqueue_interaction_analysis(source_id: UUID, channel: str) -> None:
    """Schedule the worker to run on the source row. Idempotent.

    We use ``asyncio.create_task`` so callers (webhooks, pollers) return
    immediately. The worker is wrapped in ``_run_worker_safely`` so a
    crash in the pipeline never escapes to the caller's event loop.
    """
    asyncio.create_task(_run_worker_safely(source_id, channel))


async def _run_worker_safely(source_id: UUID, channel: str) -> None:
    """Run the worker, swallowing exceptions so they don't sink the event loop."""
    try:
        # Local import to avoid circular dep: worker -> queue -> worker.
        from app.services.ai.worker import process_interaction

        await process_interaction(source_id, channel)
    except Exception:  # noqa: BLE001 — dead-letter is logged inside the worker
        logger.exception(
            "Interaction worker crashed for %s:%s", channel, source_id
        )


__all__ = ["enqueue_interaction_analysis"]
