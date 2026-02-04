"""
Middleware modules for the CRM API.

Provides request processing middleware for:
- Correlation ID tracking for distributed tracing
- Structured logging with context injection
- Prometheus metrics collection
- Cache-Control headers for browser caching
- Server-Timing headers for performance debugging
"""

from .correlation import CorrelationIdMiddleware, correlation_id_ctx, request_id_ctx
from .metrics import MetricsMiddleware
from .cache_headers import CacheHeadersMiddleware
from .timing import ServerTimingMiddleware

__all__ = [
    "CorrelationIdMiddleware",
    "correlation_id_ctx",
    "request_id_ctx",
    "MetricsMiddleware",
    "CacheHeadersMiddleware",
    "ServerTimingMiddleware",
]
