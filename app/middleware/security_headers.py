"""Security headers middleware for PCI-DSS and OWASP compliance.

Adds the following headers to all responses:
- Content-Security-Policy: Restricts resource loading to trusted origins
- Strict-Transport-Security: Forces HTTPS for 1 year with preload
- X-Frame-Options: Prevents clickjacking
- X-Content-Type-Options: Prevents MIME sniffing
- Referrer-Policy: Controls referrer information leakage
- Permissions-Policy: Restricts browser feature access
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all HTTP responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Prevent clickjacking — no iframe embedding allowed
        response.headers["X-Frame-Options"] = "DENY"

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Force HTTPS for 1 year (Railway handles TLS termination)
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains; preload"
        )

        # Control referrer leakage — send origin only on cross-origin requests
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Restrict browser features — disable camera, mic, geolocation, payment
        # for the API itself (frontend controls its own Permissions-Policy)
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )

        # Content-Security-Policy for API responses
        # Restrictive since this is an API server, not serving HTML pages.
        # default-src 'none' blocks everything except what's explicitly allowed.
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; "
            "frame-ancestors 'none'; "
            "base-uri 'none'; "
            "form-action 'none'"
        )

        return response
