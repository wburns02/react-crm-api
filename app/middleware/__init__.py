"""
Middleware modules for the CRM API.

Provides request processing middleware for:
- Correlation ID tracking for distributed tracing
- Structured logging with context injection
- Prometheus metrics collection
"""

from .correlation import CorrelationIdMiddleware, correlation_id_ctx, request_id_ctx
from .metrics import MetricsMiddleware

__all__ = [
    "CorrelationIdMiddleware",
    "correlation_id_ctx",
    "request_id_ctx",
    "MetricsMiddleware",
]
