"""AI Interaction Analyzer — read endpoints + reanalyze + dismiss.

Routes (mounted at /api/v2):
  GET  /customers/{customer_id}/interactions       — per-customer history
  GET  /ai/interactions/hot                         — cross-channel hot leads inbox
  GET  /ai/budget                                   — daily/monthly spend + cap + paused
  GET  /ai/interactions/{interaction_id}            — full detail (action items, latest run)
  POST /ai/interactions/{interaction_id}/reanalyze  — re-run worker pipeline
  POST /ai/interactions/{interaction_id}/dismiss-hot — clear hot_lead_score, mark dismissed

Static routes (`/hot`, `/budget`) MUST be declared BEFORE the dynamic
`/{interaction_id}` route so FastAPI resolves them in priority order.
"""
from __future__ import annotations

import logging
import uuid as uuid_module
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession
from app.models.customer import Customer
from app.models.customer_interaction import (
    CustomerInteraction,
    InteractionAnalysisRun,
)
from app.schemas.interactions import (
    BudgetSummary,
    HotLeadItem,
    InteractionListItem,
    InteractionRead,
)
from app.services.ai import budget as budget_module

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
VALID_CHANNELS = {"call", "voicemail", "sms", "email", "chat"}


def _parse_uuid(value: str, *, label: str) -> uuid_module.UUID:
    """Validate a path/query UUID, raising 404 (not 422) on bad shape."""
    try:
        return uuid_module.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{label} not found",
        )


def _serialize_detail(
    interaction: CustomerInteraction,
    *,
    latest_run: Optional[InteractionAnalysisRun] = None,
) -> InteractionRead:
    """Build an InteractionRead from the ORM row (action items eager-loaded)."""
    payload = {
        "id": interaction.id,
        "customer_id": interaction.customer_id,
        "external_id": interaction.external_id,
        "channel": interaction.channel,
        "direction": interaction.direction,
        "provider": interaction.provider,
        "occurred_at": interaction.occurred_at,
        "duration_seconds": interaction.duration_seconds,
        "from_address": interaction.from_address or "",
        "to_address": interaction.to_address or "",
        "subject": interaction.subject,
        "hot_lead_score": interaction.hot_lead_score or 0,
        "intent": interaction.intent,
        "sentiment": interaction.sentiment,
        "urgency": interaction.urgency,
        "do_not_contact": bool(interaction.do_not_contact),
        "analysis_at": interaction.analysis_at,
        "created_at": interaction.created_at,
        "updated_at": interaction.updated_at,
        "content": interaction.content or "",
        "content_uri": interaction.content_uri,
        "raw_payload": dict(interaction.raw_payload or {}),
        "analysis": dict(interaction.analysis or {}),
        "suggested_reply": interaction.suggested_reply,
        "analysis_model": interaction.analysis_model,
        "analysis_cost_usd": interaction.analysis_cost_usd or Decimal("0"),
        "action_items": list(interaction.action_items or []),
        "latest_analysis_run": latest_run,
    }
    return InteractionRead.model_validate(payload)


# ---------------------------------------------------------------------------
# GET /customers/{customer_id}/interactions
# ---------------------------------------------------------------------------
@router.get(
    "/customers/{customer_id}/interactions",
    response_model=list[InteractionListItem],
    summary="List a customer's interactions across all channels",
    tags=["ai-interactions"],
)
async def list_customer_interactions(
    customer_id: str,
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(50, ge=1, le=200),
    channel: Optional[str] = Query(None),
    since: Optional[datetime] = Query(None),
) -> list[InteractionListItem]:
    """Return up to `limit` interactions for one customer, newest first."""
    cust_uuid = _parse_uuid(customer_id, label="Customer")

    if channel is not None and channel not in VALID_CHANNELS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown channel '{channel}'",
        )

    stmt = (
        select(CustomerInteraction)
        .where(CustomerInteraction.customer_id == cust_uuid)
        .order_by(CustomerInteraction.occurred_at.desc())
        .limit(limit)
    )
    if channel:
        stmt = stmt.where(CustomerInteraction.channel == channel)
    if since is not None:
        stmt = stmt.where(CustomerInteraction.occurred_at >= since)

    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [InteractionListItem.model_validate(r) for r in rows]


# ---------------------------------------------------------------------------
# GET /ai/interactions/hot   (STATIC — must precede /{interaction_id})
# ---------------------------------------------------------------------------
@router.get(
    "/ai/interactions/hot",
    response_model=list[HotLeadItem],
    summary="Cross-channel Hot Leads inbox",
    tags=["ai-interactions"],
)
async def list_hot_interactions(
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(50, ge=1, le=200),
    min_score: int = Query(70, ge=0, le=100),
) -> list[HotLeadItem]:
    """Return rows with hot_lead_score >= min_score, hottest first."""
    stmt = (
        select(CustomerInteraction, Customer)
        .outerjoin(Customer, CustomerInteraction.customer_id == Customer.id)
        .where(CustomerInteraction.hot_lead_score >= min_score)
        .order_by(
            CustomerInteraction.hot_lead_score.desc(),
            CustomerInteraction.occurred_at.desc(),
        )
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()

    items: list[HotLeadItem] = []
    for interaction, customer in rows:
        full_name: Optional[str] = None
        if customer is not None:
            first = (customer.first_name or "").strip()
            last = (customer.last_name or "").strip()
            full_name = (f"{first} {last}").strip() or None

        reply_preview: Optional[str] = None
        if interaction.suggested_reply:
            reply_preview = interaction.suggested_reply[:240]

        items.append(
            HotLeadItem(
                id=interaction.id,
                customer_id=interaction.customer_id,
                customer_name=full_name,
                channel=interaction.channel,
                occurred_at=interaction.occurred_at,
                intent=interaction.intent,
                hot_lead_score=interaction.hot_lead_score or 0,
                urgency=interaction.urgency,
                suggested_reply_preview=reply_preview,
            )
        )
    return items


# ---------------------------------------------------------------------------
# GET /ai/budget   (STATIC — must precede /{interaction_id})
# ---------------------------------------------------------------------------
@router.get(
    "/ai/budget",
    response_model=BudgetSummary,
    summary="Today + this-month AI spend, cap, and pause flag",
    tags=["ai-interactions"],
)
async def get_ai_budget(
    db: DbSession,
    current_user: CurrentUser,
) -> BudgetSummary:
    """Return today/this-month spend, cap, and whether the worker is paused."""
    paused, today_spend = await budget_module.is_paused(db)
    cap = budget_module.get_cap_usd()

    # Sum cost_usd for runs created since the first day of the current UTC month.
    now = datetime.now(timezone.utc)
    month_start = now.replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    month_stmt = select(
        func.coalesce(func.sum(InteractionAnalysisRun.cost_usd), 0)
    ).where(InteractionAnalysisRun.created_at >= month_start)
    month_raw = (await db.execute(month_stmt)).scalar() or 0
    try:
        month_total = Decimal(str(month_raw))
    except Exception:  # noqa: BLE001
        month_total = Decimal("0")

    return BudgetSummary(
        today_usd=float(today_spend),
        this_month_usd=float(month_total),
        daily_cap_usd=float(cap),
        paused=bool(paused),
    )


# ---------------------------------------------------------------------------
# GET /ai/interactions/{interaction_id}   (DYNAMIC — declared AFTER static)
# ---------------------------------------------------------------------------
@router.get(
    "/ai/interactions/{interaction_id}",
    response_model=InteractionRead,
    summary="Full interaction detail (action items, latest analysis run)",
    tags=["ai-interactions"],
)
async def get_interaction_detail(
    interaction_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> InteractionRead:
    int_uuid = _parse_uuid(interaction_id, label="Interaction")

    stmt = (
        select(CustomerInteraction)
        .where(CustomerInteraction.id == int_uuid)
        .options(
            selectinload(CustomerInteraction.action_items),
            selectinload(CustomerInteraction.analysis_runs),
        )
    )
    interaction = (await db.execute(stmt)).scalar_one_or_none()
    if interaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interaction not found",
        )

    # analysis_runs is ordered created_at DESC by the relationship config.
    runs = list(interaction.analysis_runs or [])
    latest_run = runs[0] if runs else None

    return _serialize_detail(interaction, latest_run=latest_run)


# ---------------------------------------------------------------------------
# POST /ai/interactions/{interaction_id}/dismiss-hot
# ---------------------------------------------------------------------------
@router.post(
    "/ai/interactions/{interaction_id}/dismiss-hot",
    response_model=InteractionRead,
    summary="Clear hot_lead_score and mark interaction dismissed",
    tags=["ai-interactions"],
)
async def dismiss_hot_interaction(
    interaction_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> InteractionRead:
    int_uuid = _parse_uuid(interaction_id, label="Interaction")

    stmt = (
        select(CustomerInteraction)
        .where(CustomerInteraction.id == int_uuid)
        .options(
            selectinload(CustomerInteraction.action_items),
            selectinload(CustomerInteraction.analysis_runs),
        )
    )
    interaction = (await db.execute(stmt)).scalar_one_or_none()
    if interaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interaction not found",
        )

    # Clear the hot-lead signal and stamp a dismissed_at marker into raw_payload
    # (additive — never overwrite the analyzer's source data).
    raw = dict(interaction.raw_payload or {})
    dismissed_at = datetime.now(timezone.utc).isoformat()
    raw["dismissed_at"] = dismissed_at
    raw["dismissed_by_user_id"] = current_user.id

    interaction.hot_lead_score = 0
    interaction.raw_payload = raw

    await db.commit()
    await db.refresh(interaction)

    # Re-load with eager relationships for the response.
    refreshed = (
        await db.execute(
            select(CustomerInteraction)
            .where(CustomerInteraction.id == int_uuid)
            .options(
                selectinload(CustomerInteraction.action_items),
                selectinload(CustomerInteraction.analysis_runs),
            )
        )
    ).scalar_one()
    runs = list(refreshed.analysis_runs or [])
    return _serialize_detail(refreshed, latest_run=runs[0] if runs else None)


# ---------------------------------------------------------------------------
# POST /ai/interactions/{interaction_id}/reanalyze
# ---------------------------------------------------------------------------
@router.post(
    "/ai/interactions/{interaction_id}/reanalyze",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Re-run the analyzer worker on an existing interaction",
    tags=["ai-interactions"],
)
async def reanalyze_interaction(
    interaction_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> dict[str, Any]:
    int_uuid = _parse_uuid(interaction_id, label="Interaction")

    stmt = select(CustomerInteraction).where(CustomerInteraction.id == int_uuid)
    interaction = (await db.execute(stmt)).scalar_one_or_none()
    if interaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interaction not found",
        )

    # Force the worker's freshness check to fail so it runs the pipeline again.
    interaction.analysis_at = None
    await db.commit()

    # Try to find the original source row id so the worker can re-load the
    # call/sms/email/chat fixture and re-build the interaction. Fall back to
    # the interaction id (worker handles missing source gracefully).
    source_id = await _find_source_id(db, interaction)
    channel = interaction.channel

    try:
        # Lazy import: avoid loading the worker module on app boot.
        from app.services.ai.queue import enqueue_interaction_analysis

        await enqueue_interaction_analysis(source_id, channel)
    except Exception:  # noqa: BLE001 — never let a queue error 500 the API
        logger.exception(
            "reanalyze: enqueue failed for interaction=%s channel=%s",
            interaction.id,
            channel,
        )

    return {
        "status": "queued",
        "interaction_id": str(interaction.id),
        "channel": channel,
        "source_id": str(source_id),
    }


async def _find_source_id(
    db, interaction: CustomerInteraction
) -> uuid_module.UUID:
    """Best-effort reverse lookup of the source row's primary key.

    The worker's per-channel resolver does ``db.get(<Model>, source_id)`` —
    so if we can recover the original PK from ``external_id`` or raw_payload
    we let the worker rebuild the interaction normally. If we can't, return
    the interaction's own id (worker will short-circuit at the source-not-found
    guard, which is the safest no-op).
    """
    ext = (interaction.external_id or "").strip()
    raw = interaction.raw_payload or {}

    # raw_payload may have stashed the source id under a known key.
    for key in ("source_id", "source_row_id", "call_id", "message_id", "email_id"):
        candidate = raw.get(key) if isinstance(raw, dict) else None
        if candidate:
            try:
                return uuid_module.UUID(str(candidate))
            except (ValueError, TypeError):
                continue

    # Synthetic external_ids look like "call:<uuid>", "sms:<uuid>", "email:<uuid>".
    if ":" in ext:
        _, _, tail = ext.partition(":")
        try:
            return uuid_module.UUID(tail)
        except (ValueError, TypeError):
            pass

    # external_id may itself be a bare UUID (e.g. message_id stored as UUID string).
    try:
        return uuid_module.UUID(ext)
    except (ValueError, TypeError):
        pass

    # Last resort — let the worker hit its source-not-found guard cleanly.
    return interaction.id


__all__ = ["router"]
