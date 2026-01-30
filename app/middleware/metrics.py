"""
Metrics collection middleware.

Automatically tracks HTTP request metrics for Prometheus.
"""

import time
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from typing import Callable

from app.core.metrics import track_request_start, track_request_end

logger = logging.getLogger(__name__)


class MetricsMiddleware(BaseHTTPMiddleware):
    """
    Middleware that automatically tracks HTTP request metrics.

    Collects:
    - Request count by method, status, and path
    - Request duration histogram
    - In-flight request count
    """

    # Paths to exclude from metrics to avoid noise
    EXCLUDED_PATHS = {
        "/health",
        "/metrics",
        "/favicon.ico",
    }

    async def dispatch(self, request: Request, call_next: Callable[[Request], Response]) -> Response:
        path = request.url.path

        # Skip metrics collection for excluded paths
        if path in self.EXCLUDED_PATHS:
            return await call_next(request)

        # Track request start
        start_time = track_request_start()

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            # Track failed requests as 500
            status_code = 500
            raise
        finally:
            # Track request end
            track_request_end(start_time=start_time, method=request.method, path=path, status_code=status_code)

        return response
