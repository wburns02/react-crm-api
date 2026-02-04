"""
Server-Timing header middleware for performance debugging.

Adds Server-Timing and X-Response-Time headers to all responses,
enabling performance analysis in browser DevTools.
"""

import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from typing import Callable


class ServerTimingMiddleware(BaseHTTPMiddleware):
    """
    Add Server-Timing header for performance debugging.

    This header is visible in browser DevTools Network tab under "Timing"
    and helps identify backend processing time vs network latency.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.perf_counter()

        response = await call_next(request)

        # Calculate processing time in milliseconds
        process_time_ms = (time.perf_counter() - start_time) * 1000

        # Server-Timing header - visible in browser DevTools
        # Format: metric;dur=duration;desc="description"
        response.headers["Server-Timing"] = f"total;dur={process_time_ms:.1f};desc=\"Server Processing\""

        # X-Response-Time header - simpler format for logging/monitoring
        response.headers["X-Response-Time"] = f"{process_time_ms:.1f}ms"

        return response
