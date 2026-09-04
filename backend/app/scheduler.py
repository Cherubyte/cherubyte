"""APScheduler wiring for the panel's periodic work.

Single-tenant: the jobs below, on the one database, as they always were.

Hosted: the same jobs, run once per tenant inside `scoped_to`, which gives
each pass that tenant's database *and* that tenant's settings. Two of them do
not go per tenant at all — the update check and the panel's own temperature
are facts about the machine, not about a customer, and writing one shared
box's sensor reading into twenty-five inventories would be noise in all of
them.

One tenant's failure must not stop the rest, so each pass is caught and
logged and the loop goes on. A job that dies silently for tenant seven and
keeps working for everyone else is the failure this design has to survive.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .config import settings
from .database import known_tenants, scoped_to
from .tenancy import PerTenant
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

# "When did an agent last report" is one customer's answer, so it is per tenant
# (see `PerTenant`). Held here rather than in the database because it is a fact
# about this process's uptime: after a restart nobody has reported yet, and
# that is the truthful answer.
_state: PerTenant[dict] = PerTenant(lambda: {"last_scan": None, "running": False})


def _scan_state() -> dict:
    return _state.get()


def note_report() -> None:
    """Record that an agent just reported, for the dashboard's "last scan"."""
    _scan_state()["last_scan"] = utcnow()


def last_scan():
    return _scan_state()["last_scan"]


def is_running() -> bool:
    return _scan_state()["running"]


def forget_tenant_state(tenant_id: str) -> None:
    """Drop a tenant's scan state — offboarding, and tests."""
    _state.forget(tenant_id)


# ── running a job for everyone ─────────────────────────────────────────────


async def _for_each_tenant(name: str, job) -> None:
    tenants = known_tenants()
    if not tenants:
        return
    failed = 0
    for tenant_id in tenants:
        try:
            async with scoped_to(tenant_id):
                await job()
        except Exception:
            failed += 1
            logger.exception("Job %s failed for tenant %s", name, tenant_id)
    logger.info("Job %s ran for %d tenants (%d failed)", name, len(tenants), failed)


async def _purge_every_tenant() -> None:
    await _for_each_tenant("history-purge", run_purge)


async def _agent_health_every_tenant() -> None:
    # Each tenant's own agents, and its own agent_offline_after_seconds.
    await _for_each_tenant("agent-health-check", check_agents)


async def _digest_every_tenant() -> None:
    # `run_weekly` checks weekly_summary_enabled itself, and under scoped_to
    # that flag is the tenant's own rather than whoever loaded last.
    await _for_each_tenant("weekly-digest", run_weekly)


# ── wiring ─────────────────────────────────────────────────────────────────


def start() -> None:
    if settings.multi_tenant:
        _start_hosted()
        return

    scheduler.add_job(
        run_purge, "interval", hours=24, id=_PURGE_JOB_ID, max_instances=1, coalesce=True
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
        check_for_update, "interval", hours=12, id=_UPDATE_JOB_ID, max_instances=1, coalesce=True
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


def _start_hosted() -> None:
    """The same work, once per tenant.

    The digest fires hourly and each tenant's own `weekly_summary_*` decides
    whether that hour is theirs — a single cron cannot serve tenants who
    picked different days, and one job per tenant would mean rescheduling
    every time somebody changed the setting.
    """
    scheduler.add_job(
        _purge_every_tenant, "interval", hours=24, id=_PURGE_JOB_ID, max_instances=1, coalesce=True
    )
    scheduler.add_job(
        _digest_every_tenant,
        "cron",
        minute=0,
        id=_DIGEST_JOB_ID,
        max_instances=1,
        coalesce=True,
    )
    # Watch for silent agents for every tenant. Unlike the update check and the
    # panel temperature below, "has my agent stopped reporting" is a question
    # about one customer's network, so it does go per tenant.
    scheduler.add_job(
        _agent_health_every_tenant,
        "interval",
        seconds=120,
        id=_AGENT_HEALTH_JOB_ID,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )
    # No update check and no panel temperature: both are about this machine,
    # and neither belongs in a customer's inventory.
    scheduler.start()
    logger.info("Scheduler started, hosted (%d tenants)", len(known_tenants()))


def reschedule_digest(weekday: int, hour: int) -> None:
    # Hosted, the digest job is hourly and reads each tenant's own weekday and
    # hour when it runs, so there is nothing here to reschedule.
    if settings.multi_tenant:
        return
    if scheduler.get_job(_DIGEST_JOB_ID):
        scheduler.reschedule_job(
            _DIGEST_JOB_ID, trigger="cron", day_of_week=weekday, hour=hour, minute=0
        )


def job_next_run_times() -> dict[str, object]:
    """{job_id: next_run_time} — None means the job is paused and will not fire."""
    return {j.id: j.next_run_time for j in scheduler.get_jobs()}
