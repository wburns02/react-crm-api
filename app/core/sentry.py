"""
Sentry error tracking integration for the CRM backend.

Provides:
- Automatic exception capture
- Performance monitoring
- Request context
- User context
"""

import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Global flag to track initialization
_sentry_initialized = False


def init_sentry() -> None:
    """
    Initialize Sentry SDK with FastAPI integration.

    Called during application startup in main.py.
    """
    global _sentry_initialized

    from app.config import settings

    # Check if Sentry DSN is configured
    sentry_dsn = getattr(settings, "SENTRY_DSN", None)
    if not sentry_dsn:
        logger.info("Sentry DSN not configured, error tracking disabled")
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration

        sentry_sdk.init(
            dsn=sentry_dsn,
            environment=settings.ENVIRONMENT,
            release=getattr(settings, "VERSION", "unknown"),
            # Performance monitoring
            traces_sample_rate=0.1 if settings.is_production else 1.0,
            profiles_sample_rate=0.1 if settings.is_production else 0.0,
            # Integrations
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                SqlalchemyIntegration(),
                LoggingIntegration(
                    level=logging.WARNING,
                    event_level=logging.ERROR,
                ),
            ],
            # Filter sensitive data
            before_send=filter_sensitive_data,
            # Additional options
            send_default_pii=False,
            attach_stacktrace=True,
            max_breadcrumbs=50,
        )

        _sentry_initialized = True
        logger.info(f"Sentry initialized for {settings.ENVIRONMENT} environment")

    except ImportError:
        logger.warning("sentry-sdk not installed, error tracking disabled")
    except Exception as e:
        logger.warning(f"Failed to initialize Sentry: {e}")


def filter_sensitive_data(event: Dict[str, Any], hint: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Filter sensitive data before sending to Sentry.

    Removes:
    - Authorization headers
    - Passwords
    - API keys
    - Session tokens
    """
    # Filter request headers
    if "request" in event and "headers" in event["request"]:
        headers = event["request"]["headers"]
        sensitive_headers = ["authorization", "cookie", "x-csrf-token", "x-api-key"]
        for header in sensitive_headers:
            if header in headers:
                headers[header] = "[Filtered]"

    # Filter request body
    if "request" in event and "data" in event["request"]:
        data = event["request"]["data"]
        if isinstance(data, dict):
            sensitive_fields = ["password", "token", "secret", "api_key", "credit_card", "ssn", "social_security"]
            for field in sensitive_fields:
                if field in data:
                    data[field] = "[Filtered]"

    return event


def capture_exception(
    exception: Exception,
    context: Optional[Dict[str, Any]] = None,
    user: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    Capture an exception to Sentry with additional context.

    Args:
        exception: The exception to capture
        context: Additional context data
        user: User information

    Returns:
        Sentry event ID if captured, None otherwise
    """
    if not _sentry_initialized:
        return None

    try:
        import sentry_sdk

        with sentry_sdk.push_scope() as scope:
            if context:
                for key, value in context.items():
                    scope.set_extra(key, value)

            if user:
                scope.set_user(user)

            return sentry_sdk.capture_exception(exception)

    except Exception as e:
        logger.warning(f"Failed to capture exception to Sentry: {e}")
        return None


def capture_message(
    message: str,
    level: str = "info",
    context: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    Capture a message to Sentry.

    Args:
        message: The message to capture
        level: Log level (debug, info, warning, error, fatal)
        context: Additional context data

    Returns:
        Sentry event ID if captured, None otherwise
    """
    if not _sentry_initialized:
        return None

    try:
        import sentry_sdk

        with sentry_sdk.push_scope() as scope:
            if context:
                for key, value in context.items():
                    scope.set_extra(key, value)

            return sentry_sdk.capture_message(message, level=level)

    except Exception as e:
        logger.warning(f"Failed to capture message to Sentry: {e}")
        return None


def set_user_context(user_id: str, email: Optional[str] = None, role: Optional[str] = None) -> None:
    """Set user context for all subsequent events in this request."""
    if not _sentry_initialized:
        return

    try:
        import sentry_sdk

        sentry_sdk.set_user(
            {
                "id": user_id,
                "email": email,
                "role": role,
            }
        )
    except Exception:
        pass


def add_breadcrumb(
    message: str,
    category: str,
    level: str = "info",
    data: Optional[Dict[str, Any]] = None,
) -> None:
    """Add a breadcrumb for debugging context."""
    if not _sentry_initialized:
        return

    try:
        import sentry_sdk

        sentry_sdk.add_breadcrumb(
            message=message,
            category=category,
            level=level,
            data=data,
        )
    except Exception:
        pass
