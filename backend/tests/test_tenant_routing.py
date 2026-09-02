"""Working out whose request this is, without an edge in front.

The panel now answers the internet directly, so it resolves the tenant from
the request itself. The rule is that the *credential* decides: a session
cookie and an agent key each name the tenant they were minted for, and the
header is only for internal callers that hold neither.

The ordering is the point. If the header won, a valid session for one tenant
could be aimed at another — it would fail there, since the token is not in
that database, but "cannot be aimed" is a better property than "fails closed"
when it costs nothing.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app import database
from app.api import api_router
from app.config import settings
from app.services import auth
from app.tenancy import TenantMiddleware, current_tenant

KEY = "test-provision-key"
R = "x" * 43


@pytest_asyncio.fixture
async def hosted(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "multi_tenant", True)
    monkeypatch.setattr(settings, "tenants_dir", str(tmp_path / "tenants"))
    monkeypatch.setattr(settings, "provision_key", KEY)
    yield tmp_path / "tenants"
    await database.dispose_tenants()


@pytest_asyncio.fixture
async def client():
    app = FastAPI()
    app.add_middleware(TenantMiddleware)
    app.include_router(api_router)

    @app.get("/whoami")
    async def whoami():
        return {"tenant": current_tenant.get()}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://panel") as c:
        yield c


async def _tenant_with_owner(client, tenant_id: str) -> None:
    r = await client.post(
        "/api/tenants",
        json={"tenant_id": tenant_id, "username": "owner", "password": "correct horse"},
        headers={settings.provision_header: KEY},
    )
    assert r.status_code == 201, r.text


# ── the credential decides ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_session_cookie_names_its_own_tenant(hosted, client):
    r = await client.get("/whoami", headers={"cookie": f"cherubyte_session=t.alpha.{R}"})
    assert r.json() == {"tenant": "alpha"}


@pytest.mark.asyncio
async def test_an_agent_key_names_its_own_tenant(hosted, client):
    r = await client.get("/whoami", headers={"authorization": f"Bearer t.beta.{R}"})
    assert r.json() == {"tenant": "beta"}


@pytest.mark.asyncio
async def test_a_cookie_cannot_be_aimed_at_another_tenant(hosted, client):
    # The header says beta; the cookie was minted for alpha. Alpha wins.
    r = await client.get(
        "/whoami",
        headers={"cookie": f"cherubyte_session=t.alpha.{R}", settings.tenant_header: "beta"},
    )
    assert r.json() == {"tenant": "alpha"}


@pytest.mark.asyncio
async def test_a_key_cannot_be_aimed_at_another_tenant(hosted, client):
    r = await client.get(
        "/whoami",
        headers={"authorization": f"Bearer t.alpha.{R}", settings.tenant_header: "beta"},
    )
    assert r.json() == {"tenant": "alpha"}


@pytest.mark.asyncio
async def test_the_header_is_used_when_there_is_no_credential(hosted, client):
    # The login window asking a specific tenant a question, and provisioning.
    r = await client.get("/whoami", headers={settings.tenant_header: "alpha"})
    assert r.json() == {"tenant": "alpha"}


@pytest.mark.asyncio
async def test_an_unprefixed_credential_falls_through_to_the_header(hosted, client):
    # A self-hosted panel's tokens have no prefix. If one is presented here it
    # names nobody, and the request is resolved as if it carried none.
    r = await client.get(
        "/whoami",
        headers={"cookie": f"cherubyte_session={R}", settings.tenant_header: "alpha"},
    )
    assert r.json() == {"tenant": "alpha"}


@pytest.mark.asyncio
async def test_nothing_at_all_is_no_tenant(hosted, client):
    assert (await client.get("/whoami")).json() == {"tenant": None}
    assert (await client.get("/whoami", headers={settings.tenant_header: "../etc"})).json() == {
        "tenant": None
    }


# ── minting a session ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_minted_session_logs_straight_in(hosted, client):
    await _tenant_with_owner(client, "alpha")

    minted = await client.post("/api/tenants/alpha/session", headers={settings.provision_header: KEY})
    assert minted.status_code == 201, minted.text
    body = minted.json()
    assert body["username"] == "owner"
    assert body["token"].startswith("t.alpha.")

    # The cookie alone, with no tenant header: it routes itself and it works.
    me = await client.get("/api/auth/status", headers={"cookie": f"cherubyte_session={body['token']}"})
    assert me.status_code == 200
    assert me.json()["account"]["username"] == "owner"


@pytest.mark.asyncio
async def test_a_minted_session_does_not_open_another_tenant(hosted, client):
    await _tenant_with_owner(client, "alpha")
    await _tenant_with_owner(client, "beta")
    token = (
        await client.post("/api/tenants/alpha/session", headers={settings.provision_header: KEY})
    ).json()["token"]

    # Aimed at beta, it resolves to alpha anyway — and even if it did not, the
    # token is not a row in beta's database.
    r = await client.get(
        "/api/auth/status",
        headers={"cookie": f"cherubyte_session={token}", settings.tenant_header: "beta"},
    )
    assert r.json()["account"]["username"] == "owner"
    forged = token.replace("t.alpha.", "t.beta.", 1)
    r = await client.get("/api/auth/status", headers={"cookie": f"cherubyte_session={forged}"})
    assert r.json()["account"] is None


@pytest.mark.asyncio
async def test_minting_is_guarded_exactly_like_provisioning(hosted, client):
    await _tenant_with_owner(client, "alpha")
    for headers in ({}, {settings.provision_header: "wrong"}):
        r = await client.post("/api/tenants/alpha/session", headers=headers)
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_minting_an_unknown_tenant_is_refused(hosted, client):
    r = await client.post("/api/tenants/ghost/session", headers={settings.provision_header: KEY})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_minting_does_not_exist_when_self_hosted(client):
    assert settings.multi_tenant is False
    r = await client.post("/api/tenants/alpha/session", headers={settings.provision_header: KEY})
    assert r.status_code == 404


def test_a_self_hosted_session_token_carries_no_prefix():
    assert current_tenant.get() is None
    token = auth.new_session_token()
    assert "." not in token
    assert len(token) == 64


# ── a stranded browser is sent to log in ───────────────────────────────────


@pytest.mark.asyncio
async def test_a_browser_with_no_session_is_sent_to_the_login_window(hosted, client):
    # Without this the SPA is stranded after a sign-out: it holds a screen of
    # stale data and never navigates, because every call it makes is a 401.
    r = await client.get("/", headers={"accept": "text/html"})
    assert r.status_code == 302
    assert r.headers["location"] == "/login"
    assert r.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_an_api_call_with_no_session_still_gets_json(hosted, client):
    # Only a document navigation moves. The SPA's own calls must keep getting
    # a status it can act on rather than a redirect it would follow blindly.
    r = await client.get("/api/auth/status", headers={"accept": "application/json"})
    assert r.status_code == 401
    r = await client.get("/api/auth/status", headers={"accept": "text/html"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_a_browser_with_a_session_is_not_redirected(hosted, client):
    await _tenant_with_owner(client, "alpha")
    token = (
        await client.post("/api/tenants/alpha/session", headers={settings.provision_header: KEY})
    ).json()["token"]
    r = await client.get(
        "/", headers={"accept": "text/html", "cookie": f"cherubyte_session={token}"}
    )
    assert r.status_code != 302


@pytest.mark.asyncio
async def test_static_assets_are_never_redirected(hosted, client):
    # A redirect served in place of a stylesheet is a broken page rather than
    # a login prompt.
    for path in ("/assets/index.css", "/uploads/photo.png"):
        r = await client.get(path, headers={"accept": "text/html"})
        assert r.status_code != 302



# ── the ops endpoints ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_listing_tenants_reports_enough_to_spot_a_broken_one(hosted, client):
    await _tenant_with_owner(client, "alpha")
    await _tenant_with_owner(client, "beta")

    r = await client.get("/api/tenants", headers={settings.provision_header: KEY})
    assert r.status_code == 200
    rows = {t["tenant_id"]: t for t in r.json()["tenants"]}
    assert set(rows) == {"alpha", "beta"}
    for row in rows.values():
        assert row["devices"] == 0
        assert row["agents"] == 0
        assert row["last_report"] is None
        assert row["bytes"] > 0


@pytest.mark.asyncio
async def test_revoking_sessions_signs_a_tenant_out_everywhere(hosted, client):
    await _tenant_with_owner(client, "alpha")
    token = (
        await client.post("/api/tenants/alpha/session", headers={settings.provision_header: KEY})
    ).json()["token"]
    cookie = {"cookie": f"cherubyte_session={token}"}
    assert (await client.get("/api/auth/status", headers=cookie)).json()["account"] is not None

    r = await client.request("DELETE", "/api/tenants/alpha/sessions", headers={settings.provision_header: KEY})
    assert r.status_code == 200 and r.json()["revoked"] == 1

    # The cookie still routes — it names its tenant — but it opens nothing.
    assert (await client.get("/api/auth/status", headers=cookie)).json()["account"] is None


@pytest.mark.asyncio
async def test_revoking_one_tenant_does_not_sign_out_another(hosted, client):
    await _tenant_with_owner(client, "alpha")
    await _tenant_with_owner(client, "beta")
    beta = (
        await client.post("/api/tenants/beta/session", headers={settings.provision_header: KEY})
    ).json()["token"]

    await client.request("DELETE", "/api/tenants/alpha/sessions", headers={settings.provision_header: KEY})
    r = await client.get("/api/auth/status", headers={"cookie": f"cherubyte_session={beta}"})
    assert r.json()["account"] is not None


@pytest.mark.asyncio
async def test_deleting_a_tenant_removes_the_database_and_its_sidecars(hosted, client):
    await _tenant_with_owner(client, "alpha")
    await _tenant_with_owner(client, "beta")
    assert (hosted / "alpha.db").is_file()

    r = await client.request("DELETE", "/api/tenants/alpha", headers={settings.provision_header: KEY})
    assert r.status_code == 200 and r.json()["deleted"] == "alpha"

    # A .db-wal left behind is data the next tenant with this id would inherit.
    for suffix in ("", "-wal", "-shm"):
        assert not (hosted / f"alpha.db{suffix}").exists()
    assert (hosted / "beta.db").is_file()  # untouched


@pytest.mark.asyncio
async def test_the_ops_endpoints_are_guarded_and_do_not_exist_self_hosted(hosted, client):
    await _tenant_with_owner(client, "alpha")
    for method, path in (
        ("GET", "/api/tenants"),
        ("DELETE", "/api/tenants/alpha/sessions"),
        ("DELETE", "/api/tenants/alpha"),
    ):
        r = await client.request(method, path)
        assert r.status_code == 403, (method, path)
        r = await client.request(method, path, headers={settings.provision_header: "wrong"})
        assert r.status_code == 403, (method, path)
    # And the tenant survived every refusal.
    assert (hosted / "alpha.db").is_file()


@pytest.mark.asyncio
async def test_deleting_an_unknown_tenant_is_refused(hosted, client):
    r = await client.request("DELETE", "/api/tenants/ghost", headers={settings.provision_header: KEY})
    assert r.status_code == 404
