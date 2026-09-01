"""Provisioning a tenant, and the door it closes.

The panel's first run — whoever arrives first creates the admin — is right
for a box in a cupboard and catastrophic for a database that just became
reachable from the internet. These pin that in multi-tenant mode a tenant only
ever comes into being with its account, that the first-run door is gone even
for a database with no accounts in it, and that provisioning itself admits
nobody without the key.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app import database
from app.api import api_router, provisioning
from app.config import settings
from app.models import Account, AccountRole
from app.tenancy import TenantMiddleware

KEY = "test-provision-key"
BODY = {"tenant_id": "alpha", "username": "Owner", "password": "correct horse"}


@pytest_asyncio.fixture
async def hosted(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "multi_tenant", True)
    monkeypatch.setattr(settings, "tenants_dir", str(tmp_path / "tenants"))
    monkeypatch.setattr(settings, "provision_key", KEY)
    yield tmp_path / "tenants"
    await database.dispose_tenants()


@pytest_asyncio.fixture
async def client():
    # The real router behind the real middleware on a fresh app. main.app
    # decided at import time, with the flag off, not to install the
    # middleware, so it cannot stand in for the hosted configuration. An ASGI
    # transport keeps every request on this test's event loop.
    app = FastAPI()
    app.add_middleware(TenantMiddleware)
    app.include_router(api_router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://panel") as c:
        yield c


async def _accounts(tenant_id: str) -> list[Account]:
    session = await database.session_for(tenant_id)
    async with session:
        return list((await session.execute(select(Account))).scalars())


async def _count(tenant_id: str) -> int:
    session = await database.session_for(tenant_id)
    async with session:
        return int((await session.execute(select(func.count(Account.id)))).scalar_one())


# ── who may provision ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_route_does_not_exist_in_single_tenant_mode(client):
    assert settings.multi_tenant is False
    r = await client.post("/api/tenants", json=BODY, headers={settings.provision_header: KEY})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_no_key_configured_admits_nobody(hosted, client, monkeypatch):
    # The failure mode that matters: the secret was never set. That must
    # lock provisioning, never open it.
    monkeypatch.setattr(settings, "provision_key", "")
    r = await client.post("/api/tenants", json=BODY, headers={settings.provision_header: "anything"})
    assert r.status_code == 403
    assert not (hosted / "alpha.db").exists()


@pytest.mark.asyncio
async def test_a_wrong_key_is_refused(hosted, client):
    r = await client.post("/api/tenants", json=BODY, headers={settings.provision_header: "nope"})
    assert r.status_code == 403
    assert not (hosted / "alpha.db").exists()


@pytest.mark.asyncio
async def test_a_missing_key_is_refused(hosted, client):
    r = await client.post("/api/tenants", json=BODY)
    assert r.status_code == 403


# ── what provisioning produces ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_tenant_is_born_with_its_admin(hosted, client):
    r = await client.post("/api/tenants", json=BODY, headers={settings.provision_header: KEY})
    assert r.status_code == 201, r.text
    assert r.json() == {"tenant_id": "alpha", "username": "owner"}  # lower-cased, as login does

    assert (hosted / "alpha.db").is_file()
    accounts = await _accounts("alpha")
    assert [a.username for a in accounts] == ["owner"]
    assert accounts[0].role == AccountRole.admin
    assert "password" not in r.text


@pytest.mark.asyncio
async def test_the_seeded_admin_can_log_in(hosted, client):
    await client.post("/api/tenants", json=BODY, headers={settings.provision_header: KEY})
    r = await client.post(
        "/api/auth/login",
        json={"username": "owner", "password": "correct horse"},
        headers={settings.tenant_header: "alpha"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["username"] == "owner"


@pytest.mark.asyncio
async def test_a_tenant_cannot_be_provisioned_twice(hosted, client):
    first = await client.post("/api/tenants", json=BODY, headers={settings.provision_header: KEY})
    again = await client.post(
        "/api/tenants",
        json={**BODY, "username": "intruder", "password": "another one!"},
        headers={settings.provision_header: KEY},
    )
    assert first.status_code == 201
    assert again.status_code == 409
    assert await _count("alpha") == 1
    assert [a.username for a in await _accounts("alpha")] == ["owner"]


@pytest.mark.parametrize("bad_id", ["../etc", "a/b", "x.db", "Upper", "ab"])
@pytest.mark.asyncio
async def test_a_bad_tenant_id_never_reaches_the_filesystem(hosted, client, bad_id):
    r = await client.post(
        "/api/tenants", json={**BODY, "tenant_id": bad_id}, headers={settings.provision_header: KEY}
    )
    assert r.status_code == 422
    assert not hosted.exists() or not any(hosted.iterdir())


@pytest.mark.asyncio
async def test_a_short_password_is_refused_before_anything_is_created(hosted, client):
    r = await client.post(
        "/api/tenants", json={**BODY, "password": "short"}, headers={settings.provision_header: KEY}
    )
    assert r.status_code == 422
    assert not (hosted / "alpha.db").exists()


@pytest.mark.asyncio
async def test_a_failed_seed_leaves_no_database_behind(hosted, client, monkeypatch):
    # A database with no account is exactly the state the seed exists to
    # prevent, so a seed that fails has to take the database with it.
    async def boom(*_a, **_k):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(provisioning, "_seed_account", boom)
    r = await client.post("/api/tenants", json=BODY, headers={settings.provision_header: KEY})
    assert r.status_code == 500
    assert not (hosted / "alpha.db").exists()
    assert not (hosted / "alpha.db-wal").exists()
    assert "alpha" not in database._tenants


# ── the door that is closed ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_first_run_setup_is_gone_even_for_an_empty_tenant(hosted, client):
    # Provisioned without a seed, deliberately: zero accounts is the exact
    # state in which single-tenant setup would hand the panel to the first
    # visitor. Hosted, that door must not exist even then.
    await database.provision_tenant("bare")
    assert await _count("bare") == 0

    r = await client.post(
        "/api/auth/setup",
        json={"username": "intruder", "password": "correct horse"},
        headers={settings.tenant_header: "bare"},
    )
    assert r.status_code == 404
    assert await _count("bare") == 0


@pytest.mark.asyncio
async def test_a_provisioned_tenant_does_not_ask_for_setup(hosted, client):
    await client.post("/api/tenants", json=BODY, headers={settings.provision_header: KEY})
    r = await client.get("/api/auth/status", headers={settings.tenant_header: "alpha"})
    assert r.status_code == 200
    assert r.json()["setup_required"] is False
