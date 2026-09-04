"""The panel's half of a blue/green rollout.

Two properties, and the second one exists because the first will eventually
be got wrong.

A tenant's schema is upgraded the first time *this* process opens it, not for
everybody at boot. Boot-time was right for one process and wrong for two: the
new version would upgrade tenants the old one is still serving, and the old
code would then be running against a schema it does not know.

And a request that reaches the wrong process is refused. The router is what
keeps one tenant on one version; this is what catches the router being wrong,
because the alternative symptom is two schema versions writing one SQLite
file, which is not an error message — it is a corrupted database.
"""

from __future__ import annotations

import sqlite3

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app import database
from app.config import settings
from app.tenancy import TenantMiddleware


@pytest_asyncio.fixture
async def hosted(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "multi_tenant", True)
    monkeypatch.setattr(settings, "tenants_dir", str(tmp_path / "tenants"))
    for tid in ("alpha", "beta"):
        await database.provision_tenant(tid)
    yield
    await database.dispose_tenants()


def _rewind(tenant: str) -> None:
    """Put one tenant back at an older revision, with the column gone.

    What a tenant looks like when it has been served only by the old process
    and is now about to arrive at the new one.
    """
    con = sqlite3.connect(database.tenant_db_path(tenant))
    try:
        con.execute("DROP INDEX IF EXISTS ix_mac_addresses_address_bi")
        con.execute("ALTER TABLE mac_addresses DROP COLUMN address_bi")
        con.execute("UPDATE alembic_version SET version_num = 'baseline'")
        con.commit()
    finally:
        con.close()


def _columns(tenant: str, table: str) -> set[str]:
    con = sqlite3.connect(database.tenant_db_path(tenant))
    try:
        return {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
    finally:
        con.close()


# -- upgrading on arrival ----------------------------------------------------


@pytest.mark.asyncio
async def test_a_tenant_is_upgraded_the_first_time_this_process_opens_it(hosted):
    _rewind("alpha")
    database._upgraded.discard("alpha")
    await database.close_tenant("alpha")
    assert "address_bi" not in _columns("alpha", "mac_addresses")

    async with database.scoped_to("alpha") as session:
        await session.execute(text("SELECT 1"))

    assert "address_bi" in _columns("alpha", "mac_addresses")


@pytest.mark.asyncio
async def test_a_tenant_this_process_never_touches_is_left_alone(hosted):
    # The property the boot sweep broke. Beta belongs to the other process
    # until the router moves it, and this one must not migrate it underneath.
    _rewind("beta")
    database._upgraded.discard("beta")
    await database.close_tenant("beta")

    async with database.scoped_to("alpha") as session:
        await session.execute(text("SELECT 1"))

    assert "address_bi" not in _columns("beta", "mac_addresses")


@pytest.mark.asyncio
async def test_the_upgrade_happens_once_however_many_requests_arrive(hosted):
    import asyncio

    calls: list[str] = []
    real = database.init_db

    async def counting(target=None):
        calls.append("x")
        await real(target)

    database.init_db = counting
    try:
        database._upgraded.discard("alpha")
        # Two requests arriving together for a tenant this process has not
        # seen must run one migration, not two.
        await asyncio.gather(
            database.ensure_schema("alpha"),
            database.ensure_schema("alpha"),
            database.ensure_schema("alpha"),
        )
    finally:
        database.init_db = real
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_one_tenant_that_will_not_upgrade_is_not_an_outage(hosted):
    # It was a sweep at boot, so one unreadable file could have taken down
    # the whole process. Per-tenant, the blast radius is that tenant: their
    # requests fail and everybody else is served.
    real = database.init_db

    async def only_alpha_is_broken(target=None):
        if target is not None and "alpha" in str(target.url):
            raise RuntimeError("disk is on fire")
        await real(target)

    database.init_db = only_alpha_is_broken
    try:
        database._upgraded.discard("alpha")
        database._upgraded.discard("beta")
        with pytest.raises(RuntimeError, match="on fire"):
            async with database.scoped_to("alpha") as session:
                await session.execute(text("SELECT 1"))

        async with database.scoped_to("beta") as session:
            assert (await session.execute(text("SELECT 1"))).scalar() == 1
    finally:
        database.init_db = real


@pytest.mark.asyncio
async def test_forgetting_a_tenant_forgets_that_it_was_checked(hosted):
    # Otherwise a tenant deleted and re-provisioned under the same id inherits
    # the answer from before it existed.
    await database.scoped_to("alpha").__aenter__()
    assert "alpha" in database._upgraded
    await database.discard_tenant("alpha")
    assert "alpha" not in database._upgraded


# -- refusing a misrouted request -------------------------------------------


@pytest_asyncio.fixture
async def client():
    app = FastAPI()
    app.add_middleware(TenantMiddleware)

    @app.get("/api/ping")
    async def ping():
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://panel") as c:
        yield c


@pytest.mark.asyncio
async def test_a_request_meant_for_the_other_process_is_refused(client, monkeypatch):
    monkeypatch.setattr(settings, "multi_tenant", True)
    monkeypatch.setattr(settings, "upstream_name", "green")

    r = await client.get(
        "/api/ping",
        headers={settings.upstream_header: "blue", settings.tenant_header: "alpha"},
    )
    assert r.status_code == 421
    assert b"Misdirected" in r.content


@pytest.mark.asyncio
async def test_a_request_meant_for_this_process_is_served(client, monkeypatch):
    monkeypatch.setattr(settings, "multi_tenant", True)
    monkeypatch.setattr(settings, "upstream_name", "green")

    r = await client.get(
        "/api/ping",
        headers={settings.upstream_header: "green", settings.tenant_header: "alpha"},
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_an_unnamed_process_serves_whatever_arrives(client, monkeypatch):
    # Every single-process install, which is the normal case and must not
    # start refusing requests because a header happens to be present.
    monkeypatch.setattr(settings, "multi_tenant", True)
    monkeypatch.setattr(settings, "upstream_name", "")

    r = await client.get(
        "/api/ping",
        headers={settings.upstream_header: "blue", settings.tenant_header: "alpha"},
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_a_named_process_still_serves_a_request_with_no_routing_header(
    client, monkeypatch
):
    # A health check, or anything reaching the process directly rather than
    # through the router. Refusing these would make the process unmonitorable.
    monkeypatch.setattr(settings, "multi_tenant", True)
    monkeypatch.setattr(settings, "upstream_name", "green")

    r = await client.get("/api/ping", headers={settings.tenant_header: "alpha"})
    assert r.status_code == 200
