"""Read-only audit log endpoint."""
import datetime
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import AuditLog, User

router = APIRouter(prefix="/api/audit", tags=["audit"])
logger = structlog.get_logger("accesswave.audit")

_MAX_LIMIT = 200


class AuditLogOut(BaseModel):
    id: int
    action: str
    resource_type: Optional[str]
    resource_id: Optional[int]
    ip_address: Optional[str]
    user_agent: Optional[str]
    extra: Optional[dict]
    created_at: datetime.datetime

    class Config:
        from_attributes = True


@router.get(
    "",
    response_model=list[AuditLogOut],
    summary="List your audit log",
    description=(
        "Returns your most-recent audit events in reverse-chronological order. "
        "Use `limit` (max 200) and `offset` for pagination."
    ),
)
async def list_audit_logs(
    limit: int = Query(50, ge=1, le=_MAX_LIMIT),
    offset: int = Query(0, ge=0),
    action: Optional[str] = Query(None, description="Filter by action prefix, e.g. 'login'"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(AuditLog)
        .where(AuditLog.user_id == user.id)
        .order_by(AuditLog.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    if action:
        stmt = stmt.where(AuditLog.action.startswith(action))
    result = await db.execute(stmt)
    return result.scalars().all()
