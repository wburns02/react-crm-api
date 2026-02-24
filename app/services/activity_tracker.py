"""
User Activity Tracker — async, fire-and-forget activity logging.

Performance design:
- Uses background tasks (won't slow down API responses)
- Batches inserts when possible
- Skips noisy endpoints (health, metrics, static)
- Auto-prunes records older than 90 days
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker

logger = logging.getLogger(__name__)

# Endpoints to skip (high-frequency, low-value)
SKIP_ENDPOINTS = {
    "/health",
    "/metrics",
    "/favicon.ico",
    "/api/v2/auth/me",  # Called every 5 min by frontend — too noisy
    "/api/v2/ws",  # WebSocket
}

# Prefixes to skip
SKIP_PREFIXES = (
    "/assets/",
    "/static/",
    "/_next/",
)


async def log_activity(
    *,
    category: str,
    action: str,
    description: Optional[str] = None,
    user_id: Optional[int] = None,
    user_email: Optional[str] = None,
    user_name: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    source: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    endpoint: Optional[str] = None,
    http_method: Optional[str] = None,
    status_code: Optional[int] = None,
    response_time_ms: Optional[int] = None,
    session_id: Optional[str] = None,
    entity_id: Optional[str] = None,
) -> None:
    """Log a user activity event. Fire-and-forget — errors are swallowed."""
    try:
        async with async_session_maker() as db:
            await db.execute(
                text("""
                    INSERT INTO user_activity_log
                    (id, user_id, user_email, user_name, category, action, description,
                     ip_address, user_agent, source, resource_type, resource_id,
                     endpoint, http_method, status_code, response_time_ms,
                     session_id, entity_id, created_at)
                    VALUES
                    (:id, :user_id, :user_email, :user_name, :category, :action, :description,
                     :ip_address, :user_agent, :source, :resource_type, :resource_id,
                     :endpoint, :http_method, :status_code, :response_time_ms,
                     :session_id, :entity_id, NOW())
                """),
                {
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "user_email": user_email,
                    "user_name": user_name,
                    "category": category,
                    "action": action,
                    "description": description,
                    "ip_address": ip_address,
                    "user_agent": user_agent,
                    "source": source,
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "endpoint": endpoint,
                    "http_method": http_method,
                    "status_code": status_code,
                    "response_time_ms": response_time_ms,
                    "session_id": session_id,
                    "entity_id": entity_id,
                },
            )
            await db.commit()
    except Exception as e:
        # Never let activity logging break the app
        logger.debug(f"Activity log insert failed (non-critical): {e}")


def get_client_ip(request) -> str:
    """Extract real client IP from request, respecting proxy headers."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def should_track_endpoint(path: str) -> bool:
    """Return True if this endpoint should be tracked."""
    if path in SKIP_ENDPOINTS:
        return False
    for prefix in SKIP_PREFIXES:
        if path.startswith(prefix):
            return False
    return True


def extract_resource_info(path: str) -> tuple[Optional[str], Optional[str]]:
    """Extract resource type and ID from API path.

    Examples:
        /api/v2/work-orders/abc-123 → ('work_order', 'abc-123')
        /api/v2/customers/def-456 → ('customer', 'def-456')
        /api/v2/invoices → ('invoice', None)
    """
    parts = path.strip("/").split("/")
    # Skip api/v2 prefix
    if len(parts) >= 2 and parts[0] == "api" and parts[1] == "v2":
        parts = parts[2:]

    if not parts:
        return None, None

    resource_type = parts[0].replace("-", "_").rstrip("s")  # work-orders → work_order
    resource_id = parts[1] if len(parts) > 1 and not parts[1].startswith("{") else None

    return resource_type, resource_id


async def prune_old_activity(days: int = 90) -> int:
    """Delete activity log entries older than N days. Returns count deleted."""
    try:
        async with async_session_maker() as db:
            result = await db.execute(
                text("DELETE FROM user_activity_log WHERE created_at < NOW() - MAKE_INTERVAL(days => :days)"),
                {"days": days},
            )
            await db.commit()
            return result.rowcount
    except Exception as e:
        logger.warning(f"Activity log pruning failed: {e}")
        return 0
