import structlog
import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.audit import log_action
from app.auth import create_access_token, get_current_user, hash_password, verify_password
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


class UserOut(BaseModel):
    id: int
    email: str
    plan: str
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class UpdateProfileRequest(BaseModel):
    email: EmailStr


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class DeleteAccountRequest(BaseModel):
    password: str


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=201,
    summary="Create a new account",
    description="Register with an email and password. Returns a Bearer JWT on success.",
)
@limiter.limit(settings.RATE_LIMIT_AUTH_REGISTER)
async def register(request: Request, body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none():
        logger.warning("register_duplicate_email", email=body.email)
        AUTH_ATTEMPTS.labels(endpoint="register", outcome="failure").inc()
        raise HTTPException(status_code=400, detail="Email already registered")
    if len(body.password) < 8:
        AUTH_ATTEMPTS.labels(endpoint="register", outcome="failure").inc()
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    user = User(email=body.email, hashed_password=hash_password(body.password))
    db.add(user)
    await db.flush()
    await log_action(db, action="register.success", user_id=user.id, request=request,
                     extra={"email": user.email})
    await db.commit()
    await db.refresh(user)
    logger.info("user_registered", user_id=user.id, email=user.email)
    AUTH_ATTEMPTS.labels(endpoint="register", outcome="success").inc()
    return TokenResponse(access_token=create_access_token(user.id))


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Log in",
    description=(
        "Authenticate with email + password (OAuth2 `password` flow). "
        "Returns a short-lived Bearer JWT valid for the duration set in `ACCESS_TOKEN_EXPIRE_MINUTES`."
    ),
)
@limiter.limit(settings.RATE_LIMIT_AUTH_LOGIN)
async def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == form.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form.password, user.hashed_password):
        logger.warning("login_failed", email=form.username)
        AUTH_ATTEMPTS.labels(endpoint="login", outcome="failure").inc()
        # Log failure (user_id may be None if email not found)
        uid = user.id if user else None
        await log_action(db, action="login.failure", user_id=uid, request=request,
                         extra={"email": form.username})
        await db.commit()
        raise HTTPException(status_code=401, detail="Invalid credentials")
    logger.info("user_login", user_id=user.id, email=user.email)
    AUTH_ATTEMPTS.labels(endpoint="login", outcome="success").inc()
    await log_action(db, action="login.success", user_id=user.id, request=request)
    await db.commit()
    return TokenResponse(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut, summary="Get current user")
async def get_me(user: User = Depends(get_current_user)):
    return user


@router.put("/profile", response_model=UserOut)
async def update_profile(
    request: Request,
    body: UpdateProfileRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    new_email = str(body.email).lower()
    if new_email != user.email:
        existing = await db.execute(select(User).where(User.email == new_email))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Email already in use")
        old_email = user.email
        user.email = new_email
        await log_action(db, action="profile.updated", user_id=user.id, request=request,
                         extra={"old_email": old_email, "new_email": new_email})
        await db.commit()
        await db.refresh(user)
    return user


@router.put("/password", status_code=204)
async def change_password(
    request: Request,
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")
    if body.current_password == body.new_password:
        raise HTTPException(status_code=400, detail="New password must differ from current password")
    user.hashed_password = hash_password(body.new_password)
    await log_action(db, action="password.changed", user_id=user.id, request=request)
    await db.commit()


@router.delete("/account", status_code=204)
async def delete_account(
    request: Request,
    body: DeleteAccountRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect password")
    # Log before deletion so the user_id FK still resolves during the flush
    await log_action(db, action="account.deleted", user_id=user.id, request=request,
                     extra={"email": user.email})
    await db.flush()
    await db.delete(user)
    await db.commit()
