"""Custom Python Task Scheduler using APScheduler.

Manages recurring background jobs (rent reminders, daily digests, stale approval expiration)
without external visual workflow dependencies.
"""

from typing import Any, Callable, Dict, List

from app.core.logging import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler


class AutomationScheduler:
    """Thin wrapper around APScheduler AsyncIOScheduler for tenant and platform recurring jobs."""

    def __init__(self):
        self._scheduler = AsyncIOScheduler(timezone="UTC")
        self._started = False
        self._has_shutdown = False

    def start(self) -> None:
        """Start the async scheduler if not already running."""
        if not self._started:
            if self._scheduler.running or self._has_shutdown:
                self._scheduler = AsyncIOScheduler(timezone="UTC")
            self._has_shutdown = False
            self._scheduler.start()
            self._started = True
            logger.info("Custom Python AutomationScheduler started")

    def shutdown(self) -> None:
        """Gracefully stop the scheduler."""
        if self._started:
            try:
                self._scheduler.shutdown(wait=False)
            except Exception:
                pass
            self._started = False
            self._has_shutdown = True
            logger.info("Custom Python AutomationScheduler stopped")

    def schedule_interval_job(
        self,
        job_id: str,
        func: Callable[..., Any],
        seconds: int,
        kwargs: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Register or replace an interval-based recurring job."""
        job = self._scheduler.add_job(
            func,
            trigger="interval",
            seconds=seconds,
            id=job_id,
            kwargs=kwargs or {},
            replace_existing=True,
        )
        return {"job_id": job.id, "trigger": str(job.trigger)}

    def list_jobs(self) -> List[Dict[str, Any]]:
        """List all registered scheduled jobs."""
        return [
            {
                "id": job.id,
                "trigger": str(job.trigger),
            }
            for job in self._scheduler.get_jobs()
        ]


automation_scheduler = AutomationScheduler()
