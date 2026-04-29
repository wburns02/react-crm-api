"""Backfill the AI Interaction Analyzer over the last N days.

Walks the source tables (``call_logs``, ``messages``, ``inbound_emails``)
since a date cutoff, finds rows that don't already have a corresponding
``customer_interactions`` row, and enqueues analysis for each.

Respects the daily AI budget cap: if `is_paused()` returns True we sleep
60 seconds and retry once before exiting gracefully.

Usage:
    python scripts/backfill_interactions.py --days 90
    python scripts/backfill_interactions.py --days 30 --channel email --dry-run
    python scripts/backfill_interactions.py --days 7 --limit 100
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

# Allow `python scripts/backfill_interactions.py` from the repo root.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from app.database import async_session_maker  # noqa: E402
from app.models.call_log import CallLog  # noqa: E402
from app.models.customer_interaction import CustomerInteraction  # noqa: E402
from app.models.inbound_email import InboundEmail  # noqa: E402
from app.models.message import Message  # noqa: E402
from app.services.ai import budget as budget_module  # noqa: E402
from app.services.ai.queue import enqueue_interaction_analysis  # noqa: E402

logger = logging.getLogger("backfill")


CHANNELS = ("call", "sms", "email", "chat")
PROGRESS_INTERVAL = 50
ESTIMATED_COST_PER_INTERACTION_USD = 0.005  # rough — Haiku triage ≈ $0.001-$0.005


async def backfill(
    days: int,
    channel_filter: str | None,
    limit: int | None,
    dry_run: bool,
) -> dict[str, int]:
    """Walk source tables and enqueue analysis for missing interactions."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    enqueued = 0
    skipped = 0

    async with async_session_maker() as db:
        # Existing external_ids to dedupe against.
        existing_ids: set[str] = set(
            (
                await db.execute(
                    select(CustomerInteraction.external_id).where(
                        CustomerInteraction.external_id.isnot(None)
                    )
                )
            )
            .scalars()
            .all()
        )

        # 1. Calls --------------------------------------------------------
        if _channel_enabled("call", channel_filter):
            stmt = (
                select(CallLog.id, CallLog.ringcentral_call_id, CallLog.created_at)
                .where(CallLog.created_at >= cutoff)
                .order_by(CallLog.created_at.desc())
            )
            if limit is not None:
                stmt = stmt.limit(limit)

            for row in (await db.execute(stmt)).all():
                call_id, rc_id, _ts = row
                external_id = (
                    f"call:{rc_id}" if rc_id else f"call:{call_id}"
                )
                if external_id in existing_ids:
                    skipped += 1
                    continue
                if not await _budget_ok(db):
                    logger.warning("backfill: budget paused — exiting early")
                    return {
                        "enqueued": enqueued,
                        "skipped": skipped,
                        "estimated_cost_usd": _est_cost(enqueued),
                    }
                if dry_run:
                    enqueued += 1
                    continue
                await enqueue_interaction_analysis(call_id, "call")
                enqueued += 1
                if enqueued % PROGRESS_INTERVAL == 0:
                    logger.info("backfill: enqueued %d so far", enqueued)

        # 2. SMS / chat ---------------------------------------------------
        for ch in ("sms", "chat"):
            if not _channel_enabled(ch, channel_filter):
                continue
            stmt = (
                select(Message.id, Message.created_at, Message.type)
                .where(Message.created_at >= cutoff)
                .where(Message.type == ch)
                .order_by(Message.created_at.desc())
            )
            if limit is not None:
                stmt = stmt.limit(limit)

            for row in (await db.execute(stmt)).all():
                msg_id, _ts, _type = row
                external_id = f"{ch}:{msg_id}"
                if external_id in existing_ids:
                    skipped += 1
                    continue
                if not await _budget_ok(db):
                    logger.warning("backfill: budget paused — exiting early")
                    return {
                        "enqueued": enqueued,
                        "skipped": skipped,
                        "estimated_cost_usd": _est_cost(enqueued),
                    }
                if dry_run:
                    enqueued += 1
                    continue
                await enqueue_interaction_analysis(msg_id, ch)
                enqueued += 1
                if enqueued % PROGRESS_INTERVAL == 0:
                    logger.info("backfill: enqueued %d so far", enqueued)

        # 3. Emails -------------------------------------------------------
        if _channel_enabled("email", channel_filter):
            stmt = (
                select(InboundEmail.id, InboundEmail.created_at)
                .where(InboundEmail.created_at >= cutoff)
                .order_by(InboundEmail.created_at.desc())
            )
            if limit is not None:
                stmt = stmt.limit(limit)

            for row in (await db.execute(stmt)).all():
                email_id, _ts = row
                external_id = f"email:{email_id}"
                if external_id in existing_ids:
                    skipped += 1
                    continue
                if not await _budget_ok(db):
                    logger.warning("backfill: budget paused — exiting early")
                    return {
                        "enqueued": enqueued,
                        "skipped": skipped,
                        "estimated_cost_usd": _est_cost(enqueued),
                    }
                if dry_run:
                    enqueued += 1
                    continue
                await enqueue_interaction_analysis(email_id, "email")
                enqueued += 1
                if enqueued % PROGRESS_INTERVAL == 0:
                    logger.info("backfill: enqueued %d so far", enqueued)

    return {
        "enqueued": enqueued,
        "skipped": skipped,
        "estimated_cost_usd": _est_cost(enqueued),
    }


def _channel_enabled(channel: str, filt: str | None) -> bool:
    if filt is None:
        return True
    return filt.lower() == channel.lower()


def _est_cost(n: int) -> float:
    return round(n * ESTIMATED_COST_PER_INTERACTION_USD, 4)


async def _budget_ok(db) -> bool:
    """Return True if it's safe to keep enqueueing.

    If the budget is paused, sleep 60s and re-check once. If still paused,
    return False so the caller can exit gracefully.
    """
    paused, _ = await budget_module.is_paused(db)
    if not paused:
        return True
    logger.warning("backfill: budget paused — sleeping 60s before retry")
    await asyncio.sleep(60)
    paused, _ = await budget_module.is_paused(db)
    return not paused


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--days", type=int, default=90, help="Lookback window in days (default: 90)"
    )
    parser.add_argument(
        "--channel",
        choices=list(CHANNELS),
        default=None,
        help="Limit to one channel (default: all)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap rows per channel (default: no cap)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print plan without enqueueing",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose logging (DEBUG)",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


async def main_async(args: argparse.Namespace) -> int:
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )
    logger.info(
        "backfill: starting (days=%d channel=%s limit=%s dry_run=%s)",
        args.days,
        args.channel or "ALL",
        args.limit,
        args.dry_run,
    )
    summary = await backfill(
        days=args.days,
        channel_filter=args.channel,
        limit=args.limit,
        dry_run=args.dry_run,
    )
    logger.info(
        "backfill: done — enqueued=%d skipped=%d est_cost=$%.4f",
        summary["enqueued"],
        summary["skipped"],
        summary["estimated_cost_usd"],
    )
    return 0


def main() -> int:
    return asyncio.run(main_async(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
