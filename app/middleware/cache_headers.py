"""
Cache-Control headers middleware for API performance.

Adds appropriate caching headers based on endpoint patterns to improve
browser caching and reduce unnecessary requests.
"""

import re
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from typing import Callable, List, Tuple


class CacheHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds Cache-Control headers based on endpoint patterns.

    Cache Strategies:
    - Public, read-only endpoints: Cache aggressively with stale-while-revalidate
    - Authenticated endpoints: Private caching only
    - Write operations (POST/PUT/DELETE): No caching
    """

    # Endpoints safe to cache publicly (no auth required, read-only)
    # Format: (pattern, max_age_seconds)
    PUBLIC_CACHEABLE: List[Tuple[str, int]] = [
        (r"^/health$", 60),  # 1 minute
        (r"^/ping$", 30),  # 30 seconds
        (r"^/$", 300),  # 5 minutes - root endpoint
        (r"^/api/v2/availability/slots", 120),  # 2 minutes - landing page
        (r"^/api/v2/availability/next-available", 120),  # 2 minutes
        (r"^/api/public/", 300),  # 5 minutes - public API
    ]

    # Endpoints with private caching (authenticated, read-only)
    # NOTE: work-orders removed — HTTP caching causes stale data after
    # drag-drop optimistic updates (invalidateQueries refetch gets cached response)
    PRIVATE_CACHEABLE: List[Tuple[str, int]] = [
        (r"^/api/v2/dashboard/stats", 60),  # 1 minute
        (r"^/api/v2/technicians$", 60),  # 1 minute
        (r"^/api/v2/marketing-hub/tasks$", 60),  # 1 minute
    ]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        # Skip cache headers for error responses
        if response.status_code >= 400:
            return response

        # Skip cache headers for write operations - explicitly no-store
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            response.headers["Cache-Control"] = "no-store"
            return response

        path = request.url.path

        # Check public cacheable endpoints
        for pattern, max_age in self.PUBLIC_CACHEABLE:
            if re.match(pattern, path):
                # Public caching with stale-while-revalidate for better UX
                response.headers["Cache-Control"] = (
                    f"public, max-age={max_age}, stale-while-revalidate={max_age * 2}"
                )
                return response

        # Check private cacheable endpoints
        for pattern, max_age in self.PRIVATE_CACHEABLE:
            if re.match(pattern, path):
                response.headers["Cache-Control"] = (
                    f"private, max-age={max_age}, stale-while-revalidate={max_age}"
                )
                return response

        # Default: private, no-cache for other API endpoints
        # This still allows conditional requests with ETags
        if path.startswith("/api/"):
            response.headers["Cache-Control"] = "private, no-cache"

        return response
