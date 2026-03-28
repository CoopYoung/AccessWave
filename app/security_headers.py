"""
Security-headers middleware and CORS configuration for AccessWave.

Adds the following to every HTTP response:
  - Content-Security-Policy
  - X-Content-Type-Options
  - X-Frame-Options
  - Referrer-Policy
  - Permissions-Policy
  - Cross-Origin-Opener-Policy
  - Cross-Origin-Resource-Policy
  - Strict-Transport-Security (opt-in via HSTS_ENABLED env var)

None of these require third-party packages beyond what FastAPI/Starlette
already install.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Inject security headers into every response."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

        # Build Content-Security-Policy once at startup.
        #
        # 'unsafe-inline' is required because the Jinja2 templates use:
        #   - inline style="…" attributes  →  style-src
        #   - inline <script>initX();</script> blocks  →  script-src
        #
        # If CSP_REPORT_URI is set, a report-uri directive is appended so
        # violation reports are collected without blocking (add report-only
        # mode later via a separate header if needed).
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline'",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data:",
            "font-src 'self'",
            "connect-src 'self'",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
            "upgrade-insecure-requests",
        ]
        if settings.CSP_REPORT_URI:
            csp_directives.append(f"report-uri {settings.CSP_REPORT_URI}")

        self._csp = "; ".join(csp_directives)

        self._hsts = (
            "max-age=63072000; includeSubDomains; preload"
            if settings.HSTS_ENABLED
            else None
        )

    async def dispatch(self, request: Request, call_next) -> Response:
        response: Response = await call_next(request)

        response.headers["Content-Security-Policy"] = self._csp
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), payment=()"
        )
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"

        if self._hsts:
            response.headers["Strict-Transport-Security"] = self._hsts

        return response
