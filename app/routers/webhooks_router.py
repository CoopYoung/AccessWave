"""CRUD endpoints for webhook management + test-delivery."""

import datetime
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import User, Webhook
from app.services.webhook_sender import deliver

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

MAX_WEBHOOKS_PER_USER = 20

VALID_EVENTS = {"scan.completed", "scan.failed"}


class WebhookCreate(BaseModel):
    url: HttpUrl
    events: list[str] = Field(..., min_length=1)

    def validate_events(self) -> list[str]:
        invalid = [e for e in self.events if e not in VALID_EVENTS]
        if invalid:
            raise ValueError(f"Unknown events: {invalid}. Valid: {sorted(VALID_EVENTS)}")
        return list(set(self.events))


class WebhookOut(BaseModel):
    id: int
    url: str
    events: list[str]
    is_active: bool
    created_at: datetime.datetime
    # secret is shown only on creation via WebhookCreated

    class Config:
        from_attributes = True


class WebhookCreated(WebhookOut):
    """Returned only on creation — includes the plaintext signing secret."""
    secret: str


class WebhookUpdate(BaseModel):
    is_active: Optional[bool] = None
    events: Optional[list[str]] = None


def _generate_secret() -> str:
    return "whsec_" + os.urandom(24).hex()


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


@router.post("", response_model=WebhookCreated, status_code=201)
async def create_webhook(
    body: WebhookCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    count = (
        await db.execute(select(Webhook).where(Webhook.user_id == user.id))
    ).scalars().all()
    if len(count) >= MAX_WEBHOOKS_PER_USER:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum of {MAX_WEBHOOKS_PER_USER} webhooks allowed per account.",
        )

    try:
        events = body.validate_events()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    secret = _generate_secret()
    webhook = Webhook(
        user_id=user.id,
        url=str(body.url),
        secret=secret,
        events=events,
        is_active=True,
    )
    db.add(webhook)
    await db.commit()
    await db.refresh(webhook)

    return WebhookCreated(
        id=webhook.id,
        url=webhook.url,
        events=webhook.events,
        is_active=webhook.is_active,
        created_at=webhook.created_at,
        secret=secret,
    )


@router.patch("/{webhook_id}", response_model=WebhookOut)
async def update_webhook(
    webhook_id: int,
    body: WebhookUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Webhook).where(Webhook.id == webhook_id, Webhook.user_id == user.id)
    )
    webhook = result.scalar_one_or_none()
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    if body.is_active is not None:
        webhook.is_active = body.is_active
    if body.events is not None:
        try:
            events_model = WebhookCreate(url=webhook.url, events=body.events)
            webhook.events = events_model.validate_events()
        except (ValueError, Exception) as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    await db.commit()
    await db.refresh(webhook)
    return webhook


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(
    webhook_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Webhook).where(Webhook.id == webhook_id, Webhook.user_id == user.id)
    )
    webhook = result.scalar_one_or_none()
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    await db.delete(webhook)
    await db.commit()


@router.post("/{webhook_id}/test", status_code=200)
async def test_webhook(
    webhook_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Webhook).where(Webhook.id == webhook_id, Webhook.user_id == user.id)
    )
    webhook = result.scalar_one_or_none()
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    success = await deliver(
        url=webhook.url,
        secret=webhook.secret,
        event="webhook.test",
        data={
            "message": "This is a test delivery from AccessWave.",
            "webhook_id": webhook.id,
        },
    )
    if not success:
        raise HTTPException(
            status_code=502,
            detail="Test delivery failed. Check that your endpoint is reachable and returns a 2xx status.",
        )
    return {"ok": True}
