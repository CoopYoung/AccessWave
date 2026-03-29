"""Periodic scan scheduler using APScheduler.

Polls the database every 5 minutes for sites whose next_scan_at has passed
and whose schedule is not 'none', then fires off a background scan for each.
"""

import asyncio
import datetime
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import func, select

from app.config import settings
from app.database import async_session
from app.models import Scan, Site, User
from app.services.scan_runner import run_scan

logger = logging.getLogger("accesswave.scheduler")

# Cadence → timedelta
_CADENCE_DELTA: dict[str, datetime.timedelta] = {
    "daily": datetime.timedelta(days=1),
    "weekly": datetime.timedelta(weeks=1),
    "monthly": datetime.timedelta(days=30),
}

scheduler = AsyncIOScheduler(timezone="UTC")


def next_run_time(schedule: str, from_time: datetime.datetime) -> datetime.datetime | None:
    """Return the next scheduled run time for a given cadence."""
    delta = _CADENCE_DELTA.get(schedule)
    return from_time + delta if delta else None


async def _dispatch_scheduled_scans() -> None:
    """Fire scans for all sites that are due."""
    now = datetime.datetime.utcnow()
    async with async_session() as db:
        result = await db.execute(
            select(Site).where(
                Site.schedule != "none",
                Site.next_scan_at != None,  # noqa: E711
                Site.next_scan_at <= now,
            )
        )
        due_sites = result.scalars().all()

        for site in due_sites:
            # Skip if a scan is already in flight
            running = (
                await db.execute(
                    select(func.count())
                    .select_from(Scan)
                    .where(
                        Scan.site_id == site.id,
                        Scan.status.in_(["pending", "running"]),
                    )
                )
            ).scalar()
            if running:
                logger.info("scheduled_scan_skipped site_id=%s reason=already_running", site.id)
                continue

            # Resolve the user's plan to get the page cap
            user_result = await db.execute(select(User).where(User.id == site.user_id))
            user = user_result.scalar_one_or_none()
            if not user:
                continue
            max_pages = settings.PLAN_LIMITS[user.plan]["pages_per_scan"]

            # Create the Scan record
            scan = Scan(site_id=site.id)
            db.add(scan)

            # Advance next_scan_at immediately so concurrent ticks don't double-fire
            site.next_scan_at = next_run_time(site.schedule, now)

            await db.commit()
            await db.refresh(scan)

            logger.info(
                "scheduled_scan_started site_id=%s scan_id=%s schedule=%s",
                site.id,
                scan.id,
                site.schedule,
            )
            # Fire-and-forget; run_scan manages its own session
            asyncio.create_task(run_scan(scan.id, max_pages=max_pages))


def start_scheduler() -> None:
    """Register the polling job and start the scheduler."""
    scheduler.add_job(
        _dispatch_scheduled_scans,
        trigger=IntervalTrigger(minutes=5),
        id="dispatch_scheduled_scans",
        replace_existing=True,
        misfire_grace_time=60,
    )
    scheduler.start()
    logger.info("scheduler_started poll_interval=5m")


def stop_scheduler() -> None:
    """Gracefully stop the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("scheduler_stopped")
