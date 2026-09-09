"""In-process scheduler. Minimal today (alerts are on-request only).

This is the hook point for later proactive features: reminder pushes, a morning
digest, low-stock shopping nudges. Each capability can contribute jobs via
`Capability.scheduled_jobs()`; wire them in `start()` when you enable them.
"""

from __future__ import annotations

from collections.abc import Callable

from apscheduler.schedulers.background import BackgroundScheduler

from family_agent.logging_setup import get_logger

log = get_logger(__name__)


class SchedulerService:
    def __init__(self, timezone: str) -> None:
        self._sched = BackgroundScheduler(timezone=timezone)

    def add_cron(self, func: Callable[[], None], *, hour: int, minute: int, id: str) -> None:
        self._sched.add_job(func, "cron", hour=hour, minute=minute, id=id, replace_existing=True)
        log.info("scheduler.job_added", id=id, hour=hour, minute=minute)

    def start(self) -> None:
        # No jobs registered yet — proactive alerts are a future feature.
        self._sched.start()
        log.info("scheduler.started", jobs=len(self._sched.get_jobs()))

    def shutdown(self) -> None:
        self._sched.shutdown(wait=False)
