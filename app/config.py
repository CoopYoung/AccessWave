import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./accesswave.db")
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


settings = Settings()
