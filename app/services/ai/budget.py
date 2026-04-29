"""Daily AI budget guard for the Interaction Analyzer.

If today's cumulative ``cost_usd`` across all ``interaction_analysis_runs``
hits the cap (env ``AI_DAILY_BUDGET_USD``, default $25.00), the worker
no-ops and emails Will once per process.

Email send is best-effort: failures are logged and never crash the worker.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.customer_interaction import InteractionAnalysisRun

logger = logging.getLogger(__name__)


# Default cap if env var is unset.
DAILY_BUDGET_USD_DEFAULT = Decimal("25.00")

# Process-level "alerted today" guard so we send at most one email per run.
# Stores the date we last alerted (UTC).
_alert_state: dict[str, str | None] = {"last_alert_date": None}


def _today_utc_start() -> datetime:
    """Return the UTC midnight of 'today' as a tz-aware datetime."""
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def get_cap_usd() -> Decimal:
    """Read the daily cap from settings, falling back to the default."""
    raw = getattr(settings, "AI_DAILY_BUDGET_USD", None)
    if raw is None:
        return DAILY_BUDGET_USD_DEFAULT
    try:
        return Decimal(str(raw))
    except Exception:  # noqa: BLE001
        return DAILY_BUDGET_USD_DEFAULT


async def get_today_spend_usd(db: AsyncSession) -> Decimal:
    """Sum cost_usd across interaction_analysis_runs created today (UTC)."""
    start = _today_utc_start()
    stmt = select(func.coalesce(func.sum(InteractionAnalysisRun.cost_usd), 0)).where(
        InteractionAnalysisRun.created_at >= start
    )
    result = await db.execute(stmt)
    raw = result.scalar() or 0
    try:
        return Decimal(str(raw))
    except Exception:  # noqa: BLE001
        return Decimal("0")


async def is_paused(db: AsyncSession) -> tuple[bool, Decimal]:
    """Return (paused, today_spend) — True if budget cap met or exceeded."""
    spend = await get_today_spend_usd(db)
    cap = get_cap_usd()
    return (spend >= cap, spend)


async def alert_will(today_spend: Decimal, cap: Decimal) -> None:
    """Send Will an email that the daily AI budget cap was hit. Idempotent per UTC day per process.

    Best-effort: a misconfigured email service must not crash the worker.
    """
    today = _today_utc_start().date().isoformat()
    if _alert_state["last_alert_date"] == today:
        # Already alerted today.
        return
    _alert_state["last_alert_date"] = today

    recipient = getattr(settings, "AI_BUDGET_ALERT_RECIPIENT", None) or getattr(
        settings, "EMAIL_FROM_ADDRESS", None
    ) or "willwalterburns@gmail.com"

    subject = f"MAC Septic AI: daily spend ${today_spend:.2f} exceeded ${cap:.2f} cap"
    body = (
        "The AI Interaction Analyzer has hit its daily budget cap and is "
        "paused for the rest of the day (UTC).\n\n"
        f"Today's spend: ${today_spend:.4f}\n"
        f"Daily cap:    ${cap:.4f}\n\n"
        "New incoming calls/SMS/emails will be ingested into source tables "
        "as usual, but Claude analysis is paused until 00:00 UTC. To raise "
        "the cap, set AI_DAILY_BUDGET_USD on Railway."
    )

    try:
        from app.services.email_service import EmailService

        service = EmailService()
        await service.send_email(to=recipient, subject=subject, body=body)
        logger.warning(
            "AI budget cap hit (spend=%s, cap=%s) — alert email sent to %s",
            today_spend,
            cap,
            recipient,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "AI budget cap hit (spend=%s, cap=%s) — alert email FAILED: %s",
            today_spend,
            cap,
            exc,
        )


def reset_alert_state_for_tests() -> None:
    """Reset the in-process 'alerted today' flag. Tests only."""
    _alert_state["last_alert_date"] = None


__all__ = [
    "DAILY_BUDGET_USD_DEFAULT",
    "get_cap_usd",
    "get_today_spend_usd",
    "is_paused",
    "alert_will",
    "reset_alert_state_for_tests",
]
