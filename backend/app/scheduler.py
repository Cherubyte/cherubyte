"""APScheduler wiring for the periodic network scan."""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .config import settings
from .models import utcnow
from .services.agent_health import check_agents
from .services.digest import run_weekly
from .services.hoststat import record_panel_temp
from .services.retention import run_purge
from .services.update import check as check_for_update

logger = logging.getLogger("cherubyte.scheduler")

scheduler = AsyncIOScheduler()
_PURGE_JOB_ID = "history-purge"
_DIGEST_JOB_ID = "weekly-digest"
_UPDATE_JOB_ID = "update-check"
_HOST_TEMP_JOB_ID = "host-temp-sample"
_AGENT_HEALTH_JOB_ID = "agent-health-check"

_state: dict = {"last_scan": None, "running": False}


def note_report() -> None:
    """Record that an agent just reported, for the dashboard's "last scan"."""
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
    # The panel is the one host no agent reports for, so it samples its own
    # sensor. Agents send theirs on every sweep. A generous misfire grace so a
    # busy event loop delays a reading rather than dropping it silently.
    scheduler.add_job(
        record_panel_temp,
        "interval",
        seconds=60,
        id=_HOST_TEMP_JOB_ID,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=45,
    )
    # Watch for an agent that has stopped reporting. Cheap (one indexed query),
    # so it can run often; the threshold that actually decides "silent" is
    # settings.agent_offline_after_seconds.
    scheduler.add_job(
        check_agents,
        "interval",
        seconds=120,
        id=_AGENT_HEALTH_JOB_ID,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
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
