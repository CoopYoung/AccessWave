import hashlib
import structlog
import datetime
import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
import jwt
from jwt.exceptions import PyJWTError as JWTError
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.audit import log_action
from app.auth import create_access_token, create_email_verify_token, create_pre_auth_token, create_password_reset_token, get_current_user, hash_password, verify_password
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
    """Returned by POST /login — either a full token or a 2FA challenge."""
    access_token: str | None = None
    token_type: str = "bearer"
    requires_totp: bool = False
    pre_auth_token: str | None = None


class TotpVerifyLoginRequest(BaseModel):
    pre_auth_token: str
    totp_code: str


class TotpSetupResponse(BaseModel):
    secret: str
    provisioning_uri: str


class TotpEnableRequest(BaseModel):
    totp_code: str


class TotpDisableRequest(BaseModel):
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    plan: str
    email_verified: bool
    is_admin: bool = False
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


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def pw_constraints(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if len(v) > 128:
            raise ValueError("Password must not exceed 128 characters")
        return v


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
    if settings.email_enabled:
        from app.services.email_service import send_verification_email
        token = create_email_verify_token(user.id, user.email)
        verify_url = f"{settings.BASE_URL}/verify-email?token={token}"
        await send_verification_email(to_address=user.email, verify_url=verify_url)
    return TokenResponse(access_token=create_access_token(user.id, user.token_version or 0))


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Log in",
    description=(
        "Authenticate with email + password (OAuth2 `password` flow). "
        "If 2FA is enabled, returns `requires_totp: true` and a `pre_auth_token` instead of a full JWT. "
        "Call POST /api/auth/login/totp with the pre_auth_token and TOTP code to complete login."
    ),
)
@limiter.limit(settings.RATE_LIMIT_AUTH_LOGIN)
async def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == form.username))
    user = result.scalar_one_or_none()

    # Check if account is currently locked
    now = datetime.datetime.utcnow()
    if user and user.locked_until and user.locked_until > now:
        remaining = int((user.locked_until - now).total_seconds() // 60) + 1
        logger.warning("login_account_locked", user_id=user.id, locked_until=str(user.locked_until))
        AUTH_ATTEMPTS.labels(endpoint="login", outcome="locked").inc()
        raise HTTPException(
            status_code=429,
            detail=f"Account locked due to too many failed attempts. Try again in {remaining} minute(s).",
        )

    if not user or not verify_password(form.password, user.hashed_password):
        logger.warning("login_failed", email=form.username)
        AUTH_ATTEMPTS.labels(endpoint="login", outcome="failure").inc()
        uid = user.id if user else None
        if user:
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= settings.MAX_LOGIN_ATTEMPTS:
                user.locked_until = now + datetime.timedelta(minutes=settings.LOCKOUT_MINUTES)
                logger.warning(
                    "login_account_locked_now",
                    user_id=user.id,
                    attempts=user.failed_login_attempts,
                    locked_until=str(user.locked_until),
                )
                await log_action(db, action="login.account_locked", user_id=uid, request=request,
                                 extra={"email": form.username, "attempts": user.failed_login_attempts})
            else:
                await log_action(db, action="login.failure", user_id=uid, request=request,
                                 extra={"email": form.username, "attempts": user.failed_login_attempts})
        else:
            await log_action(db, action="login.failure", user_id=None, request=request,
                             extra={"email": form.username})
        await db.commit()
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Successful password check — reset lockout counters
    if user.failed_login_attempts or user.locked_until:
        user.failed_login_attempts = 0
        user.locked_until = None

    # If 2FA is enabled, issue a pre-auth token instead of a full JWT
    if user.totp_enabled and user.totp_secret:
        pre_token = create_pre_auth_token(user.id)
        logger.info("login_2fa_required", user_id=user.id)
        AUTH_ATTEMPTS.labels(endpoint="login", outcome="2fa_required").inc()
        await db.commit()
        return LoginResponse(requires_totp=True, pre_auth_token=pre_token)

    logger.info("user_login", user_id=user.id, email=user.email)
    AUTH_ATTEMPTS.labels(endpoint="login", outcome="success").inc()
    await log_action(db, action="login.success", user_id=user.id, request=request)
    await db.commit()
    return LoginResponse(access_token=create_access_token(user.id, user.token_version or 0))


@router.post(
    "/login/totp",
    response_model=TokenResponse,
    summary="Complete 2FA login",
    description="Exchange a pre_auth_token + TOTP code for a full access token.",
)
@limiter.limit("10/minute")
async def login_totp(
    request: Request,
    body: TotpVerifyLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = jwt.decode(body.pre_auth_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired pre-auth token")
    if payload.get("type") != "pre_auth":
        raise HTTPException(status_code=401, detail="Invalid or expired pre-auth token")
    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired pre-auth token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.totp_enabled or not user.totp_secret:
        raise HTTPException(status_code=401, detail="Invalid or expired pre-auth token")

    totp = pyotp.TOTP(user.totp_secret)
    code = body.totp_code.strip().replace(" ", "")
    if not totp.verify(code, valid_window=1):
        AUTH_ATTEMPTS.labels(endpoint="login_totp", outcome="failure").inc()
        await log_action(db, action="login.2fa_failure", user_id=user.id, request=request)
        await db.commit()
        raise HTTPException(status_code=401, detail="Invalid authenticator code")

    logger.info("user_login_2fa", user_id=user.id, email=user.email)
    AUTH_ATTEMPTS.labels(endpoint="login_totp", outcome="success").inc()
    await log_action(db, action="login.success", user_id=user.id, request=request,
                     extra={"method": "2fa"})
    await db.commit()
    return TokenResponse(access_token=create_access_token(user.id, user.token_version or 0))


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


@router.post(
    "/verify-email",
    status_code=200,
    summary="Verify email address",
    description="Mark the account's email as verified using the token from the verification email.",
)
@limiter.limit("10/minute")
async def verify_email(
    request: Request,
    token: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")
    if payload.get("type") != "email_verify":
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")
    try:
        user_id = int(payload["sub"])
        token_email = payload["email"]
    except (KeyError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")
    if user.email != token_email:
        raise HTTPException(status_code=400, detail="This link is no longer valid — your email has changed")
    if user.email_verified:
        return {"ok": True, "message": "Email already verified."}
    user.email_verified = True
    await log_action(db, action="email.verified", user_id=user.id, request=request)
    await db.commit()
    logger.info("email_verified", user_id=user.id)
    return {"ok": True, "message": "Email address verified successfully."}


@router.post(
    "/verify-email/send",
    status_code=200,
    summary="Resend verification email",
    description="Send (or resend) the email verification link to the authenticated user.",
)
@limiter.limit("3/minute")
async def resend_verification_email(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.email_verified:
        return {"ok": True, "message": "Email is already verified."}
    if not settings.email_enabled:
        raise HTTPException(status_code=503, detail="Email delivery is not configured")
    from app.services.email_service import send_verification_email
    token = create_email_verify_token(user.id, user.email)
    verify_url = f"{settings.BASE_URL}/verify-email?token={token}"
    await send_verification_email(to_address=user.email, verify_url=verify_url)
    await log_action(db, action="email.verify_resent", user_id=user.id, request=request)
    await db.commit()
    logger.info("verification_email_resent", user_id=user.id)
    return {"ok": True, "message": "Verification email sent. Please check your inbox."}


@router.post(
    "/forgot-password",
    status_code=200,
    summary="Request a password-reset email",
    description=(
        "Send a one-time password-reset link to the given email address. "
        "Always returns 200 to prevent email enumeration. "
        "The link expires after 15 minutes."
    ),
)
@limiter.limit("5/minute")
async def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    # Look up the user — but always return the same response to avoid leaking
    # whether a given email address is registered.
    result = await db.execute(select(User).where(User.email == str(body.email).lower()))
    user = result.scalar_one_or_none()
    if user and settings.email_enabled:
        from app.services.email_service import send_password_reset  # local import avoids circular at module level
        token = create_password_reset_token(user.id, user.hashed_password)
        reset_url = f"{settings.BASE_URL}/reset-password?token={token}"
        await send_password_reset(to_address=user.email, reset_url=reset_url)
        await log_action(db, action="password.reset_requested", user_id=user.id, request=request)
        await db.commit()
    logger.info("forgot_password_requested", email=str(body.email))
    return {"ok": True, "message": "If that email is registered, a reset link has been sent."}


@router.post(
    "/reset-password",
    status_code=200,
    summary="Reset password using a token",
    description="Set a new password using the token from the reset email. The token is single-use.",
)
@limiter.limit("10/minute")
async def reset_password(
    request: Request,
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    # Decode the JWT without fingerprint check first to get user_id
    try:
        payload = jwt.decode(body.token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    if payload.get("type") != "pwd_reset":
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    # Validate fingerprint — token is stale if password already changed
    fingerprint = hashlib.sha256(user.hashed_password.encode()).hexdigest()[:16]
    if payload.get("fp") != fingerprint:
        raise HTTPException(status_code=400, detail="This reset link has already been used")

    user.hashed_password = hash_password(body.new_password)
    await log_action(db, action="password.reset_completed", user_id=user.id, request=request)
    await db.commit()
    logger.info("password_reset_completed", user_id=user.id)
    return {"ok": True, "message": "Password updated. You can now log in."}


# ── Two-Factor Authentication (TOTP) ─────────────────────────────────────────

@router.get(
    "/2fa/setup",
    response_model=TotpSetupResponse,
    summary="Begin 2FA setup",
    description=(
        "Generate a TOTP secret and provisioning URI for the authenticated user. "
        "The secret is stored temporarily (2FA is NOT enabled until /2fa/enable is called). "
        "Use the provisioning_uri to render a QR code with any TOTP library."
    ),
)
async def setup_2fa(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    secret = pyotp.random_base32()
    user.totp_secret = secret
    user.totp_enabled = False  # not yet confirmed
    await db.commit()
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=user.email, issuer_name="AccessWave")
    return TotpSetupResponse(secret=secret, provisioning_uri=uri)


@router.post(
    "/2fa/enable",
    status_code=200,
    summary="Enable 2FA",
    description="Verify the user's current TOTP code and activate 2FA on the account.",
)
async def enable_2fa(
    request: Request,
    body: TotpEnableRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user.totp_secret:
        raise HTTPException(status_code=400, detail="Call /2fa/setup first to generate a secret")
    if user.totp_enabled:
        raise HTTPException(status_code=400, detail="2FA is already enabled")
    totp = pyotp.TOTP(user.totp_secret)
    code = body.totp_code.strip().replace(" ", "")
    if not totp.verify(code, valid_window=1):
        raise HTTPException(status_code=400, detail="Invalid authenticator code — please try again")
    user.totp_enabled = True
    await log_action(db, action="2fa.enabled", user_id=user.id, request=request)
    await db.commit()
    logger.info("2fa_enabled", user_id=user.id)
    return {"ok": True, "message": "Two-factor authentication is now enabled."}


@router.delete(
    "/2fa/disable",
    status_code=200,
    summary="Disable 2FA",
    description="Disable 2FA after confirming the user's password.",
)
async def disable_2fa(
    request: Request,
    body: TotpDisableRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user.totp_enabled:
        raise HTTPException(status_code=400, detail="2FA is not enabled on this account")
    if not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect password")
    user.totp_enabled = False
    user.totp_secret = None
    await log_action(db, action="2fa.disabled", user_id=user.id, request=request)
    await db.commit()
    logger.info("2fa_disabled", user_id=user.id)
    return {"ok": True, "message": "Two-factor authentication has been disabled."}


@router.get(
    "/2fa/status",
    summary="Get 2FA status",
    description="Returns whether 2FA is currently enabled for the authenticated user.",
)
async def get_2fa_status(user: User = Depends(get_current_user)):
    return {"totp_enabled": user.totp_enabled}


@router.post(
    "/logout",
    status_code=200,
    summary="Log out",
    description=(
        "Invalidate the current JWT by incrementing the user's token_version. "
        "The token is still syntactically valid but will be rejected on all "
        "subsequent requests. The client should discard the token."
    ),
)
async def logout(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user.token_version = (user.token_version or 0) + 1
    await log_action(db, action="auth.logout", user_id=user.id, request=request)
    await db.commit()
    logger.info("user_logout", user_id=user.id)
    return {"ok": True, "message": "Logged out successfully"}


@router.post(
    "/logout-all",
    status_code=200,
    summary="Sign out of all devices",
    description=(
        "Invalidate all active JWTs for this account by incrementing token_version. "
        "Every device or API client using a token for this account will be signed out "
        "immediately. A new token can be obtained by logging in again."
    ),
)
async def logout_all(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user.token_version = (user.token_version or 0) + 1
    await log_action(db, action="auth.logout_all", user_id=user.id, request=request)
    await db.commit()
    logger.info("user_logout_all", user_id=user.id)
    return {"ok": True, "message": "All sessions have been revoked"}
