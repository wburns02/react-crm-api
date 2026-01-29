"""
OpenTelemetry APM integration.

Provides distributed tracing for the CRM API with:
- Automatic instrumentation for FastAPI, SQLAlchemy, Redis, HTTPX
- Custom @traced() decorator for business operations
- OTLP exporter for sending traces to backends (Jaeger, Tempo, etc.)

Usage:
    # Initialize on startup
    from app.core.telemetry import init_telemetry
    init_telemetry()

    # Custom tracing
    from app.core.telemetry import traced, get_tracer

    @traced("process_payment")
    async def process_payment(payment_id: int):
        ...
"""

import logging
from typing import Optional, Callable, TypeVar, Any
from functools import wraps
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Type variable for generic return types
T = TypeVar("T")

# Global tracer instance
_tracer = None
_initialized = False


def init_telemetry() -> bool:
    """
    Initialize OpenTelemetry instrumentation.

    Configures tracing with OTLP exporter if endpoint is configured.
    Falls back to no-op if OpenTelemetry packages are not installed.

    Returns:
        True if telemetry was initialized, False otherwise
    """
    global _tracer, _initialized

    if _initialized:
        return _tracer is not None

    _initialized = True

    from app.config import settings
    endpoint = settings.OTEL_EXPORTER_OTLP_ENDPOINT
    service_name = settings.OTEL_SERVICE_NAME

    if not endpoint:
        logger.info("OpenTelemetry disabled (OTEL_EXPORTER_OTLP_ENDPOINT not set)")
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME

        # Create resource with service name
        resource = Resource(attributes={
            SERVICE_NAME: service_name,
        })

        # Create tracer provider
        provider = TracerProvider(resource=resource)

        # Configure OTLP exporter
        exporter = OTLPSpanExporter(endpoint=endpoint)
        processor = BatchSpanProcessor(exporter)
        provider.add_span_processor(processor)

        # Set global tracer provider
        trace.set_tracer_provider(provider)

        # Get tracer
        _tracer = trace.get_tracer(service_name)

        # Auto-instrument frameworks
        _instrument_frameworks()

        logger.info(f"OpenTelemetry initialized with endpoint: {endpoint}")
        return True

    except ImportError as e:
        logger.warning(f"OpenTelemetry packages not installed: {e}")
        return False
    except Exception as e:
        logger.warning(f"Failed to initialize OpenTelemetry: {e}")
        return False


def _instrument_frameworks():
    """Auto-instrument supported frameworks."""
    # FastAPI
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor().instrument()
        logger.debug("Instrumented FastAPI")
    except ImportError:
        pass

    # SQLAlchemy
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        SQLAlchemyInstrumentor().instrument()
        logger.debug("Instrumented SQLAlchemy")
    except ImportError:
        pass

    # Redis
    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        RedisInstrumentor().instrument()
        logger.debug("Instrumented Redis")
    except ImportError:
        pass

    # HTTPX (for external API calls)
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        HTTPXClientInstrumentor().instrument()
        logger.debug("Instrumented HTTPX")
    except ImportError:
        pass


def get_tracer():
    """Get the global tracer instance."""
    global _tracer
    if _tracer is None and not _initialized:
        init_telemetry()
    return _tracer


def traced(
    name: Optional[str] = None,
    attributes: Optional[dict] = None,
):
    """
    Decorator for tracing function execution.

    Creates a span for the decorated function with automatic
    timing and error capture.

    Args:
        name: Span name (defaults to function name)
        attributes: Additional span attributes

    Example:
        @traced("process_payment")
        async def process_payment(payment_id: int):
            ...

        @traced(attributes={"operation": "bulk_import"})
        def import_customers(data: list):
            ...
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        span_name = name or func.__name__

        if _is_async(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs) -> T:
                tracer = get_tracer()
                if tracer is None:
                    return await func(*args, **kwargs)

                with tracer.start_as_current_span(span_name) as span:
                    if attributes:
                        for key, value in attributes.items():
                            span.set_attribute(key, value)
                    try:
                        result = await func(*args, **kwargs)
                        return result
                    except Exception as e:
                        span.record_exception(e)
                        span.set_status(trace_status_error())
                        raise

            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs) -> T:
                tracer = get_tracer()
                if tracer is None:
                    return func(*args, **kwargs)

                with tracer.start_as_current_span(span_name) as span:
                    if attributes:
                        for key, value in attributes.items():
                            span.set_attribute(key, value)
                    try:
                        result = func(*args, **kwargs)
                        return result
                    except Exception as e:
                        span.record_exception(e)
                        span.set_status(trace_status_error())
                        raise

            return sync_wrapper

    return decorator


def _is_async(func: Callable) -> bool:
    """Check if function is async."""
    import asyncio
    return asyncio.iscoroutinefunction(func)


def trace_status_error():
    """Get error status for span."""
    try:
        from opentelemetry.trace import StatusCode, Status
        return Status(StatusCode.ERROR)
    except ImportError:
        return None


@contextmanager
def span(name: str, attributes: Optional[dict] = None):
    """
    Context manager for creating a span.

    Usage:
        with span("process_item", {"item_id": item.id}):
            do_processing()
    """
    tracer = get_tracer()
    if tracer is None:
        yield None
        return

    with tracer.start_as_current_span(name) as s:
        if attributes:
            for key, value in attributes.items():
                s.set_attribute(key, value)
        yield s


def add_span_attribute(key: str, value: Any):
    """Add attribute to current span."""
    try:
        from opentelemetry import trace
        current_span = trace.get_current_span()
        if current_span:
            current_span.set_attribute(key, value)
    except ImportError:
        pass


def record_exception(exception: Exception):
    """Record exception on current span."""
    try:
        from opentelemetry import trace
        current_span = trace.get_current_span()
        if current_span:
            current_span.record_exception(exception)
    except ImportError:
        pass
