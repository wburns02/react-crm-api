"""
Correlation ID middleware for distributed tracing.

Extracts or generates correlation IDs and request IDs from incoming requests,
making them available via context variables for logging and error handling.

Headers:
- X-Correlation-ID: Session-level ID from the client (persists across requests)
- X-Request-ID: Per-request unique identifier

Usage:
    from app.middleware.correlation import correlation_id_ctx, request_id_ctx

    correlation_id = correlation_id_ctx.get()
    request_id = request_id_ctx.get()
"""

import uuid
import logging
from contextvars import ContextVar
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# Context variables for correlation IDs
# These are thread-safe and async-safe, isolated per request
correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="")
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


def generate_id() -> str:
    """Generate a short unique ID suitable for logging."""
    return str(uuid.uuid4())[:12]


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware that extracts/generates correlation IDs for request tracing.

    Sets context variables that can be accessed anywhere in the request:
    - correlation_id_ctx: Session-level ID from client or generated
    - request_id_ctx: Per-request unique ID

    Also adds these IDs to response headers for client-side correlation.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Response]
    ) -> Response:
        # Extract correlation ID from request headers or generate new one
        correlation_id = request.headers.get("X-Correlation-ID")
        if not correlation_id:
            correlation_id = generate_id()

        # Extract request ID from headers or generate new one
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = generate_id()

        # Set context variables for use throughout the request lifecycle
        correlation_id_ctx.set(correlation_id)
        request_id_ctx.set(request_id)

        # Store in request state for easy access in route handlers
        request.state.correlation_id = correlation_id
        request.state.request_id = request_id

        # Process the request
        response = await call_next(request)

        # Add correlation headers to response for client-side debugging
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Request-ID"] = request_id

        return response


def get_correlation_id() -> str:
    """Get the current correlation ID from context."""
    return correlation_id_ctx.get() or "unknown"


def get_request_id() -> str:
    """Get the current request ID from context."""
    return request_id_ctx.get() or "unknown"


class CorrelationLogFilter(logging.Filter):
    """
    Logging filter that injects correlation IDs into log records.

    Usage:
        handler = logging.StreamHandler()
        handler.addFilter(CorrelationLogFilter())
        handler.setFormatter(logging.Formatter(
            '%(asctime)s [%(correlation_id)s] [%(request_id)s] %(message)s'
        ))
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = get_correlation_id()
        record.request_id = get_request_id()
        return True
