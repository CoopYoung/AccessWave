"""Request ID middleware for AccessWave.

Each inbound request is assigned a unique correlation ID that is:

* Bound to structlog's context-variable store so every log line emitted
  during the request includes ``request_id=<uuid>``.
* Returned as the ``X-Request-ID`` response header so clients and load
  balancers can correlate their logs with ours.

If the client (or an upstream proxy / load balancer) sends an
``X-Request-ID`` request header, that value is reused verbatim.  This
lets the entire call chain share one ID.  A fresh UUID4 is generated when
no header is present.
"""

import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assign a unique correlation ID to every HTTP request."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Honour a client-supplied ID (e.g. from a load balancer or SDK);
        # fall back to a fresh UUID4.
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # Reset structlog's per-task context so we never leak bindings from a
        # previous request that ran on the same asyncio task.
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response: Response = await call_next(request)

        # Echo the ID back so the caller can correlate its own logs.
        response.headers["X-Request-ID"] = request_id

        return response
