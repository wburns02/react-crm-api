"""Tier 3 — Weekly Strategist (Opus 4.7 with extended thinking).

Reads a week of customer interactions and produces ONE markdown report for
Will (top complaints, win patterns, channel performance, recommended ad-copy
changes, recommended landing-page changes, coaching note for Dannia,
one-thing-Will-should-call). The output is cached in
`interaction_insights` keyed by ISO week, so the Weekly Insights page
doesn't pay an Opus call on every render.

Trigger paths:
  - Sunday 06:00 America/Chicago via `app.tasks.ai_strategy_scheduler`.
  - Manual via `POST /api/v2/ai/insights/weekly/refresh` (admin-only).

Cost discipline: caps the prompt at ~300 interactions; if more, samples
stratified by intent (proportional, with at least 1 from each intent if
present in the week's data).
"""
from __future__ import annotations

import logging
import math
import random
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, Iterable, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.customer_interaction import (
    CustomerInteraction,
    InteractionAnalysisRun,
)
from app.models.interaction_insight import InteractionInsight
from app.services.ai.anthropic_client import (
    AnthropicClient,
    STRATEGY_MODEL,
)
from app.services.ai.prompts import (
    STRATEGY_VERSION,
    render_strategy_user_message,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CHICAGO_TZ = ZoneInfo("America/Chicago")
MAX_INTERACTIONS_PER_RUN = 300
TRANSCRIPT_MAX_CHARS = 4000  # cap each interaction's content to keep prompt size in check


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------
async def run_weekly_strategy(
    db: AsyncSession,
    iso_week: Optional[str] = None,
    *,
    force: bool = False,
    client: Optional[AnthropicClient] = None,
) -> InteractionInsight:
    """Run the Tier 3 weekly strategist for the given ISO week.

    Args:
        db: Async session.
        iso_week: e.g. ``"2026-W17"``. Defaults to the previous calendar
            week in America/Chicago.
        force: If True and a row already exists for this iso_week, replace
            it instead of returning the cached row.
        client: Inject an AnthropicClient for tests; default constructs from
            ``settings.ANTHROPIC_API_KEY``.

    Returns:
        The persisted ``InteractionInsight`` row (newly written or cached).
    """
    if iso_week is None:
        iso_week = previous_iso_week()

    start_date, end_date = iso_week_to_date_range(iso_week)

    # 1. Idempotency — return cached row unless force=True ------------------
    existing = await _get_existing(db, iso_week)
    if existing is not None and not force:
        logger.info(
            "weekly_strategy: cached row exists for %s — returning", iso_week
        )
        return existing

    # 2. Pull interactions in the date range --------------------------------
    interactions = await _load_interactions(db, start_date, end_date)
    total = len(interactions)
    by_channel = _count_by_channel(interactions)

    if total == 0:
        # Edge case — empty week. Persist a tiny placeholder row so the page
        # has something to show ("no interactions this week").
        report_markdown = (
            f"# Weekly Insights — {iso_week}\n\n"
            f"_No customer interactions recorded between {start_date.isoformat()} "
            f"and {end_date.isoformat()}._\n\n"
            "Nothing to analyze. Check back next week."
        )
        return await _persist(
            db,
            iso_week=iso_week,
            start_date=start_date,
            end_date=end_date,
            total=0,
            by_channel={},
            report_markdown=report_markdown,
            model=STRATEGY_MODEL,
            prompt_version=STRATEGY_VERSION,
            cost=Decimal("0"),
            input_tokens=0,
            output_tokens=0,
            cache_read_tokens=0,
            cache_write_tokens=0,
            thinking_tokens=0,
            duration_ms=0,
            replace_existing=existing is not None,
            existing_row=existing,
            report_json=None,
        )

    # 3. Stratified sampling cap (300 max) ---------------------------------
    if total > MAX_INTERACTIONS_PER_RUN:
        sampled = _stratified_sample(interactions, MAX_INTERACTIONS_PER_RUN)
    else:
        sampled = list(interactions)

    # 4. Build the user message --------------------------------------------
    user_message = render_strategy_user_message(
        week=iso_week,
        date_range=(start_date.isoformat(), end_date.isoformat()),
        total=total,
        by_channel=by_channel,
        interactions=[_serialize_interaction(row) for row in sampled],
    )

    # 5. Call Opus ---------------------------------------------------------
    client = client or AnthropicClient(settings.ANTHROPIC_API_KEY or "")
    result = await client.call_strategy(user_message)

    # 6. Persist & log run -------------------------------------------------
    insight = await _persist(
        db,
        iso_week=iso_week,
        start_date=start_date,
        end_date=end_date,
        total=total,
        by_channel=by_channel,
        report_markdown=result.text or "_(empty model output)_",
        model=result.model,
        prompt_version=result.prompt_version,
        cost=result.cost_usd,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cache_read_tokens=result.cache_read_tokens,
        cache_write_tokens=result.cache_write_tokens,
        thinking_tokens=result.thinking_tokens,
        duration_ms=result.duration_ms,
        replace_existing=existing is not None,
        existing_row=existing,
        report_json=None,
    )

    # Audit row in interaction_analysis_runs (tier="strategy"). The
    # strategy run isn't tied to a specific interaction, so we use a
    # synthesized synthetic interaction_id pattern: pick the first
    # interaction in the week if any. (FK requires a valid interaction id.)
    try:
        first_id = sampled[0].id if sampled else None
        if first_id is not None:
            db.add(
                InteractionAnalysisRun(
                    interaction_id=first_id,
                    tier="strategy",
                    model=result.model,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    cache_read_tokens=result.cache_read_tokens,
                    cache_write_tokens=result.cache_write_tokens,
                    cost_usd=result.cost_usd,
                    duration_ms=result.duration_ms,
                    prompt_version=result.prompt_version,
                    status="ok",
                )
            )
            await db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("weekly_strategy: failed to write strategy run audit row")

    return insight


# ---------------------------------------------------------------------------
# ISO week helpers
# ---------------------------------------------------------------------------
def previous_iso_week(now: Optional[datetime] = None) -> str:
    """Return the previous ISO week (Mon..Sun) in America/Chicago.

    Example: if today is Mon 2026-04-27 (CT), returns "2026-W17".
    """
    now_dt = now or datetime.now(tz=CHICAGO_TZ)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=CHICAGO_TZ)
    # Step back 7 days then take that week's iso calendar.
    prior = now_dt - timedelta(days=7)
    yr, wk, _ = prior.isocalendar()
    return f"{yr:04d}-W{wk:02d}"


def iso_week_to_date_range(iso_week: str) -> tuple[date, date]:
    """Convert ISO week string (e.g. "2026-W17") -> (Mon date, Sun date)."""
    if "-W" not in iso_week:
        raise ValueError(f"Invalid ISO week: {iso_week!r}")
    year_part, week_part = iso_week.split("-W", 1)
    year = int(year_part)
    week = int(week_part)
    # ISO week — Monday is day 1.
    monday = date.fromisocalendar(year, week, 1)
    sunday = monday + timedelta(days=6)
    return monday, sunday


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------
async def _get_existing(
    db: AsyncSession, iso_week: str
) -> Optional[InteractionInsight]:
    stmt = select(InteractionInsight).where(InteractionInsight.iso_week == iso_week)
    return (await db.execute(stmt)).scalar_one_or_none()


async def _load_interactions(
    db: AsyncSession, start_date: date, end_date: date
) -> list[CustomerInteraction]:
    """Load interactions whose ``occurred_at`` falls in [Mon 00:00, Sun 23:59:59] CT."""
    start_dt = datetime.combine(start_date, time.min, tzinfo=CHICAGO_TZ).astimezone(
        timezone.utc
    )
    end_dt = datetime.combine(end_date, time.max, tzinfo=CHICAGO_TZ).astimezone(
        timezone.utc
    )
    stmt = (
        select(CustomerInteraction)
        .where(CustomerInteraction.occurred_at >= start_dt)
        .where(CustomerInteraction.occurred_at <= end_dt)
        .order_by(CustomerInteraction.occurred_at.asc())
    )
    return list((await db.execute(stmt)).scalars().all())


def _count_by_channel(rows: Iterable[CustomerInteraction]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for r in rows:
        counts[str(r.channel or "unknown")] += 1
    return dict(counts)


def _stratified_sample(
    rows: list[CustomerInteraction], cap: int
) -> list[CustomerInteraction]:
    """Sample ``cap`` rows, distributing proportionally across intent groups.

    Each intent group with N items contributes ``round(N / total * cap)`` rows
    (minimum 1 if the group has any items). Within a group we pick by
    hot_lead_score desc then occurred_at desc, falling back to random for
    ties.

    Deterministic-ish (seeded by week) so the same week renders the same
    sample if we re-run with ``force=False`` then later ``force=True``.
    """
    total = len(rows)
    if total <= cap:
        return list(rows)

    groups: dict[str, list[CustomerInteraction]] = defaultdict(list)
    for r in rows:
        intent = (r.intent or "unknown").lower()
        groups[intent].append(r)

    rng = random.Random(42)
    out: list[CustomerInteraction] = []

    # Compute per-group quotas (proportional, min 1 if group non-empty).
    quotas: dict[str, int] = {}
    for intent, items in groups.items():
        share = max(1, math.floor(len(items) / total * cap))
        quotas[intent] = min(share, len(items))

    # Adjust to exactly cap by adding/removing 1 from largest groups.
    quota_sum = sum(quotas.values())
    while quota_sum < cap:
        # add one to the group with the most remaining headroom
        candidates = [
            (intent, len(items) - quotas[intent])
            for intent, items in groups.items()
            if quotas[intent] < len(items)
        ]
        if not candidates:
            break
        intent_to_bump = max(candidates, key=lambda x: x[1])[0]
        quotas[intent_to_bump] += 1
        quota_sum += 1
    while quota_sum > cap:
        # remove one from the group with the largest current quota
        intent_to_shrink = max(quotas.items(), key=lambda x: x[1])[0]
        quotas[intent_to_shrink] = max(0, quotas[intent_to_shrink] - 1)
        quota_sum -= 1

    # Pick within each group: best hot_lead_score first, ties broken random.
    for intent, items in groups.items():
        q = quotas.get(intent, 0)
        if q <= 0:
            continue
        items_sorted = sorted(
            items,
            key=lambda r: (
                int(r.hot_lead_score or 0),
                r.occurred_at or datetime.min.replace(tzinfo=timezone.utc),
                rng.random(),
            ),
            reverse=True,
        )
        out.extend(items_sorted[:q])

    return out[:cap]


def _serialize_interaction(row: CustomerInteraction) -> dict[str, Any]:
    """Compact per-interaction dict for the user prompt."""
    transcript = (row.content or "")[:TRANSCRIPT_MAX_CHARS]
    triage = dict(row.analysis or {})
    customer = {
        "city_state": None,
        "prior_jobs": 0,
    }
    return {
        "id": str(row.id),
        "channel": row.channel,
        "direction": row.direction,
        "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
        "customer": customer,
        "duration_seconds": row.duration_seconds,
        "transcript": transcript,
        "triage": triage,
        "outcome": "open",  # outcome bookkeeping is post-MVP
    }


async def _persist(
    db: AsyncSession,
    *,
    iso_week: str,
    start_date: date,
    end_date: date,
    total: int,
    by_channel: dict[str, int],
    report_markdown: str,
    model: str,
    prompt_version: str,
    cost: Decimal,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
    cache_write_tokens: int,
    thinking_tokens: int,
    duration_ms: int,
    replace_existing: bool,
    existing_row: Optional[InteractionInsight],
    report_json: Optional[dict[str, Any]],
) -> InteractionInsight:
    """Insert or replace the row, then commit and refresh."""
    if replace_existing and existing_row is not None:
        existing_row.start_date = start_date
        existing_row.end_date = end_date
        existing_row.total_interactions = total
        existing_row.by_channel = by_channel
        existing_row.report_markdown = report_markdown
        existing_row.report_json = report_json
        existing_row.model = model
        existing_row.prompt_version = prompt_version
        existing_row.cost_usd = cost
        existing_row.input_tokens = input_tokens
        existing_row.output_tokens = output_tokens
        existing_row.cache_read_tokens = cache_read_tokens
        existing_row.cache_write_tokens = cache_write_tokens
        existing_row.thinking_tokens = thinking_tokens
        existing_row.duration_ms = duration_ms
        await db.commit()
        await db.refresh(existing_row)
        return existing_row

    row = InteractionInsight(
        iso_week=iso_week,
        start_date=start_date,
        end_date=end_date,
        total_interactions=total,
        by_channel=by_channel,
        report_markdown=report_markdown,
        report_json=report_json,
        model=model,
        prompt_version=prompt_version,
        cost_usd=cost,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        thinking_tokens=thinking_tokens,
        duration_ms=duration_ms,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


__all__ = [
    "run_weekly_strategy",
    "previous_iso_week",
    "iso_week_to_date_range",
]
