"""Weekly AI Insights — Tier 3 Opus 4.7 strategist read + refresh endpoints.

Routes (mounted at /api/v2):
  GET  /ai/insights/weekly?week=2026-W17  — return the cached row or 404
  GET  /ai/insights/recent?limit=8        — recent insights for selector
  POST /ai/insights/weekly/refresh        — admin-only, force regenerate

The Sunday 06:00 CT scheduler is the canonical writer; refresh is a
manual override (e.g. when Will wants a fresh report mid-week).

Static routes (`/recent`, `/weekly`, `/weekly/refresh`) declared before any
catch-all to keep FastAPI's route resolver happy. There is no
``/{insight_id}`` route to collide with.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.interaction_insight import InteractionInsight
from app.schemas.insights import (
    InsightRead,
    InsightRefreshRequest,
    InsightRefreshResponse,
    InsightSummary,
)
from app.services.ai.strategy import (
    iso_week_to_date_range,
    previous_iso_week,
    run_weekly_strategy,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# GET /ai/insights/recent
# ---------------------------------------------------------------------------
@router.get(
    "/ai/insights/recent",
    response_model=list[InsightSummary],
    summary="Most recent weekly insights (for the week selector)",
    tags=["ai-insights"],
)
async def list_recent_insights(
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(8, ge=1, le=52),
) -> list[InsightSummary]:
    stmt = (
        select(InteractionInsight)
        .order_by(InteractionInsight.end_date.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [InsightSummary.model_validate(r) for r in rows]


# ---------------------------------------------------------------------------
# GET /ai/insights/weekly
# ---------------------------------------------------------------------------
@router.get(
    "/ai/insights/weekly",
    response_model=InsightRead,
    summary="Cached weekly insight for the requested ISO week (defaults to previous)",
    tags=["ai-insights"],
)
async def get_weekly_insight(
    db: DbSession,
    current_user: CurrentUser,
    week: Optional[str] = Query(
        None,
        description=(
            "ISO week, e.g. '2026-W17'. If omitted, defaults to the previous "
            "calendar week in America/Chicago."
        ),
    ),
) -> InsightRead:
    iso_week = week or previous_iso_week()
    try:
        # Validate parseability up-front so we 404 cleanly instead of 500.
        iso_week_to_date_range(iso_week)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid ISO week '{iso_week}': {exc}",
        )

    stmt = select(InteractionInsight).where(InteractionInsight.iso_week == iso_week)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No insights for week {iso_week} yet.",
        )
    return InsightRead.model_validate(row)


# ---------------------------------------------------------------------------
# POST /ai/insights/weekly/refresh
# ---------------------------------------------------------------------------
@router.post(
    "/ai/insights/weekly/refresh",
    response_model=InsightRefreshResponse,
    summary="Force-regenerate the weekly insight (admin only)",
    tags=["ai-insights"],
)
async def refresh_weekly_insight(
    payload: InsightRefreshRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> InsightRefreshResponse:
    if not getattr(current_user, "is_admin", False) and not getattr(
        current_user, "is_superuser", False
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required to refresh weekly insights.",
        )

    iso_week = payload.week or previous_iso_week()
    try:
        iso_week_to_date_range(iso_week)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid ISO week '{iso_week}': {exc}",
        )

    try:
        insight = await run_weekly_strategy(db, iso_week=iso_week, force=True)
    except Exception as exc:  # noqa: BLE001
        logger.exception("refresh_weekly_insight failed for %s", iso_week)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Strategy run failed: {exc}",
        )

    return InsightRefreshResponse(
        status="ok",
        week=iso_week,
        insight=InsightRead.model_validate(insight),
    )


__all__ = ["router"]
