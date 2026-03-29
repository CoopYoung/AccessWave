import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth import create_access_token, hash_password, verify_password
from app.config import settings
from app.database import get_db
from app.limiter import limiter
from app.metrics import AUTH_ATTEMPTS
from app.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = structlog.get_logger("accesswave.auth")


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def email_constraints(cls, v: str) -> str:
        if len(v) > 255:
            raise ValueError("Email must not exceed 255 characters")
        return v.lower()

    @field_validator("password")
    @classmethod
    def password_constraints(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if len(v) > 128:
            raise ValueError("Password must not exceed 128 characters")
        if not v.strip():
            raise ValueError("Password must not consist entirely of whitespace")
        return v


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/register", response_model=TokenResponse, status_code=201)
@limiter.limit(settings.RATE_LIMIT_AUTH_REGISTER)
async def register(request: Request, body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none():
        logger.warning("register_duplicate_email", email=body.email)
        raise HTTPException(status_code=400, detail="Email already registered")
        AUTH_ATTEMPTS.labels(endpoint="register", outcome="failure").inc()
        raise HTTPException(status_code=400, detail="Email already registered")
    if len(body.password) < 8:
        AUTH_ATTEMPTS.labels(endpoint="register", outcome="failure").inc()
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    user = User(email=body.email, hashed_password=hash_password(body.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info("user_registered", user_id=user.id, email=user.email)
    AUTH_ATTEMPTS.labels(endpoint="register", outcome="success").inc()
    return TokenResponse(access_token=create_access_token(user.id))


@router.post("/login", response_model=TokenResponse)
@limiter.limit(settings.RATE_LIMIT_AUTH_LOGIN)
async def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == form.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form.password, user.hashed_password):
        logger.warning("login_failed", email=form.username)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    logger.info("user_login", user_id=user.id, email=user.email)
        AUTH_ATTEMPTS.labels(endpoint="login", outcome="failure").inc()
        raise HTTPException(status_code=401, detail="Invalid credentials")
    AUTH_ATTEMPTS.labels(endpoint="login", outcome="success").inc()
    return TokenResponse(access_token=create_access_token(user.id))
