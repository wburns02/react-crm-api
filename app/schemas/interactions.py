"""Pydantic v2 schemas for the AI Interaction Analyzer API.

UUID fields use UUIDStr to coerce SQLAlchemy uuid.UUID objects to strings
when serializing JSON responses (per backend rules in CLAUDE.md).
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.types import UUIDStr


# ---------------------------------------------------------------------------
# Action items.
# ---------------------------------------------------------------------------
class ActionItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUIDStr
    interaction_id: UUIDStr
    action: str
    owner: str
    deadline_at: Optional[datetime] = None
    status: Literal["open", "done", "dismissed"]
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class ActionItemUpdate(BaseModel):
    """Mutable fields on an action item (PATCH payload)."""

    status: Optional[Literal["open", "done", "dismissed"]] = None
    owner: Optional[str] = None
    deadline_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Analysis runs (audit log).
# ---------------------------------------------------------------------------
class AnalysisRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUIDStr
    interaction_id: UUIDStr
    tier: Literal["triage", "reply", "strategy"]
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: Decimal
    duration_ms: int
    prompt_version: str
    status: Literal["ok", "error", "timeout"]
    error_detail: Optional[str] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Interaction read schemas.
# ---------------------------------------------------------------------------
class InteractionListItem(BaseModel):
    """Slim row for list endpoints — no transcript or raw_payload."""

    model_config = ConfigDict(from_attributes=True)

    id: UUIDStr
    customer_id: Optional[UUIDStr] = None
    external_id: str
    channel: Literal["call", "voicemail", "sms", "email", "chat"]
    direction: Literal["inbound", "outbound"]
    provider: Literal[
        "ringcentral", "twilio", "brevo", "microsoft365", "website_chat"
    ]
    occurred_at: datetime
    duration_seconds: Optional[int] = None
    from_address: str
    to_address: str
    subject: Optional[str] = None
    hot_lead_score: int
    intent: Optional[str] = None
    sentiment: Optional[str] = None
    urgency: Optional[str] = None
    do_not_contact: bool
    analysis_at: Optional[datetime] = None
    created_at: datetime


class InteractionRead(InteractionListItem):
    """Full row — transcript, analysis, action items, latest run."""

    content: str
    content_uri: Optional[str] = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    analysis: dict[str, Any] = Field(default_factory=dict)
    suggested_reply: Optional[str] = None
    analysis_model: Optional[str] = None
    analysis_cost_usd: Decimal = Decimal("0")
    action_items: list[ActionItemRead] = Field(default_factory=list)
    latest_analysis_run: Optional[AnalysisRunRead] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Hot leads inbox row (denormalized from CustomerInteraction + Customer).
# ---------------------------------------------------------------------------
class HotLeadItem(BaseModel):
    """One row in the cross-channel Hot Leads inbox."""

    model_config = ConfigDict(from_attributes=True)

    id: UUIDStr
    customer_id: Optional[UUIDStr] = None
    customer_name: Optional[str] = None
    channel: Literal["call", "voicemail", "sms", "email", "chat"]
    occurred_at: datetime
    intent: Optional[str] = None
    hot_lead_score: int
    urgency: Optional[str] = None
    suggested_reply_preview: Optional[str] = None


# ---------------------------------------------------------------------------
# Budget summary (daily / monthly spend; pause flag).
# ---------------------------------------------------------------------------
class BudgetSummary(BaseModel):
    """Returned by GET /api/v2/ai/budget."""

    today_usd: float
    this_month_usd: float
    daily_cap_usd: float
    paused: bool


__all__ = [
    "ActionItemRead",
    "ActionItemUpdate",
    "AnalysisRunRead",
    "InteractionListItem",
    "InteractionRead",
    "HotLeadItem",
    "BudgetSummary",
]
