"""
Activity Tracking Middleware — logs authenticated API requests.

Performance notes:
- Logging happens AFTER the response is sent (fire-and-forget via asyncio.create_task)
- Skips health/metrics/auth-me and static endpoints
- Only logs authenticated requests (has JWT session cookie or Bearer token)
- Adds ~0ms latency to requests (async background task)
"""
import asyncio
import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.services.activity_tracker import (
    log_activity,
    get_client_ip,
    should_track_endpoint,
    extract_resource_info,
)

logger = logging.getLogger(__name__)

# Only track mutating or significant read endpoints
# Skip GET list endpoints to reduce noise — focus on actions
TRACKED_METHODS = {"POST", "PATCH", "PUT", "DELETE"}


class ActivityTrackingMiddleware(BaseHTTPMiddleware):
    """Lightweight middleware that logs user actions asynchronously."""

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        method = request.method

        # Quick bail for endpoints we don't care about
        if not should_track_endpoint(path):
            return await call_next(request)

        # Only track mutating requests + important GETs
        # (GET tracking would be too noisy for a CRM with constant polling)
        if method not in TRACKED_METHODS:
            return await call_next(request)

        start_time = time.time()
        response = await call_next(request)
        elapsed_ms = int((time.time() - start_time) * 1000)

        # Only log if there's a user (authenticated request)
        # We check for the session cookie or auth header
        has_auth = (
            request.cookies.get("session")
            or request.headers.get("authorization", "").startswith("Bearer ")
        )
        if not has_auth:
            return response

        # Extract user info from request state (set by auth dependency)
        # We can't always get this from middleware, so we use what's available
        user_email = None
        user_id = None
        try:
            if hasattr(request.state, "user"):
                user_email = request.state.user.email
                user_id = request.state.user.id
        except Exception:
            pass

        # Extract info
        resource_type, resource_id = extract_resource_info(path)
        session_id = request.headers.get("x-correlation-id", "")
        entity_id = request.headers.get("x-entity-id", "")
        source = request.headers.get("x-source", "crm")
        ip = get_client_ip(request)
        ua = (request.headers.get("user-agent", ""))[:500]

        # Determine action from method
        action_map = {
            "POST": "create",
            "PATCH": "update",
            "PUT": "update",
            "DELETE": "delete",
        }
        action = action_map.get(method, "api_call")

        # Build description
        desc = f"{method} {path}"
        if response.status_code >= 400:
            desc += f" → {response.status_code}"

        # Fire and forget — don't await, don't slow down the response
        asyncio.create_task(
            log_activity(
                category="action",
                action=action,
                description=desc,
                user_id=user_id,
                user_email=user_email,
                ip_address=ip,
                user_agent=ua,
                source=source,
                resource_type=resource_type,
                resource_id=resource_id,
                endpoint=path[:200],
                http_method=method,
                status_code=response.status_code,
                response_time_ms=elapsed_ms,
                session_id=session_id,
                entity_id=entity_id,
            )
        )

        return response
