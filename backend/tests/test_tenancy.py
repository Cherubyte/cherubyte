"""Tenant resolution and isolation.

What is worth pinning here is not that two databases can exist — SQLite does
that — but the refusals: no tenant, an unknown tenant, a malformed id, and the
single-tenant entry point being called in multi-tenant mode. Each of those is
a way one customer's data could be read by another, and each has to end in a
refusal rather than in somewhere shared.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import database
from app.config import settings
from app.tenancy import TenantMiddleware, current_tenant, validate_tenant_id


@pytest_asyncio.fixture
async def multi_tenant(tmp_path, monkeypatch):
    """Multi-tenant mode with a scratch tenants directory. The module-level
    engine is left alone: single-tenant tests still run against it."""
    monkeypatch.setattr(settings, "multi_tenant", True)
    monkeypatch.setattr(settings, "tenants_dir", str(tmp_path / "tenants"))
    monkeypatch.setattr(settings, "tenant_engine_cache", 32)
    yield tmp_path / "tenants"
    await database.dispose_tenants()


async def _tables(tenant_id: str) -> set[str]:
    session = await database.session_for(tenant_id)
    async with session:
        rows = await session.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        return {r[0] for r in rows}


# ── the id is a path segment ───────────────────────────────────────────────


@pytest.mark.parametrize("good", ["abc", "tenant-1", "a_b_c", "x" * 64, "0zero"])
def test_accepts_a_safe_tenant_id(good):
    assert validate_tenant_id(good) == good


@pytest.mark.parametrize(
    "bad",
    ["", "ab", "../etc", "a/b", "a\\b", "x.db", "a b", "Upper", "x" * 65, "-lead", None, 42],
)
def test_refuses_anything_that_is_not_one_path_segment(bad):
    # The id becomes `tenants_dir/<id>.db`. Traversal, separators, a dot that
    # could change the extension, or an object that is not a string at all —
    # none of them gets near a filesystem.
    with pytest.raises(ValueError):
        validate_tenant_id(bad)


# ── two tenants, two files, no crosstalk ───────────────────────────────────


@pytest.mark.asyncio
async def test_each_tenant_gets_its_own_database(multi_tenant):
    await database.provision_tenant("alpha")
    await database.provision_tenant("beta")

    assert (multi_tenant / "alpha.db").is_file()
    assert (multi_tenant / "beta.db").is_file()
    assert "devices" in await _tables("alpha")
    assert "devices" in await _tables("beta")

    # Something only alpha has. If it shows up in beta, the two sessions were
    # on the same file after all, and everything above this test is moot.
    session = await database.session_for("alpha")
    async with session:
        await session.execute(text("CREATE TABLE only_alpha (x INTEGER)"))
        await session.commit()

    assert "only_alpha" in await _tables("alpha")
    assert "only_alpha" not in await _tables("beta")


@pytest.mark.asyncio
async def test_provisioning_twice_is_harmless(multi_tenant):
    first = await database.provision_tenant("alpha")
    second = await database.provision_tenant("alpha")
    assert first == second
    assert "devices" in await _tables("alpha")


# ── the refusals ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_request_with_no_tenant_is_refused(multi_tenant):
    assert current_tenant.get() is None
    with pytest.raises(HTTPException) as exc:
        async for _ in database.get_session():
            pass
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_an_unknown_tenant_is_refused_and_leaves_no_file(multi_tenant):
    token = current_tenant.set("ghost")
    try:
        with pytest.raises(HTTPException) as exc:
            async for _ in database.get_session():
                pass
    finally:
        current_tenant.reset(token)
    assert exc.value.status_code == 404
    # Refusing is not enough on its own: SQLite creates a file on first
    # connect, and an empty database left behind here would be found by the
    # next request and treated as a real tenant.
    assert not (multi_tenant / "ghost.db").exists()


@pytest.mark.asyncio
async def test_a_provisioned_tenant_is_served(multi_tenant):
    await database.provision_tenant("alpha")
    token = current_tenant.set("alpha")
    try:
        async for session in database.get_session():
            rows = await session.execute(text("SELECT count(*) FROM devices"))
            assert rows.scalar() == 0
    finally:
        current_tenant.reset(token)


@pytest.mark.asyncio
async def test_session_local_refuses_in_multi_tenant_mode(multi_tenant):
    # Every job and service that still calls SessionLocal() bare has to fail
    # here, loudly, rather than open a database that belongs to nobody.
    with pytest.raises(RuntimeError, match="session_for"):
        database.SessionLocal()


# ── single-tenant is untouched ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_single_tenant_serves_the_default_database():
    assert settings.multi_tenant is False
    token = current_tenant.set("alpha")  # must be ignored entirely
    try:
        async for session in database.get_session():
            assert session.bind is database.engine
    finally:
        current_tenant.reset(token)


def test_single_tenant_app_does_not_install_the_middleware():
    from app.main import app

    assert not any(m.cls is TenantMiddleware for m in app.user_middleware)


# ── the engine cache is bounded ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_engine_cache_evicts_least_recently_used(multi_tenant, monkeypatch):
    monkeypatch.setattr(settings, "tenant_engine_cache", 2)
    for tid in ("aaa", "bbb", "ccc"):
        await database.provision_tenant(tid)

    # ccc was opened last, so aaa is the one that goes.
    assert len(database._tenants) == 2
    assert "aaa" not in database._tenants
    assert "bbb" in database._tenants and "ccc" in database._tenants

    # And it comes straight back on demand, from the file that never went away.
    assert "devices" in await _tables("aaa")
    assert "aaa" in database._tenants
    assert "bbb" not in database._tenants


# ── the middleware ─────────────────────────────────────────────────────────


def _app_with_middleware() -> TestClient:
    app = FastAPI()
    app.add_middleware(TenantMiddleware)

    @app.get("/whoami")
    async def whoami():
        return {"tenant": current_tenant.get()}

    return TestClient(app)


def test_middleware_reads_the_tenant_header():
    client = _app_with_middleware()
    r = client.get("/whoami", headers={settings.tenant_header: "alpha"})
    assert r.json() == {"tenant": "alpha"}


def test_middleware_treats_a_malformed_header_as_no_tenant():
    client = _app_with_middleware()
    r = client.get("/whoami", headers={settings.tenant_header: "../etc"})
    assert r.json() == {"tenant": None}


def test_middleware_leaves_no_tenant_behind_between_requests():
    client = _app_with_middleware()
    client.get("/whoami", headers={settings.tenant_header: "alpha"})
    r = client.get("/whoami")
    assert r.json() == {"tenant": None}
