"""Admin dashboard API endpoints.

All routes require the authenticated user to have ``is_admin = True``.
The ``get_admin_user`` dependency (from ``app.auth``) enforces this and
returns 403 Forbidden for non-admins.

Routes
------
GET  /api/admin/stats          — system-wide counts and recent activity
GET  /api/admin/users          — paginated + searchable user list
POST /api/admin/users/{id}/ban   — ban a user (prevents login/API access)
POST /api/admin/users/{id}/unban — lift a ban
POST /api/admin/users/{id}/toggle-admin — promote or demote admin status
"""
import datetime
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_admin_user
from app.database import get_db
from app.models import Scan, Site, User

router = APIRouter(prefix="/api/admin", tags=["admin"])
logger = structlog.get_logger("accesswave.admin")


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class UserSummary(BaseModel):
    id: int
    email: str
    plan: str
    is_admin: bool
    is_banned: bool
    email_verified: bool
    created_at: datetime.datetime
    site_count: int
    scan_count: int

    class Config:
        from_attributes = True


class SystemStats(BaseModel):
    total_users: int
    total_sites: int
    total_scans: int
    scans_today: int
    recent_users: list[UserSummary]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _user_summary(user: User, db: AsyncSession) -> UserSummary:
    site_count_r = await db.execute(
        select(func.count()).where(Site.user_id == user.id)
    )
    scan_count_r = await db.execute(
        select(func.count())
        .select_from(Scan)
        .join(Site, Scan.site_id == Site.id)
        .where(Site.user_id == user.id)
    )
    return UserSummary(
        id=user.id,
        email=user.email,
        plan=user.plan,
        is_admin=bool(getattr(user, "is_admin", False)),
        is_banned=bool(getattr(user, "is_banned", False)),
        email_verified=bool(user.email_verified),
        created_at=user.created_at,
        site_count=site_count_r.scalar_one(),
        scan_count=scan_count_r.scalar_one(),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/stats",
    response_model=SystemStats,
    summary="System-wide statistics",
    description="Returns aggregate counts and the 10 most-recently registered users. Admin only.",
)
async def admin_stats(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    total_users = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    total_sites = (await db.execute(select(func.count()).select_from(Site))).scalar_one()
    total_scans = (await db.execute(select(func.count()).select_from(Scan))).scalar_one()

    today_start = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    scans_today = (
        await db.execute(
            select(func.count()).select_from(Scan).where(Scan.created_at >= today_start)
        )
    ).scalar_one()

    recent_result = await db.execute(
        select(User).order_by(User.created_at.desc()).limit(10)
    )
    recent_users_raw = recent_result.scalars().all()
    recent_users = [await _user_summary(u, db) for u in recent_users_raw]

    logger.info("admin.stats_viewed", admin_id=admin.id)
    return SystemStats(
        total_users=total_users,
        total_sites=total_sites,
        total_scans=total_scans,
        scans_today=scans_today,
        recent_users=recent_users,
    )


@router.get(
    "/users",
    response_model=list[UserSummary],
    summary="List all users",
    description=(
        "Paginated list of all users. Use `search` to filter by email prefix. "
        "Use `banned_only` or `admin_only` to narrow results. Admin only."
    ),
)
async def admin_list_users(
    search: Optional[str] = Query(None, description="Filter by email (case-insensitive prefix)"),
    banned_only: bool = Query(False),
    admin_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(User).order_by(User.created_at.desc()).offset(offset).limit(limit)
    if search:
        stmt = stmt.where(User.email.ilike(f"%{search}%"))
    if banned_only:
        stmt = stmt.where(User.is_banned == True)  # noqa: E712
    if admin_only:
        stmt = stmt.where(User.is_admin == True)  # noqa: E712
    result = await db.execute(stmt)
    users = result.scalars().all()
    return [await _user_summary(u, db) for u in users]


@router.post(
    "/users/{user_id}/ban",
    summary="Ban a user",
    description="Prevents the user from authenticating. Increments token_version to invalidate existing JWTs. Admin only.",
)
async def ban_user(
    user_id: int,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    if user_id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot ban yourself")
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    target.is_banned = True
    # Revoke all existing tokens immediately
    target.token_version = (target.token_version or 0) + 1
    await db.commit()
    logger.info("admin.user_banned", admin_id=admin.id, target_user_id=user_id)
    return {"ok": True, "message": f"User {target.email} has been banned"}


@router.post(
    "/users/{user_id}/unban",
    summary="Unban a user",
    description="Lifts a ban, allowing the user to authenticate again. Admin only.",
)
async def unban_user(
    user_id: int,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    target.is_banned = False
    await db.commit()
    logger.info("admin.user_unbanned", admin_id=admin.id, target_user_id=user_id)
    return {"ok": True, "message": f"User {target.email} has been unbanned"}


@router.post(
    "/users/{user_id}/toggle-admin",
    summary="Toggle admin status",
    description="Promote a regular user to admin, or demote an admin back to regular user. Admin only.",
)
async def toggle_admin(
    user_id: int,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    if user_id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot change your own admin status")
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    target.is_admin = not bool(getattr(target, "is_admin", False))
    await db.commit()
    action = "promoted" if target.is_admin else "demoted"
    logger.info("admin.user_toggle_admin", admin_id=admin.id, target_user_id=user_id, is_admin=target.is_admin)
    return {"ok": True, "message": f"User {target.email} has been {action}"}
