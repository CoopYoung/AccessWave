import datetime
import hashlib
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import ApiKey, User

router = APIRouter(prefix="/api/keys", tags=["api-keys"])

MAX_KEYS_PER_USER = 10


class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    expires_in_days: Optional[int] = Field(None, ge=1, le=365)


class ApiKeyOut(BaseModel):
    id: int
    name: str
    key_prefix: str
    expires_at: Optional[datetime.datetime]
    last_used_at: Optional[datetime.datetime]
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class ApiKeyCreated(ApiKeyOut):
    """Returned only on creation; includes the plaintext key (shown once)."""
    key: str


def _generate_key() -> tuple[str, str, str]:
    """Return (raw_key, prefix, sha256_hex)."""
    raw = "aw_" + os.urandom(20).hex()   # e.g. aw_ + 40 hex chars = 43 chars
    prefix = raw[:11]                      # "aw_" + first 8 hex chars
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return raw, prefix, digest


@router.get("", response_model=list[ApiKeyOut])
async def list_api_keys(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ApiKey)
        .where(ApiKey.user_id == user.id)
        .order_by(ApiKey.created_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=ApiKeyCreated, status_code=201)
async def create_api_key(
    body: ApiKeyCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    count = (
        await db.execute(
            select(ApiKey).where(ApiKey.user_id == user.id)
        )
    ).scalars().all()
    if len(count) >= MAX_KEYS_PER_USER:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum of {MAX_KEYS_PER_USER} API keys allowed per account.",
        )

    raw_key, prefix, digest = _generate_key()
    expires_at = None
    if body.expires_in_days:
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=body.expires_in_days)

    api_key = ApiKey(
        user_id=user.id,
        name=body.name,
        key_prefix=prefix,
        key_hash=digest,
        expires_at=expires_at,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    return ApiKeyCreated(
        id=api_key.id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        expires_at=api_key.expires_at,
        last_used_at=api_key.last_used_at,
        created_at=api_key.created_at,
        key=raw_key,
    )


@router.delete("/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user.id)
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")
    await db.delete(api_key)
    await db.commit()
