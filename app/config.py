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


settings = Settings()
