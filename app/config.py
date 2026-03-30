import os
import re
from dotenv import load_dotenv

load_dotenv()


def _normalise_db_url(url: str) -> str:
    """Canonicalise a database URL so it always uses an async driver.

    Many PaaS providers (Heroku, Railway, Render) emit bare ``postgres://`` or
    ``postgresql://`` URLs.  SQLAlchemy's async engine requires the asyncpg
    driver variant, so we rewrite those on the way in rather than requiring
    every deployment to remember the exact scheme.
    """
    # postgres:// → postgresql+asyncpg://
    url = re.sub(r"^postgres://", "postgresql+asyncpg://", url)
    # postgresql:// (no driver) → postgresql+asyncpg://
    url = re.sub(r"^postgresql://", "postgresql+asyncpg://", url)
    return url


class Settings:
    DATABASE_URL: str = _normalise_db_url(
        os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./accesswave.db")
    )

    @property
    def db_dialect(self) -> str:
        """Return the SQLAlchemy dialect name, e.g. ``'sqlite'`` or ``'postgresql'``."""
        return self.DATABASE_URL.split("+")[0].split(":")[0]

    # PostgreSQL connection-pool tuning (ignored for SQLite)
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "5"))
    DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "10"))
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-change-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_PUBLISHABLE_KEY: str = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
    STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    STRIPE_PRICE_PRO: str = os.getenv("STRIPE_PRICE_PRO", "")
    STRIPE_PRICE_AGENCY: str = os.getenv("STRIPE_PRICE_AGENCY", "")
    BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8000")

    PLAN_LIMITS: dict = {
        "free": {"sites": 1, "pages_per_scan": 5, "scans_per_month": 3},
        "pro": {"sites": 10, "pages_per_scan": 50, "scans_per_month": 100},
        "agency": {"sites": 50, "pages_per_scan": 200, "scans_per_month": 1000},
    }

    SCAN_TIMEOUT: int = 30
    MAX_CRAWL_DEPTH: int = 3

    # Rate limiting (requests per window, e.g. "5/minute")
    RATE_LIMIT_AUTH_REGISTER: str = os.getenv("RATE_LIMIT_AUTH_REGISTER", "5/minute")
    RATE_LIMIT_AUTH_LOGIN: str = os.getenv("RATE_LIMIT_AUTH_LOGIN", "10/minute")
    RATE_LIMIT_SCAN_START: str = os.getenv("RATE_LIMIT_SCAN_START", "10/minute")
    RATE_LIMIT_DEFAULT: str = os.getenv("RATE_LIMIT_DEFAULT", "60/minute")

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    # "console" → human-readable coloured output (dev); "json" → JSON lines (production)
    LOG_FORMAT: str = os.getenv("LOG_FORMAT", "console")
    # CORS — comma-separated list of allowed origins.
    # Set to "*" only for fully public, read-only APIs.
    # Default: the app's own BASE_URL so the frontend works out of the box.
    CORS_ORIGINS: list[str] = [
        o.strip()
        for o in os.getenv("CORS_ORIGINS", os.getenv("BASE_URL", "http://localhost:8000")).split(",")
        if o.strip()
    ]

    # Security headers
    # Set HSTS_ENABLED=true only when the app is served over HTTPS in production.
    HSTS_ENABLED: bool = os.getenv("HSTS_ENABLED", "false").lower() == "true"
    # Optional URI for CSP violation reports (leave blank to omit the directive).
    CSP_REPORT_URI: str = os.getenv("CSP_REPORT_URI", "")
    # Celery task queue
    # Set USE_CELERY=true and configure the URLs below to enable distributed scanning.
    # When disabled (default) scans run in FastAPI background tasks (single-process only).
    USE_CELERY: bool = os.getenv("USE_CELERY", "false").lower() == "true"
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

    # Email notifications (SMTP)
    # Leave SMTP_HOST blank to disable email delivery entirely.
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME: str = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    # Use STARTTLS on port 587 (default). Set SMTP_USE_TLS=true for SSL on 465.
    SMTP_USE_TLS: bool = os.getenv("SMTP_USE_TLS", "false").lower() == "true"
    SMTP_FROM_ADDRESS: str = os.getenv("SMTP_FROM_ADDRESS", "noreply@accesswave.app")
    SMTP_FROM_NAME: str = os.getenv("SMTP_FROM_NAME", "AccessWave")

    @property
    def email_enabled(self) -> bool:
        """True when SMTP_HOST is configured."""
        return bool(self.SMTP_HOST)


settings = Settings()
