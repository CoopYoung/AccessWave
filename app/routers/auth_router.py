import structlog
import datetime
import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth import create_access_token, create_partial_token, get_current_user, hash_password, verify_password
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


class LoginResponse(BaseModel):
    """Returned by POST /login.

    Normal login: ``access_token`` is populated.
    2FA required: ``requires_2fa=True`` and ``partial_token`` are populated;
    the client must call POST /2fa/verify to exchange them for a full token.
    """
    access_token: str | None = None
    token_type: str = "bearer"
    requires_2fa: bool = False
    partial_token: str | None = None


class UserOut(BaseModel):
    id: int
    email: str
    plan: str
    created_at: datetime.datetime
    totp_enabled: bool = False

    class Config:
        from_attributes = True


class TwoFactorSetupOut(BaseModel):
    secret: str
    uri: str


class TwoFactorVerifySetupRequest(BaseModel):
    code: str


class TwoFactorVerifyRequest(BaseModel):
    partial_token: str
    code: str


class TwoFactorDisableRequest(BaseModel):
    password: str


class UpdateProfileRequest(BaseModel):
    email: EmailStr


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class DeleteAccountRequest(BaseModel):
    password: str


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


@router.post("/login", response_model=LoginResponse)
@limiter.limit(settings.RATE_LIMIT_AUTH_LOGIN)
async def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == form.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form.password, user.hashed_password):
        logger.warning("login_failed", email=form.username)
        AUTH_ATTEMPTS.labels(endpoint="login", outcome="failure").inc()
        raise HTTPException(status_code=401, detail="Invalid credentials")
    logger.info("user_login", user_id=user.id, email=user.email)
    AUTH_ATTEMPTS.labels(endpoint="login", outcome="success").inc()
    if user.totp_enabled:
        return LoginResponse(requires_2fa=True, partial_token=create_partial_token(user.id))
    return LoginResponse(access_token=create_access_token(user.id))


# ── Two-Factor Authentication ─────────────────────────────────────────────────

@router.post("/2fa/setup", response_model=TwoFactorSetupOut)
async def setup_2fa(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Generate a new TOTP secret and return the provisioning URI.

    The secret is stored (unconfirmed) until the user verifies a code via
    POST /2fa/verify-setup.  Calling this endpoint again resets the secret,
    which is safe — 2FA is not yet active until verify-setup succeeds.
    """
    secret = pyotp.random_base32()
    user.totp_secret = secret
    await db.commit()
    uri = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name="AccessWave")
    logger.info("2fa_setup_initiated", user_id=user.id)
    return TwoFactorSetupOut(secret=secret, uri=uri)


@router.post("/2fa/verify-setup", status_code=204)
async def verify_2fa_setup(
    body: TwoFactorVerifySetupRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Confirm a TOTP code and activate 2FA for the account."""
    if not user.totp_secret:
        raise HTTPException(status_code=400, detail="2FA setup not initiated")
    if not pyotp.TOTP(user.totp_secret).verify(body.code, valid_window=1):
        raise HTTPException(status_code=400, detail="Invalid verification code")
    user.totp_enabled = True
    await db.commit()
    logger.info("2fa_enabled", user_id=user.id)


@router.post("/2fa/verify", response_model=TokenResponse)
@limiter.limit(settings.RATE_LIMIT_AUTH_LOGIN)
async def verify_2fa(request: Request, body: TwoFactorVerifyRequest, db: AsyncSession = Depends(get_db)):
    """Exchange a partial token + TOTP code for a full access token."""
    try:
        payload = jwt.decode(body.partial_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if payload.get("type") != "2fa_pending":
        raise HTTPException(status_code=401, detail="Invalid token type")
    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.totp_enabled or not user.totp_secret:
        raise HTTPException(status_code=401, detail="Invalid token")
    if not pyotp.TOTP(user.totp_secret).verify(body.code, valid_window=1):
        AUTH_ATTEMPTS.labels(endpoint="2fa_verify", outcome="failure").inc()
        raise HTTPException(status_code=400, detail="Invalid authentication code")
    AUTH_ATTEMPTS.labels(endpoint="2fa_verify", outcome="success").inc()
    logger.info("2fa_verified", user_id=user.id)
    return TokenResponse(access_token=create_access_token(user.id))


@router.post("/2fa/disable", status_code=204)
async def disable_2fa(
    body: TwoFactorDisableRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Disable 2FA after confirming the account password."""
    if not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect password")
    user.totp_enabled = False
    user.totp_secret = None
    await db.commit()
    logger.info("2fa_disabled", user_id=user.id)


@router.get("/me", response_model=UserOut)
async def get_me(user: User = Depends(get_current_user)):
    return user


@router.put("/profile", response_model=UserOut)
async def update_profile(
    body: UpdateProfileRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    new_email = str(body.email).lower()
    if new_email != user.email:
        existing = await db.execute(select(User).where(User.email == new_email))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Email already in use")
        user.email = new_email
        await db.commit()
        await db.refresh(user)
    return user


@router.put("/password", status_code=204)
async def change_password(
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
    await db.commit()


@router.delete("/account", status_code=204)
async def delete_account(
    body: DeleteAccountRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect password")
    await db.delete(user)
    await db.commit()
