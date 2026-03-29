"""Celery tasks for AccessWave.

Each task is a thin wrapper around the existing async service layer.
Because Celery workers are not an async event-loop context, we use
``asyncio.run()`` to drive the coroutines synchronously inside each task.
"""

import asyncio
import logging

from celery.exceptions import SoftTimeLimitExceeded

from app.worker import celery_app
from app.services.scan_runner import run_scan

logger = logging.getLogger("accesswave.tasks")


@celery_app.task(
    name="accesswave.tasks.run_scan",
    bind=True,
    max_retries=3,
    default_retry_delay=60,   # seconds between automatic retries
    soft_time_limit=300,      # raises SoftTimeLimitExceeded after 5 min
    time_limit=360,           # SIGKILL after 6 min
)
def celery_run_scan(self, scan_id: int, max_pages: int = 5) -> None:
    """Execute a full accessibility scan as a Celery task.

    Args:
        scan_id:   Primary key of the ``Scan`` row to execute.
        max_pages: Maximum number of pages to crawl (plan-dependent).

    The underlying ``run_scan`` coroutine manages all DB writes and
    transitions the scan status from *pending* → *running* → *completed*
    (or *failed*) itself, so this task does not need to touch the DB
    directly.
    """
    logger.info("Task %s: starting scan %d (max_pages=%d)", self.request.id, scan_id, max_pages)
    try:
        asyncio.run(run_scan(scan_id, max_pages=max_pages))
        logger.info("Task %s: scan %d finished", self.request.id, scan_id)
    except SoftTimeLimitExceeded:
        # The scan is taking too long; mark it failed and do not retry.
        logger.warning("Task %s: scan %d hit soft time limit", self.request.id, scan_id)
        asyncio.run(_mark_scan_failed(scan_id, "time limit exceeded"))
    except Exception as exc:
        logger.error("Task %s: scan %d failed with %r — retrying", self.request.id, scan_id, exc)
        raise self.retry(exc=exc)


async def _mark_scan_failed(scan_id: int, reason: str) -> None:
    """Failsafe: set scan status to failed when the task is killed."""
    import datetime
    from sqlalchemy import select
    from app.database import async_session
    from app.models import Scan

    async with async_session() as db:
        result = await db.execute(select(Scan).where(Scan.id == scan_id))
        scan = result.scalar_one_or_none()
        if scan and scan.status not in ("completed", "failed"):
            scan.status = "failed"
            scan.completed_at = datetime.datetime.utcnow()
            await db.commit()
            logger.info("Marked scan %d as failed (%s)", scan_id, reason)
