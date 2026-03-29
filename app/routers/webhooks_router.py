"""CRUD endpoints for user-defined webhook subscriptions."""

import datetime
import os
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import Site, User, Webhook
from app.services.webhook_service import fire_test_webhook

logger = structlog.get_logger("accesswave.webhooks")

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

MAX_WEBHOOKS_PER_USER = 20


def _generate_secret() -> str:
    """Return a 32-byte random hex string for use as the default HMAC secret."""
    return os.urandom(32).hex()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class WebhookCreate(BaseModel):
    url: HttpUrl
    site_id: Optional[int] = Field(None, description="Scope to one site; omit for all sites")
    secret: Optional[str] = Field(
        None,
        min_length=8,
        max_length=255,
        description="HMAC secret for signature verification; auto-generated if omitted",
    )


class WebhookUpdate(BaseModel):
    url: Optional[HttpUrl] = None
    site_id: Optional[int] = Field(None)
    secret: Optional[str] = Field(None, min_length=8, max_length=255)
    is_active: Optional[bool] = None


class WebhookOut(BaseModel):
    id: int
    url: str
    site_id: Optional[int]
    secret: str
    is_active: bool
    created_at: datetime.datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_webhook_or_404(webhook_id: int, user: User, db: AsyncSession) -> Webhook:
    result = await db.execute(
        select(Webhook).where(Webhook.id == webhook_id, Webhook.user_id == user.id)
    )
    webhook = result.scalar_one_or_none()
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return webhook


async def _assert_site_owned(site_id: Optional[int], user: User, db: AsyncSession) -> None:
    """Raise 404 if site_id is provided but doesn't belong to the user."""
    if site_id is None:
        return
    result = await db.execute(
        select(Site).where(Site.id == site_id, Site.user_id == user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Site not found")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=list[WebhookOut])
async def list_webhooks(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Webhook)
        .where(Webhook.user_id == user.id)
        .order_by(Webhook.created_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=WebhookOut, status_code=201)
async def create_webhook(
    body: WebhookCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    count_result = await db.execute(
        select(Webhook).where(Webhook.user_id == user.id)
    )
    if len(count_result.scalars().all()) >= MAX_WEBHOOKS_PER_USER:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum of {MAX_WEBHOOKS_PER_USER} webhooks allowed per account.",
        )

    await _assert_site_owned(body.site_id, user, db)

    webhook = Webhook(
        user_id=user.id,
        site_id=body.site_id,
        url=str(body.url),
        secret=body.secret or _generate_secret(),
        is_active=True,
    )
    db.add(webhook)
    await db.commit()
    await db.refresh(webhook)
    logger.info("webhook_created", webhook_id=webhook.id, user_id=user.id, url=webhook.url)
    return webhook


@router.patch("/{webhook_id}", response_model=WebhookOut)
async def update_webhook(
    webhook_id: int,
    body: WebhookUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    webhook = await _get_webhook_or_404(webhook_id, user, db)

    if body.url is not None:
        webhook.url = str(body.url)
    if body.secret is not None:
        webhook.secret = body.secret
    if body.is_active is not None:
        webhook.is_active = body.is_active
    if "site_id" in body.model_fields_set:
        await _assert_site_owned(body.site_id, user, db)
        webhook.site_id = body.site_id

    await db.commit()
    await db.refresh(webhook)
    logger.info("webhook_updated", webhook_id=webhook.id, user_id=user.id)
    return webhook


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(
    webhook_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    webhook = await _get_webhook_or_404(webhook_id, user, db)
    await db.delete(webhook)
    await db.commit()
    logger.info("webhook_deleted", webhook_id=webhook_id, user_id=user.id)


@router.post("/{webhook_id}/test", status_code=200)
async def test_webhook(
    webhook_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a synthetic 'ping' payload to verify the endpoint is reachable."""
    webhook = await _get_webhook_or_404(webhook_id, user, db)
    success = await fire_test_webhook(webhook)
    if not success:
        raise HTTPException(
            status_code=502,
            detail="Test delivery failed. Check that the URL is reachable and returns a 2xx status.",
        )
    return {"status": "delivered"}
