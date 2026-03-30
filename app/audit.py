"""Helpers for writing audit log entries."""
from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


def _client_ip(request: Request) -> str | None:
    """Return the best-effort client IP, honouring X-Forwarded-For."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:45]
    if request.client:
        return request.client.host[:45]
    return None


def _user_agent(request: Request) -> str | None:
    ua = request.headers.get("user-agent", "")
    return ua[:256] if ua else None


async def log_action(
    db: AsyncSession,
    *,
    action: str,
    user_id: int | None = None,
    request: Request | None = None,
    resource_type: str | None = None,
    resource_id: int | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Append a single audit log row and flush (no commit — caller commits)."""
    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=_client_ip(request) if request else None,
        user_agent=_user_agent(request) if request else None,
        extra=extra,
    )
    db.add(entry)
    await db.flush()
