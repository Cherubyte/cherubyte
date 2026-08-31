"""APScheduler wiring for the periodic network scan."""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .config import settings
from .services.digest import run_weekly
from .services.retention import run_purge
from .services.update import check as check_for_update

logger = logging.getLogger("cherubyte.scheduler")

scheduler = AsyncIOScheduler()
_PURGE_JOB_ID = "history-purge"
_DIGEST_JOB_ID = "weekly-digest"
_UPDATE_JOB_ID = "update-check"

_state: dict = {"last_scan": None, "running": False}


def note_report() -> None:
    """Record that an agent just reported, for the dashboard's "last scan"."""
    from .models import utcnow

    _state["last_scan"] = utcnow()


def start() -> None:
    scheduler.add_job(
        run_purge,
        "interval",
        hours=24,
        id=_PURGE_JOB_ID,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        run_weekly,
        "cron",
        day_of_week=settings.weekly_summary_weekday,
        hour=settings.weekly_summary_hour,
        minute=0,
        id=_DIGEST_JOB_ID,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        check_for_update,
        "interval",
        hours=12,
        id=_UPDATE_JOB_ID,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info("Scheduler started (retention=%sd)", settings.retention_days)


# NOTE: there is no scan job here any more, and no WAN probe. Both moved to the
# agent, which is the half that can see a network. The panel's cadence is now
# whatever the agents report at; `note_report` records it for the dashboard.


def reschedule_digest(weekday: int, hour: int) -> None:
    if scheduler.get_job(_DIGEST_JOB_ID):
        scheduler.reschedule_job(
            _DIGEST_JOB_ID, trigger="cron", day_of_week=weekday, hour=hour, minute=0
        )


def job_next_run_times() -> dict[str, object]:
    """{job_id: next_run_time} — None means the job is paused and will not fire."""
    return {j.id: j.next_run_time for j in scheduler.get_jobs()}


def last_scan():
    return _state["last_scan"]


def is_running() -> bool:
    return _state["running"]
