"""Global exception handlers and a consistent error response envelope.

Every API error — whether an HTTPException raised explicitly, a Pydantic
validation failure, or an unexpected server crash — is returned in the same
JSON shape:

    {
        "status_code": 422,
        "error": "Validation Error",
        "detail": [{"field": "url", "message": "value is not a valid URL"}]
    }

``detail`` is a plain string for most errors and a list of field-level
objects for validation failures (422).  This contract lets every API client
handle errors with a single code path.
"""

import logging
from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("accesswave.errors")

# Human-readable labels for common HTTP status codes used in this app.
_STATUS_LABELS: dict[int, str] = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    409: "Conflict",
    422: "Validation Error",
    429: "Too Many Requests",
    500: "Internal Server Error",
    503: "Service Unavailable",
}


def _label(status_code: int) -> str:
    return _STATUS_LABELS.get(status_code, "Error")


def _error_response(status_code: int, detail: Any) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "status_code": status_code,
            "error": _label(status_code),
            "detail": detail,
        },
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Convert any HTTPException (including FastAPI's) to the standard envelope."""
    logger.warning(
        "HTTP %s on %s %s — %s",
        exc.status_code,
        request.method,
        request.url.path,
        exc.detail,
    )
    return _error_response(exc.status_code, exc.detail)


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Flatten Pydantic v2 validation errors into a list of {field, message} objects."""
    field_errors = []
    for err in exc.errors():
        # loc is a tuple like ("body", "url") or ("query", "limit")
        loc = err.get("loc", ())
        # Skip the top-level source segment ("body" / "query" / "path") for brevity.
        field_parts = [str(p) for p in loc[1:]] if len(loc) > 1 else [str(p) for p in loc]
        field_errors.append({
            "field": ".".join(field_parts) if field_parts else "unknown",
            "message": err.get("msg", "Invalid value"),
        })

    logger.warning(
        "Validation error on %s %s — %d field(s)",
        request.method,
        request.url.path,
        len(field_errors),
    )
    return _error_response(status.HTTP_422_UNPROCESSABLE_ENTITY, field_errors)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for any exception not handled upstream.

    Logs the full traceback but returns a sanitised message to the client so
    that internal details are never leaked in production.
    """
    logger.exception(
        "Unhandled exception on %s %s",
        request.method,
        request.url.path,
    )
    return _error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "An unexpected error occurred. Please try again later.",
    )
