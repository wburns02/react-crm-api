"""
Twilio Webhook Signature Verification

This module provides security validation for Twilio webhooks to prevent
unauthorized requests from being processed.

Security: Validates X-Twilio-Signature header using HMAC-SHA1 with auth token.
"""

from functools import wraps
from fastapi import Request, HTTPException, status
from twilio.request_validator import RequestValidator
import logging

from app.config import settings

logger = logging.getLogger(__name__)


class TwilioSignatureValidator:
    """Validates Twilio webhook signatures."""

    def __init__(self):
        self._validator = None

    @property
    def validator(self) -> RequestValidator:
        """Lazy initialization of validator."""
        if self._validator is None:
            if not settings.TWILIO_AUTH_TOKEN:
                raise ValueError("TWILIO_AUTH_TOKEN not configured")
            self._validator = RequestValidator(settings.TWILIO_AUTH_TOKEN)
        return self._validator

    def get_full_url(self, request: Request) -> str:
        """
        Get the full URL for signature validation.

        Handles reverse proxy scenarios by checking X-Forwarded headers.
        Twilio signs against the public URL, not the internal one.
        """
        # Check for forwarded protocol (common with Railway, Heroku, etc.)
        forwarded_proto = request.headers.get("x-forwarded-proto", "")
        forwarded_host = request.headers.get("x-forwarded-host", "")

        if forwarded_proto and forwarded_host:
            # Build URL from forwarded headers
            scheme = forwarded_proto
            host = forwarded_host
            path = request.url.path
            query = str(request.url.query) if request.url.query else ""

            url = f"{scheme}://{host}{path}"
            if query:
                url = f"{url}?{query}"
            return url

        # Fall back to request URL
        return str(request.url)

    async def validate(self, request: Request) -> bool:
        """
        Validate Twilio signature from request.

        Args:
            request: FastAPI request object

        Returns:
            True if signature is valid

        Raises:
            HTTPException: If signature is missing or invalid
        """
        signature = request.headers.get("X-Twilio-Signature", "")

        if not signature:
            logger.warning(
                "Twilio webhook request missing X-Twilio-Signature header",
                extra={"path": request.url.path, "client": request.client.host if request.client else "unknown"},
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing Twilio signature")

        # Get form data for validation
        form_data = await request.form()
        params = {key: form_data[key] for key in form_data}

        # Get the URL Twilio used to sign
        url = self.get_full_url(request)

        # Validate signature
        try:
            is_valid = self.validator.validate(url, params, signature)
        except Exception as e:
            logger.error(f"Error validating Twilio signature: {type(e).__name__}")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Signature validation error")

        if not is_valid:
            logger.warning(
                "Invalid Twilio signature rejected",
                extra={
                    "path": request.url.path,
                    "url_used": url,
                    "client": request.client.host if request.client else "unknown",
                },
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Twilio signature")

        logger.debug("Twilio signature validated successfully")
        return True


# Global validator instance
_twilio_validator = TwilioSignatureValidator()


async def validate_twilio_signature(request: Request) -> bool:
    """
    FastAPI dependency for Twilio signature validation.

    Usage:
        @router.post("/incoming")
        async def handle_incoming(
            request: Request,
            _: bool = Depends(validate_twilio_signature)
        ):
            ...
    """
    return await _twilio_validator.validate(request)


def twilio_webhook_validator(func):
    """
    Decorator for Twilio webhook endpoints.

    Usage:
        @router.post("/incoming")
        @twilio_webhook_validator
        async def handle_incoming(request: Request):
            ...
    """

    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        await _twilio_validator.validate(request)
        return await func(request, *args, **kwargs)

    return wrapper
