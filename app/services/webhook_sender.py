"""Send HMAC-SHA256-signed webhook payloads to registered endpoints."""

import datetime
import hashlib
import hmac
import json

import httpx
import structlog

logger = structlog.get_logger("accesswave.webhooks")

# Timeout for outbound HTTP requests — keep short to avoid blocking scan completion.
_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


def _sign(secret: str, body: bytes) -> str:
    """Return 'sha256=<hex>' HMAC signature for the given body."""
    digest = hmac.new(secret.encode(), body, digestmod=hashlib.sha256).hexdigest()
    return f"sha256={digest}"


async def deliver(url: str, secret: str, event: str, data: dict) -> bool:
    """POST a signed webhook payload to *url*.  Returns True on 2xx response."""
    payload = {
        "event": event,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "data": data,
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    signature = _sign(secret, body)

    headers = {
        "Content-Type": "application/json",
        "X-AccessWave-Event": event,
        "X-AccessWave-Signature": signature,
        "User-Agent": "AccessWave-Webhook/1.0",
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False) as client:
            resp = await client.post(url, content=body, headers=headers)
        ok = resp.is_success
        logger.info(
            "webhook_delivered",
            url=url,
            event=event,
            status_code=resp.status_code,
            success=ok,
        )
        return ok
    except Exception as exc:
        logger.warning("webhook_failed", url=url, event=event, error=str(exc))
        return False


async def fire_event(webhooks: list, event: str, data: dict) -> None:
    """Fire *event* to all active webhooks subscribed to it."""
    for wh in webhooks:
        if not wh.is_active:
            continue
        subscribed = wh.events or []
        if event not in subscribed and "*" not in subscribed:
            continue
        await deliver(wh.url, wh.secret, event, data)
