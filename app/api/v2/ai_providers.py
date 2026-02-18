"""AI Providers API - Configure and manage AI provider integrations (Anthropic Claude, etc.)."""

from fastapi import APIRouter, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_, cast, Date
from typing import Optional
from datetime import datetime, timedelta, timezone
import httpx
import time
import uuid
import logging

from app.api.deps import DbSession, CurrentUser
from app.models.ai_provider_config import AIProviderConfig, AIUsageLog
from app.services.encryption import encrypt_value, decrypt_value
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# --- Constants ---
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-4-6"
AVAILABLE_MODELS = ["claude-sonnet-4-6"]

ALL_FEATURES = {
    "chat": "AI Chat",
    "summarization": "Text Summarization",
    "sentiment": "Sentiment Analysis",
    "dispatch": "Dispatch Optimization",
    "call_analysis": "Call Analysis",
    "content_generation": "Content Generation",
}

# Sonnet pricing: $3/MTok input, $15/MTok output
COST_PER_INPUT_TOKEN = 0.003 / 1000  # $0.000003 per token
COST_PER_OUTPUT_TOKEN = 0.015 / 1000  # $0.000015 per token


# --- Schemas ---

class AIProviderStatusResponse(BaseModel):
    provider: str
    connected: bool
    is_primary: bool
    model: Optional[str] = None
    available_models: list[str] = []
    features_enabled: dict[str, bool] = {}
    connected_by: Optional[str] = None
    connected_at: Optional[str] = None
    last_used_at: Optional[str] = None
    api_key_configured: bool = False
    api_key_source: str = "none"  # "database", "environment", "none"


class AIProviderConnectRequest(BaseModel):
    api_key: str = Field(..., min_length=10, description="Anthropic API key")
    model: str = DEFAULT_MODEL
    set_as_primary: bool = True
    features: Optional[dict[str, bool]] = None


class AIProviderUpdateRequest(BaseModel):
    model: Optional[str] = None
    is_primary: Optional[bool] = None
    features: Optional[dict[str, bool]] = None


class AIProviderTestResponse(BaseModel):
    success: bool
    model: str
    response_time_ms: int
    message: str


class UsageByFeature(BaseModel):
    feature: str
    feature_label: str
    requests: int
    tokens: int
    cost_usd: float


class UsageByDay(BaseModel):
    date: str
    requests: int
    tokens: int
    cost_usd: float


class AIUsageSummaryResponse(BaseModel):
    provider: str
    period: str
    total_requests: int
    total_tokens: int
    total_cost_usd: float
    by_feature: list[UsageByFeature]
    by_day: list[UsageByDay]


# --- Helpers ---

def _get_env_api_key() -> Optional[str]:
    """Get Anthropic API key from environment variables."""
    return getattr(settings, "ANTHROPIC_API_KEY", None)


def _default_feature_config() -> dict[str, bool]:
    """Default: all features enabled."""
    return {k: True for k in ALL_FEATURES}


# --- Endpoints ---

@router.get("/anthropic/status", response_model=AIProviderStatusResponse)
async def get_anthropic_status(
    db: DbSession,
    current_user: CurrentUser,
):
    """Get Anthropic Claude connection status."""
    result = await db.execute(
        select(AIProviderConfig).where(AIProviderConfig.provider == "anthropic")
    )
    config = result.scalar_one_or_none()

    env_key = _get_env_api_key()

    if config and config.is_active and config.api_key_encrypted:
        return AIProviderStatusResponse(
            provider="anthropic",
            connected=True,
            is_primary=config.is_primary,
            model=config.model_config_data.get("default_model", DEFAULT_MODEL),
            available_models=AVAILABLE_MODELS,
            features_enabled=config.feature_config or _default_feature_config(),
            connected_by=config.connected_by,
            connected_at=config.connected_at.isoformat() if config.connected_at else None,
            last_used_at=config.last_used_at.isoformat() if config.last_used_at else None,
            api_key_configured=True,
            api_key_source="database",
        )

    if env_key:
        return AIProviderStatusResponse(
            provider="anthropic",
            connected=True,
            is_primary=config.is_primary if config else False,
            model=DEFAULT_MODEL,
            available_models=AVAILABLE_MODELS,
            features_enabled=config.feature_config if config else _default_feature_config(),
            connected_by="environment",
            connected_at=None,
            last_used_at=config.last_used_at.isoformat() if config and config.last_used_at else None,
            api_key_configured=True,
            api_key_source="environment",
        )

    return AIProviderStatusResponse(
        provider="anthropic",
        connected=False,
        is_primary=False,
        model=None,
        available_models=AVAILABLE_MODELS,
        features_enabled={},
        api_key_configured=False,
        api_key_source="none",
    )


@router.post("/anthropic/connect")
async def connect_anthropic(
    request: AIProviderConnectRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Connect Anthropic Claude by providing an API key. Validates the key first."""
    # Validate the key by making a test call
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                ANTHROPIC_API_URL,
                headers={
                    "x-api-key": request.api_key,
                    "anthropic-version": ANTHROPIC_VERSION,
                    "content-type": "application/json",
                },
                json={
                    "model": request.model,
                    "max_tokens": 10,
                    "messages": [{"role": "user", "content": "Say hello"}],
                },
            )
            if response.status_code == 401:
                raise HTTPException(status_code=400, detail="Invalid API key")
            response.raise_for_status()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            raise HTTPException(status_code=400, detail="Invalid API key")
        raise HTTPException(status_code=400, detail=f"API validation failed: {e.response.status_code}")
    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail="Cannot reach Anthropic API")

    # Encrypt and store
    encrypted_key = encrypt_value(request.api_key)
    features = request.features or _default_feature_config()

    # Upsert config
    result = await db.execute(
        select(AIProviderConfig).where(AIProviderConfig.provider == "anthropic")
    )
    config = result.scalar_one_or_none()

    if config:
        config.api_key_encrypted = encrypted_key
        config.is_active = True
        config.is_primary = request.set_as_primary
        config.model_config_data = {"default_model": request.model, "available_models": AVAILABLE_MODELS}
        config.feature_config = features
        config.connected_by = current_user.email
        config.connected_at = datetime.now(timezone.utc)
    else:
        config = AIProviderConfig(
            provider="anthropic",
            api_key_encrypted=encrypted_key,
            is_active=True,
            is_primary=request.set_as_primary,
            model_config_data={"default_model": request.model, "available_models": AVAILABLE_MODELS},
            feature_config=features,
            connected_by=current_user.email,
            connected_at=datetime.now(timezone.utc),
        )
        db.add(config)

    # If setting as primary, unset other providers
    if request.set_as_primary:
        await db.execute(
            select(AIProviderConfig)
            .where(AIProviderConfig.provider != "anthropic")
        )
        # Simple approach: just mark this one as primary
        # Other providers would be set is_primary=False if they existed

    await db.commit()
    return {"success": True, "message": "Claude AI connected successfully"}


@router.post("/anthropic/disconnect")
async def disconnect_anthropic(
    db: DbSession,
    current_user: CurrentUser,
):
    """Disconnect Anthropic Claude."""
    result = await db.execute(
        select(AIProviderConfig).where(AIProviderConfig.provider == "anthropic")
    )
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(status_code=404, detail="Anthropic not configured")

    config.is_active = False
    config.is_primary = False
    config.api_key_encrypted = None
    await db.commit()

    return {"success": True, "message": "Claude AI disconnected"}


@router.post("/anthropic/test", response_model=AIProviderTestResponse)
async def test_anthropic(
    db: DbSession,
    current_user: CurrentUser,
):
    """Test the Anthropic connection with a lightweight API call."""
    # Get API key
    result = await db.execute(
        select(AIProviderConfig).where(AIProviderConfig.provider == "anthropic")
    )
    config = result.scalar_one_or_none()

    api_key = None
    model = DEFAULT_MODEL

    if config and config.is_active and config.api_key_encrypted:
        api_key = decrypt_value(config.api_key_encrypted)
        model = config.model_config_data.get("default_model", DEFAULT_MODEL)

    if not api_key:
        api_key = _get_env_api_key()

    if not api_key:
        return AIProviderTestResponse(
            success=False,
            model=model,
            response_time_ms=0,
            message="No API key configured",
        )

    try:
        start = time.time()
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                ANTHROPIC_API_URL,
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": ANTHROPIC_VERSION,
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 20,
                    "messages": [{"role": "user", "content": "Say hello in one word."}],
                },
            )
            duration_ms = int((time.time() - start) * 1000)
            response.raise_for_status()
            data = response.json()
            content = data.get("content", [{}])[0].get("text", "")

            return AIProviderTestResponse(
                success=True,
                model=model,
                response_time_ms=duration_ms,
                message=f"Response: {content}",
            )
    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        return AIProviderTestResponse(
            success=False,
            model=model,
            response_time_ms=duration_ms,
            message=str(e)[:200],
        )


@router.patch("/anthropic/config", response_model=AIProviderStatusResponse)
async def update_anthropic_config(
    request: AIProviderUpdateRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update Anthropic config (model, features, primary status)."""
    result = await db.execute(
        select(AIProviderConfig).where(AIProviderConfig.provider == "anthropic")
    )
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(status_code=404, detail="Anthropic not configured")

    if request.model is not None:
        config.model_config_data = {
            **config.model_config_data,
            "default_model": request.model,
        }

    if request.is_primary is not None:
        config.is_primary = request.is_primary

    if request.features is not None:
        config.feature_config = {
            **(config.feature_config or {}),
            **request.features,
        }

    await db.commit()
    await db.refresh(config)

    return AIProviderStatusResponse(
        provider="anthropic",
        connected=config.is_active and config.api_key_encrypted is not None,
        is_primary=config.is_primary,
        model=config.model_config_data.get("default_model", DEFAULT_MODEL),
        available_models=AVAILABLE_MODELS,
        features_enabled=config.feature_config or {},
        connected_by=config.connected_by,
        connected_at=config.connected_at.isoformat() if config.connected_at else None,
        last_used_at=config.last_used_at.isoformat() if config.last_used_at else None,
        api_key_configured=True,
        api_key_source="database",
    )


@router.get("/anthropic/usage", response_model=AIUsageSummaryResponse)
async def get_anthropic_usage(
    db: DbSession,
    current_user: CurrentUser,
    period: str = Query("month", pattern="^(today|week|month)$"),
):
    """Get Anthropic usage statistics for a given period."""
    now = datetime.now(timezone.utc)
    if period == "today":
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        start_date = now - timedelta(days=7)
    else:
        start_date = now - timedelta(days=30)

    # Total aggregates
    totals_q = select(
        func.count(AIUsageLog.id).label("total_requests"),
        func.coalesce(func.sum(AIUsageLog.total_tokens), 0).label("total_tokens"),
        func.coalesce(func.sum(AIUsageLog.cost_cents), 0).label("total_cost_cents"),
    ).where(
        and_(
            AIUsageLog.provider == "anthropic",
            AIUsageLog.created_at >= start_date,
        )
    )
    totals_result = await db.execute(totals_q)
    totals = totals_result.one()

    # By feature
    feature_q = select(
        AIUsageLog.feature,
        func.count(AIUsageLog.id).label("requests"),
        func.coalesce(func.sum(AIUsageLog.total_tokens), 0).label("tokens"),
        func.coalesce(func.sum(AIUsageLog.cost_cents), 0).label("cost_cents"),
    ).where(
        and_(
            AIUsageLog.provider == "anthropic",
            AIUsageLog.created_at >= start_date,
        )
    ).group_by(AIUsageLog.feature)
    feature_result = await db.execute(feature_q)
    by_feature = [
        UsageByFeature(
            feature=row.feature,
            feature_label=ALL_FEATURES.get(row.feature, row.feature),
            requests=row.requests,
            tokens=row.tokens,
            cost_usd=round(row.cost_cents / 100, 4),
        )
        for row in feature_result
    ]

    # By day
    day_q = select(
        cast(AIUsageLog.created_at, Date).label("day"),
        func.count(AIUsageLog.id).label("requests"),
        func.coalesce(func.sum(AIUsageLog.total_tokens), 0).label("tokens"),
        func.coalesce(func.sum(AIUsageLog.cost_cents), 0).label("cost_cents"),
    ).where(
        and_(
            AIUsageLog.provider == "anthropic",
            AIUsageLog.created_at >= start_date,
        )
    ).group_by("day").order_by("day")
    day_result = await db.execute(day_q)
    by_day = [
        UsageByDay(
            date=str(row.day),
            requests=row.requests,
            tokens=row.tokens,
            cost_usd=round(row.cost_cents / 100, 4),
        )
        for row in day_result
    ]

    return AIUsageSummaryResponse(
        provider="anthropic",
        period=period,
        total_requests=totals.total_requests,
        total_tokens=totals.total_tokens,
        total_cost_usd=round(totals.total_cost_cents / 100, 4),
        by_feature=by_feature,
        by_day=by_day,
    )
