"""Stub for the AI Interaction Analyzer queue.

Stage 2 webhooks call enqueue_interaction_analysis() to fan out work to the
worker. The real implementation (BackgroundTasks dispatch + retry) lands in
Stage 3 — this stub only logs so the webhooks can be wired up safely.
"""
import logging
from uuid import UUID

logger = logging.getLogger(__name__)


async def enqueue_interaction_analysis(source_id: UUID, channel: str) -> None:
    """STUB. Real implementation in Stage 3."""
    logger.info(
        "enqueue_interaction_analysis stub: channel=%s source_id=%s",
        channel,
        source_id,
    )
