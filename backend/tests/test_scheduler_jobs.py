"""Regression guard for the scheduler wiring.

The periodic scan was registered with `next_run_time=None`, which APScheduler
treats as *paused*: the job existed, showed up in the job list, and never fired.
The sweep only came alive if a settings save happened to call reschedule(), and
went back to sleep on the next restart. Assert every job is actually armed.
"""

import pytest
import pytest_asyncio

from app import scheduler as sched
from app.config import settings


@pytest_asyncio.fixture
async def started_scheduler():
    # AsyncIOScheduler binds to the running loop, so this fixture has to be async
    sched.start()
    yield sched
    sched.scheduler.shutdown(wait=False)


@pytest.mark.asyncio
async def test_every_job_is_armed(started_scheduler):
    next_runs = started_scheduler.job_next_run_times()

    assert next_runs, "the scheduler registered no jobs at all"
    paused = [job_id for job_id, when in next_runs.items() if when is None]
    assert not paused, f"jobs registered in a paused state and will never fire: {paused}"


@pytest.mark.asyncio
async def test_every_expected_job_is_registered(started_scheduler):
    assert set(started_scheduler.job_next_run_times()) == {
        "history-purge",
        "weekly-digest",
        "update-check",
        "host-temp-sample",
        "agent-health-check",
    }, "scanning and the WAN probe belong to the agent now, not to this scheduler"


@pytest.mark.asyncio
async def test_rescheduling_the_digest_keeps_it_armed(started_scheduler):
    started_scheduler.reschedule_digest(2, 8)
    assert started_scheduler.job_next_run_times()["weekly-digest"] is not None


@pytest_asyncio.fixture
async def hosted_scheduler(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "multi_tenant", True)
    monkeypatch.setattr(settings, "tenants_dir", str(tmp_path / "tenants"))
    sched.start()
    yield sched
    sched.scheduler.shutdown(wait=False)


@pytest.mark.asyncio
async def test_every_hosted_job_is_registered_and_armed(hosted_scheduler):
    """The hosted job set, asserted separately because it is a different branch.

    `agent-health-check` was added to the single-tenant path only, so hosted
    tenants got no "your agent went silent" alert at all — and nothing failed,
    because a job that is never registered raises nothing. Naming the whole
    set here is what makes the next such omission a test failure.
    """
    next_runs = hosted_scheduler.job_next_run_times()
    assert set(next_runs) == {
        "history-purge",
        "weekly-digest",
        "agent-health-check",
    }, "the update check and the panel's own temperature are about this machine, not a tenant"
    paused = [job_id for job_id, when in next_runs.items() if when is None]
    assert not paused, f"jobs registered in a paused state and will never fire: {paused}"
