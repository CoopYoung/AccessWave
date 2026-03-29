import time
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.database import async_session

router = APIRouter(tags=["health"])

_start_time = time.monotonic()


@router.get("/health")
async def liveness():
    """Liveness probe — confirms the process is alive and event loop is running."""
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": round(time.monotonic() - _start_time, 1),
    }


@router.get("/ready")
async def readiness():
    """Readiness probe — confirms the app can serve traffic (DB reachable)."""
    checks: dict[str, str] = {}
    all_ok = True

    # Database check
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except OperationalError as exc:
        checks["database"] = f"error: {exc.orig}"
        all_ok = False
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"error: {exc}"
        all_ok = False

    status_code = 200 if all_ok else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok" if all_ok else "degraded",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checks": checks,
        },
    )
