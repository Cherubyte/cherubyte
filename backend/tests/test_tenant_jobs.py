"""Background work, per tenant.

Two things would be silent if they broke, and both are here. Settings are
loaded from the database at runtime onto a shared object, so without an
overlay one tenant's retention, quiet hours and notification targets become
everybody's. And "when did an agent last report" was process-global, so one
tenant's report showed as every other tenant's last scan.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select

from app import database, scheduler
from app.config import settings
from app.models import Device, Setting
from app.tenancy import current_tenant


@pytest_asyncio.fixture
async def two_tenants(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "multi_tenant", True)
    monkeypatch.setattr(settings, "tenants_dir", str(tmp_path / "tenants"))
    for tid in ("alpha", "beta"):
        await database.provision_tenant(tid)
        scheduler.forget_tenant_state(tid)
    yield
    for tid in ("alpha", "beta"):
        scheduler.forget_tenant_state(tid)
    await database.dispose_tenants()


async def _set(tenant_id: str, key: str, value: str) -> None:
    async with database.scoped_to(tenant_id) as session:
        session.add(Setting(key=key, value=value))
        await session.commit()


# ── settings do not leak ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_each_tenant_reads_its_own_settings(two_tenants):
    await _set("alpha", "retention_days", "7")
    await _set("beta", "retention_days", "365")

    async with database.scoped_to("alpha"):
        assert settings.retention_days == 7
    async with database.scoped_to("beta"):
        assert settings.retention_days == 365
    # And back outside, the process-wide value is untouched by either.
    assert settings.retention_days == 90


@pytest.mark.asyncio
async def test_a_tenants_notification_targets_stay_its_own(two_tenants):
    # The leak that would matter most: alpha's chat id must never become the
    # place beta's alerts are sent.
    await _set("alpha", "telegram_chat_id", "alpha-chat")

    async with database.scoped_to("alpha"):
        assert settings.telegram_chat_id == "alpha-chat"
    async with database.scoped_to("beta"):
        assert settings.telegram_chat_id == ""
    assert settings.telegram_chat_id == ""


@pytest.mark.asyncio
async def test_the_overlay_is_dropped_even_if_the_block_raises(two_tenants):
    await _set("alpha", "retention_days", "7")
    with pytest.raises(RuntimeError):
        async with database.scoped_to("alpha"):
            assert settings.retention_days == 7
            raise RuntimeError("boom")
    assert settings.retention_days == 90
    assert current_tenant.get() is None


# ── the database in scope is the tenant's ──────────────────────────────────


@pytest.mark.asyncio
async def test_scoped_to_opens_that_tenants_database(two_tenants):
    async with database.scoped_to("alpha") as session:
        session.add(Device(name="alpha's laptop"))
        await session.commit()

    async with database.scoped_to("alpha") as session:
        assert len((await session.execute(select(Device))).scalars().all()) == 1
    async with database.scoped_to("beta") as session:
        assert len((await session.execute(select(Device))).scalars().all()) == 0


@pytest.mark.asyncio
async def test_open_session_refuses_outside_a_tenant(two_tenants):
    with pytest.raises(RuntimeError, match="scoped_to"):
        async with database.open_session():
            pass


# ── the tenant registry is the files ───────────────────────────────────────


@pytest.mark.asyncio
async def test_known_tenants_reads_the_directory(two_tenants, tmp_path):
    assert database.known_tenants() == ["alpha", "beta"]
    # Something that is not a tenant database does not become one.
    (tmp_path / "tenants" / "notes.txt").write_text("hello")
    (tmp_path / "tenants" / "Bad Name.db").write_text("")
    assert database.known_tenants() == ["alpha", "beta"]


def test_known_tenants_is_empty_before_anything_is_provisioned(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "multi_tenant", True)
    monkeypatch.setattr(settings, "tenants_dir", str(tmp_path / "nothing-here"))
    assert database.known_tenants() == []


# ── a job runs for everyone, and survives one of them failing ──────────────


@pytest.mark.asyncio
async def test_a_job_runs_once_per_tenant(two_tenants):
    seen: list[str] = []

    async def job():
        seen.append(current_tenant.get() or "?")

    await scheduler._for_each_tenant("test", job)
    assert seen == ["alpha", "beta"]


@pytest.mark.asyncio
async def test_one_tenants_failure_does_not_stop_the_others(two_tenants):
    seen: list[str] = []

    async def job():
        tenant = current_tenant.get()
        seen.append(tenant or "?")
        if tenant == "alpha":
            raise RuntimeError("this tenant is having a bad day")

    await scheduler._for_each_tenant("test", job)  # must not raise
    assert seen == ["alpha", "beta"]


# ── last scan is one tenant's answer ───────────────────────────────────────


@pytest.mark.asyncio
async def test_last_scan_is_per_tenant(two_tenants):
    async with database.scoped_to("alpha"):
        scheduler.note_report()
        alpha_seen = scheduler.last_scan()

    assert alpha_seen is not None
    # Beta's dashboard must not show alpha's agent as its own last scan.
    async with database.scoped_to("beta"):
        assert scheduler.last_scan() is None


def test_last_scan_is_shared_state_when_self_hosted():
    assert settings.multi_tenant is False
    scheduler._state.pop(None, None)
    assert scheduler.last_scan() is None
    scheduler.note_report()
    assert scheduler.last_scan() is not None
    scheduler._state.pop(None, None)
