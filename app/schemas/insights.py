"""Pydantic v2 schemas for the Weekly Insights API (Tier 3 Opus strategist).

UUID fields use UUIDStr to coerce SQLAlchemy uuid.UUID objects to strings
when serializing JSON responses (per backend rules in CLAUDE.md).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.types import UUIDStr


class InsightSummary(BaseModel):
    """Slim row for list views (e.g. recent-insights dropdown)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUIDStr
    iso_week: str
    start_date: date
    end_date: date
    total_interactions: int
    by_channel: dict[str, Any] = Field(default_factory=dict)
    cost_usd: Decimal
    created_at: datetime


class InsightRead(InsightSummary):
    """Full row — markdown report + structured JSON + token/cost metadata."""

    report_markdown: str
    report_json: Optional[dict[str, Any]] = None
    model: str
    prompt_version: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    thinking_tokens: int = 0
    duration_ms: int = 0


class InsightRefreshRequest(BaseModel):
    """POST body for the manual refresh endpoint."""

    week: Optional[str] = Field(
        default=None,
        description=(
            "ISO week, e.g. '2026-W17'. Omit to refresh the previous calendar "
            "week (Mon..Sun in America/Chicago)."
        ),
    )


class InsightRefreshResponse(BaseModel):
    """Returned by POST /ai/insights/weekly/refresh."""

    status: str  # "ok" | "queued"
    week: str
    insight: Optional[InsightRead] = None


__all__ = [
    "InsightSummary",
    "InsightRead",
    "InsightRefreshRequest",
    "InsightRefreshResponse",
]
