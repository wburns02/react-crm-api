"""
RFC 7807 Problem Details exception handling.

Provides standardized error responses for the API following the
"Problem Details for HTTP APIs" specification.

See: https://datatracker.ietf.org/doc/html/rfc7807
"""

from typing import Optional, Dict, Any, List
from enum import Enum
from pydantic import BaseModel, Field
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import logging
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)


def _get_trace_id() -> str:
    """Get trace ID from correlation context or generate a new one."""
    try:
        from app.middleware.correlation import get_request_id
        request_id = get_request_id()
        if request_id and request_id != "unknown":
            return request_id
    except ImportError:
        pass
    return str(uuid.uuid4())[:12]


class ErrorCode(str, Enum):
    """Standardized error codes for the CRM API."""

    # Authentication & Authorization
    UNAUTHORIZED = "AUTH_001"
    FORBIDDEN = "AUTH_002"
    SESSION_EXPIRED = "AUTH_003"
    CSRF_INVALID = "AUTH_004"

    # Validation
    VALIDATION_ERROR = "VAL_001"
    INVALID_FORMAT = "VAL_002"
    MISSING_FIELD = "VAL_003"
    CONSTRAINT_VIOLATION = "VAL_004"

    # Resource
    NOT_FOUND = "RES_001"
    ALREADY_EXISTS = "RES_002"
    CONFLICT = "RES_003"
    GONE = "RES_004"

    # Business Logic
    BUSINESS_RULE_VIOLATION = "BIZ_001"
    QUOTA_EXCEEDED = "BIZ_002"
    OPERATION_NOT_ALLOWED = "BIZ_003"

    # External Services
    EXTERNAL_SERVICE_ERROR = "EXT_001"
    RINGCENTRAL_ERROR = "EXT_002"
    AI_SERVICE_ERROR = "EXT_003"
    DATABASE_ERROR = "EXT_004"
    TWILIO_ERROR = "EXT_005"
    STRIPE_ERROR = "EXT_006"

    # Server
    INTERNAL_ERROR = "SRV_001"
    SERVICE_UNAVAILABLE = "SRV_002"
    TIMEOUT = "SRV_003"


class ProblemDetail(BaseModel):
    """
    RFC 7807 Problem Details response schema.

    Attributes:
        type: URI reference identifying the problem type
        title: Short, human-readable summary
        status: HTTP status code
        detail: Human-readable explanation specific to this occurrence
        instance: URI reference identifying this specific occurrence
        code: Machine-readable error code for client handling
        timestamp: ISO 8601 timestamp of when the error occurred
        trace_id: Unique identifier for tracing in logs/Sentry
        errors: List of field-level validation errors (for 422)
        help_url: Optional link to documentation
        retry_after: Seconds to wait before retrying (for rate limits)
    """

    type: str = Field(
        default="about:blank",
        description="URI reference identifying the problem type"
    )
    title: str = Field(
        description="Short, human-readable summary of the problem"
    )
    status: int = Field(
        description="HTTP status code"
    )
    detail: str = Field(
        description="Human-readable explanation specific to this occurrence"
    )
    instance: Optional[str] = Field(
        default=None,
        description="URI reference for this specific occurrence"
    )
    code: str = Field(
        description="Machine-readable error code"
    )
    timestamp: str = Field(
        description="ISO 8601 timestamp"
    )
    trace_id: str = Field(
        description="Unique trace ID for debugging"
    )
    errors: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Field-level validation errors"
    )
    help_url: Optional[str] = Field(
        default=None,
        description="Link to relevant documentation"
    )
    retry_after: Optional[int] = Field(
        default=None,
        description="Seconds to wait before retrying"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "type": "https://api.ecbtx.com/problems/not-found",
                "title": "Resource Not Found",
                "status": 404,
                "detail": "Customer with ID 123 was not found",
                "instance": "/api/v2/customers/123",
                "code": "RES_001",
                "timestamp": "2026-01-29T10:30:00Z",
                "trace_id": "abc123def456"
            }
        }
    }


class CRMException(HTTPException):
    """
    Base exception for CRM API with RFC 7807 support.

    Usage:
        raise CRMException(
            status_code=404,
            code=ErrorCode.NOT_FOUND,
            detail="Customer not found",
            instance="/api/v2/customers/123"
        )
    """

    def __init__(
        self,
        status_code: int,
        code: ErrorCode,
        detail: str,
        title: Optional[str] = None,
        instance: Optional[str] = None,
        errors: Optional[List[Dict[str, Any]]] = None,
        help_url: Optional[str] = None,
        retry_after: Optional[int] = None,
        headers: Optional[Dict[str, str]] = None,
    ):
        self.code = code
        self.title = title or self._default_title(status_code)
        self.instance = instance
        self.errors = errors
        self.help_url = help_url
        self.retry_after = retry_after
        self.trace_id = _get_trace_id()
        self.timestamp = datetime.utcnow().isoformat() + "Z"

        super().__init__(status_code=status_code, detail=detail, headers=headers)

    @staticmethod
    def _default_title(status_code: int) -> str:
        """Get default title based on status code."""
        titles = {
            400: "Bad Request",
            401: "Unauthorized",
            403: "Forbidden",
            404: "Not Found",
            409: "Conflict",
            422: "Validation Error",
            429: "Too Many Requests",
            500: "Internal Server Error",
            502: "Bad Gateway",
            503: "Service Unavailable",
            504: "Gateway Timeout",
        }
        return titles.get(status_code, "Error")

    def to_problem_detail(self) -> ProblemDetail:
        """Convert to RFC 7807 ProblemDetail."""
        return ProblemDetail(
            type=f"https://api.ecbtx.com/problems/{self.code.value.lower().replace('_', '-')}",
            title=self.title,
            status=self.status_code,
            detail=self.detail,
            instance=self.instance,
            code=self.code.value,
            timestamp=self.timestamp,
            trace_id=self.trace_id,
            errors=self.errors,
            help_url=self.help_url,
            retry_after=self.retry_after,
        )


# Convenience exception classes

class NotFoundError(CRMException):
    """Resource not found (404)."""

    def __init__(
        self,
        resource: str,
        resource_id: str,
        instance: Optional[str] = None
    ):
        super().__init__(
            status_code=404,
            code=ErrorCode.NOT_FOUND,
            detail=f"{resource} with ID {resource_id} was not found",
            instance=instance,
        )


class ValidationError(CRMException):
    """Validation error (422)."""

    def __init__(
        self,
        detail: str,
        errors: Optional[List[Dict[str, Any]]] = None
    ):
        super().__init__(
            status_code=422,
            code=ErrorCode.VALIDATION_ERROR,
            detail=detail,
            errors=errors,
        )


class UnauthorizedError(CRMException):
    """Authentication required (401)."""

    def __init__(self, detail: str = "Authentication required"):
        super().__init__(
            status_code=401,
            code=ErrorCode.UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


class ForbiddenError(CRMException):
    """Permission denied (403)."""

    def __init__(self, detail: str = "Permission denied"):
        super().__init__(
            status_code=403,
            code=ErrorCode.FORBIDDEN,
            detail=detail,
        )


class ConflictError(CRMException):
    """Resource conflict (409)."""

    def __init__(self, detail: str):
        super().__init__(
            status_code=409,
            code=ErrorCode.CONFLICT,
            detail=detail,
        )


class RateLimitError(CRMException):
    """Rate limit exceeded (429)."""

    def __init__(self, retry_after: int = 60):
        super().__init__(
            status_code=429,
            code=ErrorCode.QUOTA_EXCEEDED,
            detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
            retry_after=retry_after,
            headers={"Retry-After": str(retry_after)},
        )


class ExternalServiceError(CRMException):
    """External service error (502)."""

    def __init__(self, service: str, detail: str):
        super().__init__(
            status_code=502,
            code=ErrorCode.EXTERNAL_SERVICE_ERROR,
            detail=f"{service} service error: {detail}",
        )


class BusinessRuleError(CRMException):
    """Business rule violation (400)."""

    def __init__(self, detail: str):
        super().__init__(
            status_code=400,
            code=ErrorCode.BUSINESS_RULE_VIOLATION,
            detail=detail,
        )


# Exception handlers for FastAPI

def create_problem_response(
    status_code: int,
    code: ErrorCode,
    detail: str,
    request: Request,
    errors: Optional[List[Dict[str, Any]]] = None,
    trace_id: Optional[str] = None,
    allowed_origins: Optional[List[str]] = None,
) -> JSONResponse:
    """Create a RFC 7807 compliant JSON response with CORS headers."""
    problem = ProblemDetail(
        type=f"https://api.ecbtx.com/problems/{code.value.lower().replace('_', '-')}",
        title=CRMException._default_title(status_code),
        status=status_code,
        detail=detail,
        instance=str(request.url.path),
        code=code.value,
        timestamp=datetime.utcnow().isoformat() + "Z",
        trace_id=trace_id or _get_trace_id(),
        errors=errors,
    )

    response = JSONResponse(
        status_code=status_code,
        content=problem.model_dump(exclude_none=True),
        media_type="application/problem+json",
    )

    # Add CORS headers
    if allowed_origins:
        origin = request.headers.get("origin", "")
        if origin in allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Vary"] = "Origin"

    return response


async def crm_exception_handler(
    request: Request,
    exc: CRMException,
    allowed_origins: Optional[List[str]] = None,
) -> JSONResponse:
    """Handle CRMException with RFC 7807 response."""
    logger.warning(
        f"CRMException: {exc.code.value} - {exc.detail}",
        extra={
            "trace_id": exc.trace_id,
            "status_code": exc.status_code,
            "path": request.url.path,
        }
    )

    response = JSONResponse(
        status_code=exc.status_code,
        content=exc.to_problem_detail().model_dump(exclude_none=True),
        media_type="application/problem+json",
        headers=exc.headers,
    )

    # Add CORS headers
    if allowed_origins:
        origin = request.headers.get("origin", "")
        if origin in allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Vary"] = "Origin"

    return response


def create_exception_handlers(allowed_origins: List[str]):
    """
    Create exception handlers with configured allowed origins for CORS.

    Usage in main.py:
        handlers = create_exception_handlers(allowed_origins)
        app.add_exception_handler(CRMException, handlers["crm"])
        app.add_exception_handler(RequestValidationError, handlers["validation"])
        app.add_exception_handler(Exception, handlers["generic"])
    """

    async def handle_crm_exception(request: Request, exc: CRMException) -> JSONResponse:
        return await crm_exception_handler(request, exc, allowed_origins)

    async def handle_http_exception(
        request: Request,
        exc: StarletteHTTPException
    ) -> JSONResponse:
        """Handle standard HTTPException with RFC 7807 response."""
        # Map status codes to error codes
        code_map = {
            400: ErrorCode.VALIDATION_ERROR,
            401: ErrorCode.UNAUTHORIZED,
            403: ErrorCode.FORBIDDEN,
            404: ErrorCode.NOT_FOUND,
            409: ErrorCode.CONFLICT,
            422: ErrorCode.VALIDATION_ERROR,
            429: ErrorCode.QUOTA_EXCEEDED,
            500: ErrorCode.INTERNAL_ERROR,
            502: ErrorCode.EXTERNAL_SERVICE_ERROR,
            503: ErrorCode.SERVICE_UNAVAILABLE,
        }

        code = code_map.get(exc.status_code, ErrorCode.INTERNAL_ERROR)

        return create_problem_response(
            status_code=exc.status_code,
            code=code,
            detail=str(exc.detail),
            request=request,
            allowed_origins=allowed_origins,
        )

    async def handle_validation_exception(
        request: Request,
        exc: RequestValidationError
    ) -> JSONResponse:
        """Handle Pydantic validation errors with field-level details."""
        errors = []
        for error in exc.errors():
            errors.append({
                "field": ".".join(str(loc) for loc in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            })

        return create_problem_response(
            status_code=422,
            code=ErrorCode.VALIDATION_ERROR,
            detail="Request validation failed",
            request=request,
            errors=errors,
            allowed_origins=allowed_origins,
        )

    async def handle_generic_exception(
        request: Request,
        exc: Exception
    ) -> JSONResponse:
        """Handle unexpected exceptions with RFC 7807 response."""
        import traceback

        trace_id = str(uuid.uuid4())[:12]

        # Log the full traceback for debugging
        logger.error(
            f"Unhandled exception: {exc}",
            extra={"trace_id": trace_id, "path": request.url.path},
        )
        logger.error(traceback.format_exc())

        # Try to report to Sentry if available
        try:
            from app.core.sentry import capture_exception
            capture_exception(
                exc,
                context={
                    "trace_id": trace_id,
                    "path": request.url.path,
                    "method": request.method,
                }
            )
        except ImportError:
            pass  # Sentry not configured yet

        # Don't expose internal details in production
        from app.config import settings
        detail = str(exc) if settings.DEBUG else "An unexpected error occurred"

        return create_problem_response(
            status_code=500,
            code=ErrorCode.INTERNAL_ERROR,
            detail=detail,
            request=request,
            trace_id=trace_id,
            allowed_origins=allowed_origins,
        )

    return {
        "crm": handle_crm_exception,
        "http": handle_http_exception,
        "validation": handle_validation_exception,
        "generic": handle_generic_exception,
    }
