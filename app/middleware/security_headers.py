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

    # Paths that serve HTML content rendered inside the CRM's iframe previews.
    # These get frame-ancestors set to the CRM origin instead of 'none'.
    IFRAME_ALLOWED_PATHS = ("/api/v2/documents/", "/api/v2/reference-docs/")
    IFRAME_ALLOWED_ORIGIN = "https://react.ecbtx.com"

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        path = request.url.path
        is_iframe_preview = (
            path.endswith("/html")
            and any(path.startswith(p) for p in self.IFRAME_ALLOWED_PATHS)
        )

        if is_iframe_preview:
            response.headers["X-Frame-Options"] = f"ALLOW-FROM {self.IFRAME_ALLOWED_ORIGIN}"
        else:
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
        if is_iframe_preview:
            # HTML preview endpoints need relaxed CSP so the CRM can iframe them
            # and the HTML content can use inline styles/scripts it ships with.
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                f"frame-ancestors {self.IFRAME_ALLOWED_ORIGIN}; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: https:; "
                "font-src 'self' https://fonts.gstatic.com"
            )
        else:
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; "
                "frame-ancestors 'none'; "
                "base-uri 'none'; "
                "form-action 'none'"
            )

        return response
