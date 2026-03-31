"""IP blocking middleware and auto-block helper for AccessWave.

Two concerns are handled here:

1. **Middleware** (``IPBlockMiddleware``) — runs on every request and returns
   403 Forbidden if the client IP appears in the ``blocked_ips`` table and the
   block has not yet expired.  The blocklist is cached in-memory and refreshed
   every 60 seconds so the hot path never hits the database.

2. **Auto-block helper** (``record_ip_failure`` / ``maybe_auto_block``) —
   called from the auth router after every failed login attempt.  It counts
   recent failures for the source IP and inserts a timed ``BlockedIP`` row
   once the configured threshold is reached.
"""

import asyncio
import datetime
import threading
from collections import defaultdict

import structlog
from sqlalchemy import delete, select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import BlockedIP

logger = structlog.get_logger("accesswave.ip_blocker")

# ---------------------------------------------------------------------------
# In-memory failure counter  (ip -> list[timestamp])
# ---------------------------------------------------------------------------

_failure_lock = threading.Lock()
_ip_failures: dict[str, list[datetime.datetime]] = defaultdict(list)


def record_ip_failure(ip: str) -> None:
    """Record one failed login attempt for *ip* (non-blocking, thread-safe)."""
    if not settings.IP_AUTO_BLOCK_ENABLED:
        return
    now = datetime.datetime.utcnow()
    window = datetime.timedelta(hours=settings.IP_BLOCK_WINDOW_HOURS)
    with _failure_lock:
        # Prune old entries outside the rolling window
        _ip_failures[ip] = [t for t in _ip_failures[ip] if now - t < window]
        _ip_failures[ip].append(now)


def failure_count(ip: str) -> int:
    """Return the number of recent failures for *ip* within the rolling window."""
    now = datetime.datetime.utcnow()
    window = datetime.timedelta(hours=settings.IP_BLOCK_WINDOW_HOURS)
    with _failure_lock:
        _ip_failures[ip] = [t for t in _ip_failures[ip] if now - t < window]
        return len(_ip_failures[ip])


async def maybe_auto_block(ip: str) -> bool:
    """Block *ip* automatically if it has exceeded the failure threshold.

    Returns ``True`` if a new block was inserted, ``False`` otherwise.
    """
    if not settings.IP_AUTO_BLOCK_ENABLED:
        return False
    if failure_count(ip) < settings.IP_BLOCK_THRESHOLD:
        return False

    now = datetime.datetime.utcnow()
    expires_at = (
        now + datetime.timedelta(hours=settings.IP_BLOCK_DURATION_HOURS)
        if settings.IP_BLOCK_DURATION_HOURS > 0
        else None
    )
    reason = (
        f"Auto-blocked: {settings.IP_BLOCK_THRESHOLD} failed login attempts "
        f"within {settings.IP_BLOCK_WINDOW_HOURS}h"
    )

    async with AsyncSessionLocal() as db:
        # Upsert: if a block for this IP already exists, just refresh it.
        existing = (
            await db.execute(select(BlockedIP).where(BlockedIP.ip_address == ip))
        ).scalar_one_or_none()

        if existing:
            existing.blocked_at = now
            existing.expires_at = expires_at
            existing.reason = reason
        else:
            db.add(BlockedIP(
                ip_address=ip,
                reason=reason,
                blocked_by="auto",
                blocked_at=now,
                expires_at=expires_at,
            ))
        await db.commit()

    # Reset in-memory counter so one block window is not counted into the next
    with _failure_lock:
        _ip_failures.pop(ip, None)

    # Invalidate the cache so the new block takes effect immediately
    _invalidate_cache()
    logger.warning("ip.auto_blocked", ip=ip, expires_at=str(expires_at))
    return True


# ---------------------------------------------------------------------------
# Blocklist cache
# ---------------------------------------------------------------------------

_cache_lock = asyncio.Lock()
_blocklist_cache: set[str] = set()
_cache_loaded_at: datetime.datetime | None = None
_CACHE_TTL = datetime.timedelta(seconds=60)


def _invalidate_cache() -> None:
    global _cache_loaded_at
    _cache_loaded_at = None


async def _refresh_cache_if_stale() -> None:
    global _blocklist_cache, _cache_loaded_at
    now = datetime.datetime.utcnow()
    if _cache_loaded_at is not None and (now - _cache_loaded_at) < _CACHE_TTL:
        return
    async with _cache_lock:
        # Double-checked locking
        if _cache_loaded_at is not None and (now - _cache_loaded_at) < _CACHE_TTL:
            return
        try:
            async with AsyncSessionLocal() as db:
                # Remove expired blocks first
                await db.execute(
                    delete(BlockedIP).where(
                        BlockedIP.expires_at.isnot(None),
                        BlockedIP.expires_at <= now,
                    )
                )
                await db.commit()
                rows = (await db.execute(select(BlockedIP.ip_address))).scalars().all()
                _blocklist_cache = set(rows)
                _cache_loaded_at = now
        except Exception as exc:  # pragma: no cover
            logger.error("ip_blocker.cache_refresh_failed", error=str(exc))


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class IPBlockMiddleware(BaseHTTPMiddleware):
    """Block requests from IPs in the ``blocked_ips`` table."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        # Health and metrics paths are never blocked so liveness probes keep working
        path = request.url.path
        if path in ("/health", "/metrics", "/health/live", "/health/ready"):
            return await call_next(request)

        ip = request.client.host if request.client else "unknown"
        await _refresh_cache_if_stale()

        if ip in _blocklist_cache:
            logger.warning("ip.blocked_request", ip=ip, path=path)
            return JSONResponse(
                status_code=403,
                content={
                    "detail": (
                        "Your IP address has been temporarily blocked due to "
                        "suspicious activity. Please contact support if you "
                        "believe this is an error."
                    )
                },
            )

        return await call_next(request)
