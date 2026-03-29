"""Webhook delivery: sign payloads with HMAC-SHA256 and POST to user-configured URLs."""

import asyncio
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone

import httpx
import structlog

from app.database import async_session
from app.models import Scan, Site, Webhook
from sqlalchemy import select

logger = structlog.get_logger("accesswave.webhooks")

# Maximum number of delivery attempts before giving up.
MAX_ATTEMPTS = 3
# Base backoff in seconds; doubles on each retry (1s, 2s, 4s).
BACKOFF_BASE = 1
# Timeout for each outbound HTTP request.
REQUEST_TIMEOUT = 10.0


def _sign_payload(secret: str, body: bytes) -> str:
    """Return 'sha256=<hex>' HMAC-SHA256 signature over *body* using *secret*."""
    mac = hmac.new(secret.encode(), body, hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


async def _deliver(webhook: Webhook, payload: dict) -> bool:
    """
    POST *payload* to webhook.url with HMAC signature headers.
    Retries up to MAX_ATTEMPTS times with exponential backoff.
    Returns True if any attempt succeeds (2xx response).
    """
    body = json.dumps(payload, default=str).encode()
    signature = _sign_payload(webhook.secret, body)
    delivery_id = str(uuid.uuid4())

    headers = {
        "Content-Type": "application/json",
        "X-AccessWave-Event": payload.get("event", "scan.completed"),
        "X-AccessWave-Delivery": delivery_id,
        "X-AccessWave-Signature": signature,
        "User-Agent": "AccessWave-Webhook/1.0",
    }

    log = logger.bind(webhook_id=webhook.id, url=webhook.url, delivery_id=delivery_id)

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=False) as client:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                resp = await client.post(webhook.url, content=body, headers=headers)
                if resp.is_success:
                    log.info("webhook_delivered", attempt=attempt, status=resp.status_code)
                    return True
                log.warning(
                    "webhook_non_2xx",
                    attempt=attempt,
                    status=resp.status_code,
                )
            except httpx.RequestError as exc:
                log.warning("webhook_request_error", attempt=attempt, error=str(exc))

            if attempt < MAX_ATTEMPTS:
                await asyncio.sleep(BACKOFF_BASE * (2 ** (attempt - 1)))

    log.error("webhook_all_attempts_failed", max_attempts=MAX_ATTEMPTS)
    return False


async def fire_scan_webhooks(scan_id: int) -> None:
    """
    Look up all active webhooks for the scan's owner and deliver the payload.
    Called by scan_runner after a scan reaches 'completed' or 'failed'.
    """
    async with async_session() as db:
        result = await db.execute(select(Scan).where(Scan.id == scan_id))
        scan = result.scalar_one_or_none()
        if not scan:
            return

        site_result = await db.execute(select(Site).where(Site.id == scan.site_id))
        site = site_result.scalar_one_or_none()
        if not site:
            return

        # Fetch all active webhooks for this user that either target this site
        # specifically or have no site filter (applies to all sites).
        wh_result = await db.execute(
            select(Webhook).where(
                Webhook.user_id == site.user_id,
                Webhook.is_active.is_(True),
                (Webhook.site_id == site.id) | (Webhook.site_id.is_(None)),
            )
        )
        webhooks = wh_result.scalars().all()

    if not webhooks:
        return

    completed_at = scan.completed_at or datetime.now(timezone.utc)
    event = "scan.completed" if scan.status == "completed" else "scan.failed"

    payload = {
        "event": event,
        "scan_id": scan.id,
        "site_id": site.id,
        "site_name": site.name,
        "site_url": site.url,
        "status": scan.status,
        "score": scan.score,
        "pages_scanned": scan.pages_scanned,
        "total_issues": scan.total_issues,
        "critical_count": scan.critical_count,
        "serious_count": scan.serious_count,
        "moderate_count": scan.moderate_count,
        "minor_count": scan.minor_count,
        "started_at": scan.started_at.isoformat() if scan.started_at else None,
        "completed_at": completed_at.isoformat() if hasattr(completed_at, "isoformat") else str(completed_at),
    }

    # Fire all webhooks concurrently.
    await asyncio.gather(*[_deliver(wh, payload) for wh in webhooks], return_exceptions=True)


async def fire_test_webhook(webhook: Webhook) -> bool:
    """Send a synthetic test payload to verify connectivity."""
    payload = {
        "event": "ping",
        "webhook_id": webhook.id,
        "message": "This is a test delivery from AccessWave.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return await _deliver(webhook, payload)
