"""Email notification preferences — get and update per-user settings."""

from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models import User
from app.services.email_service import send_scan_completed

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

logger = structlog.get_logger("accesswave.notifications")


class NotificationPrefs(BaseModel):
    email_notify_on_complete: bool
    email_notify_on_failure: bool
    email_score_threshold: Optional[float] = None
    email_enabled: bool  # server-level SMTP configured?


class NotificationPrefsUpdate(BaseModel):
    email_notify_on_complete: Optional[bool] = None
    email_notify_on_failure: Optional[bool] = None
    # Pass null to disable threshold, or a number 0–100 to enable it
    email_score_threshold: Optional[float] = Field(None, ge=0, le=100)
    clear_threshold: bool = False  # explicit flag to set threshold to null


@router.get("", response_model=NotificationPrefs)
async def get_prefs(user: User = Depends(get_current_user)):
    """Return the current user's email notification preferences."""
    return NotificationPrefs(
        email_notify_on_complete=user.email_notify_on_complete,
        email_notify_on_failure=user.email_notify_on_failure,
        email_score_threshold=user.email_score_threshold,
        email_enabled=settings.email_enabled,
    )


@router.patch("", response_model=NotificationPrefs)
async def update_prefs(
    body: NotificationPrefsUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update email notification preferences."""
    if body.email_notify_on_complete is not None:
        user.email_notify_on_complete = body.email_notify_on_complete
    if body.email_notify_on_failure is not None:
        user.email_notify_on_failure = body.email_notify_on_failure
    if body.clear_threshold:
        user.email_score_threshold = None
    elif body.email_score_threshold is not None:
        user.email_score_threshold = body.email_score_threshold

    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info(
        "notification_prefs_updated",
        user_id=user.id,
        on_complete=user.email_notify_on_complete,
        on_failure=user.email_notify_on_failure,
        threshold=user.email_score_threshold,
    )
    return NotificationPrefs(
        email_notify_on_complete=user.email_notify_on_complete,
        email_notify_on_failure=user.email_notify_on_failure,
        email_score_threshold=user.email_score_threshold,
        email_enabled=settings.email_enabled,
    )


@router.post("/test", status_code=200)
async def send_test_email(user: User = Depends(get_current_user)):
    """Send a test notification to the current user's email address."""
    if not settings.email_enabled:
        raise HTTPException(
            status_code=503,
            detail="Email delivery is not configured on this server. Set SMTP_HOST in the environment.",
        )
    sent = await send_scan_completed(
        to_address=user.email,
        site_name="Example Site",
        site_url="https://example.com",
        scan_id=0,
        score=85.0,
        pages_scanned=12,
        total_issues=4,
        critical_count=0,
        serious_count=1,
        score_threshold=None,
    )
    if not sent:
        raise HTTPException(status_code=502, detail="Failed to deliver test email. Check SMTP configuration.")
    return {"ok": True, "to": user.email}
