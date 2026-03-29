"""Celery application instance.

Import this module to get the configured Celery app.
Start a worker with:

    celery -A app.worker worker --loglevel=info --concurrency=4

The worker processes scan tasks asynchronously, allowing the FastAPI
process to remain responsive while long-running scans execute in the
background across multiple worker processes / machines.
"""

from celery import Celery

from app.config import settings

celery_app = Celery(
    "accesswave",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks"],
)

celery_app.conf.update(
    # Serialisation
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Reliability: acknowledge only after the task completes so a worker
    # crash does not silently drop a scan.
    task_acks_late=True,
    # Prefetch one task at a time — scan tasks are long-running and we
    # don't want a slow worker to hoard queued items.
    worker_prefetch_multiplier=1,
    # Record when a task moves from pending → started, visible via the
    # result backend, useful for the /scans/{id} status poll.
    task_track_started=True,
    # Per-task time limits (seconds).  Overridden per-task where needed.
    task_soft_time_limit=300,   # 5 min: raises SoftTimeLimitExceeded
    task_time_limit=360,        # 6 min: SIGKILL
    # Timezone
    enable_utc=True,
)
