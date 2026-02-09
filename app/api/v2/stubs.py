"""
Stub endpoints for routes the frontend calls but don't have real implementations yet.

These return empty but valid 200 responses so the frontend doesn't get 404 errors.
Each response includes an X-Stub: true header so the frontend can detect these are stubs.

To replace a stub with a real implementation, move the endpoint to the appropriate
module and remove it from here.
"""

from fastapi import APIRouter, Response
from app.api.deps import CurrentUser

# ---------------------------------------------------------------------------
# SMS stubs (prefix: /sms)
# ---------------------------------------------------------------------------
sms_router = APIRouter()


@sms_router.get("/templates")
async def sms_templates(response: Response, current_user: CurrentUser):
    """Return empty SMS templates list (stub)."""
    response.headers["X-Stub"] = "true"
    return {"items": [], "total": 0}


@sms_router.get("/conversations")
async def sms_conversations(response: Response, current_user: CurrentUser):
    """Return empty SMS conversations list (stub)."""
    response.headers["X-Stub"] = "true"
    return {"items": [], "total": 0}


@sms_router.get("/stats")
async def sms_stats(response: Response, current_user: CurrentUser):
    """Return zeroed SMS statistics (stub)."""
    response.headers["X-Stub"] = "true"
    return {"total_sent": 0, "total_received": 0, "total_failed": 0}


@sms_router.get("/settings")
async def sms_settings(response: Response, current_user: CurrentUser):
    """Return disabled SMS settings (stub)."""
    response.headers["X-Stub"] = "true"
    return {"enabled": False, "provider": None}


# ---------------------------------------------------------------------------
# Templates stubs (prefix: /templates)
# ---------------------------------------------------------------------------
templates_router = APIRouter()


@templates_router.get("")
async def list_templates(response: Response, current_user: CurrentUser):
    """Return empty templates list (stub)."""
    response.headers["X-Stub"] = "true"
    return {"items": [], "total": 0}


# ---------------------------------------------------------------------------
# Reminders stubs (prefix: /reminders)
# ---------------------------------------------------------------------------
reminders_router = APIRouter()


@reminders_router.get("")
async def list_reminders(response: Response, current_user: CurrentUser):
    """Return empty reminders list (stub)."""
    response.headers["X-Stub"] = "true"
    return {"items": [], "total": 0}


# ---------------------------------------------------------------------------
# Billing stubs (prefix: /billing)
# ---------------------------------------------------------------------------
billing_router = APIRouter()


@billing_router.get("/stats")
async def billing_stats(response: Response, current_user: CurrentUser):
    """Return zeroed billing statistics (stub)."""
    response.headers["X-Stub"] = "true"
    return {"total_revenue": 0, "outstanding": 0, "overdue": 0}


# ---------------------------------------------------------------------------
# Analytics stubs (prefix: /analytics)
# These are registered as a separate sub-router under the /analytics prefix
# to avoid conflicts with the existing analytics module.
# ---------------------------------------------------------------------------
analytics_stubs_router = APIRouter()


@analytics_stubs_router.get("/performance/summary")
async def analytics_performance_summary(response: Response, current_user: CurrentUser):
    """Return empty performance summary metrics (stub)."""
    response.headers["X-Stub"] = "true"
    return {"metrics": [], "period": "30d"}


@analytics_stubs_router.get("/ai/insights")
async def analytics_ai_insights(response: Response, current_user: CurrentUser):
    """Return empty AI-generated insights (stub)."""
    response.headers["X-Stub"] = "true"
    return {"insights": [], "generated_at": None}


# ---------------------------------------------------------------------------
# Tracking stubs (prefix: /tracking)
# ---------------------------------------------------------------------------
tracking_router = APIRouter()


@tracking_router.get("/dispatch/active")
async def tracking_dispatch_active(response: Response, current_user: CurrentUser):
    """Return empty active dispatches list (stub)."""
    response.headers["X-Stub"] = "true"
    return {"dispatches": [], "total": 0}


# ---------------------------------------------------------------------------
# Predictions stubs (prefix: /predictions)
# These are registered as a separate sub-router under the /predictions prefix
# to avoid conflicts with the existing predictions module.
# ---------------------------------------------------------------------------
predictions_stubs_router = APIRouter()


@predictions_stubs_router.get("/predictions")
async def predictions_list(response: Response, current_user: CurrentUser):
    """Return empty predictions list (stub)."""
    response.headers["X-Stub"] = "true"
    return {"items": [], "total": 0}


@predictions_stubs_router.get("/alerts")
async def predictions_alerts(response: Response, current_user: CurrentUser):
    """Return empty prediction alerts list (stub)."""
    response.headers["X-Stub"] = "true"
    return {"items": [], "total": 0}


# ---------------------------------------------------------------------------
# Help Center stubs (prefix: /help)
# Note: /onboarding/help/* routes already exist in onboarding.py.
# These stubs serve the top-level /help/* paths the frontend calls.
# ---------------------------------------------------------------------------
help_router = APIRouter()


@help_router.get("/articles")
async def help_articles(response: Response, current_user: CurrentUser):
    """Return empty help articles list (stub)."""
    response.headers["X-Stub"] = "true"
    return {"items": [], "total": 0}


@help_router.get("/categories")
async def help_categories(response: Response, current_user: CurrentUser):
    """Return empty help categories list (stub)."""
    response.headers["X-Stub"] = "true"
    return {"items": [], "total": 0}


# ---------------------------------------------------------------------------
# AI Communications stubs (prefix: /ai)
# These are registered as a separate sub-router under the /ai prefix
# to avoid conflicts with the existing ai module.
# ---------------------------------------------------------------------------
ai_stubs_router = APIRouter()


@ai_stubs_router.get("/communications/analytics")
async def ai_communications_analytics(response: Response, current_user: CurrentUser):
    """Return empty AI communications analytics (stub)."""
    response.headers["X-Stub"] = "true"
    return {"metrics": {}, "period": "30d"}


@ai_stubs_router.get("/maintenance/predictions")
async def ai_maintenance_predictions(response: Response, current_user: CurrentUser):
    """Return empty AI maintenance predictions (stub)."""
    response.headers["X-Stub"] = "true"
    return {"items": [], "total": 0}
