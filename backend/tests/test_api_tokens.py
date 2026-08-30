"""Read-only API bearer tokens."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import main
from app.models import ApiToken


@pytest.fixture
def client(session):
    return TestClient(main.app)


def _admin(client: TestClient) -> TestClient:
    r = client.post("/api/auth/setup", json={"username": "admin", "password": "hunter2!!"})
    assert r.status_code == 201
    return client


def _mint(client: TestClient, name: str = "grafana") -> str:
    r = client.post("/api/auth/tokens", json={"name": name})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["token"].startswith("nsk_")
    return body["token"]


def test_only_admins_mint_tokens(client):
    _admin(client)
    client.post(
        "/api/auth/accounts",
        json={"username": "ed", "password": "hunter2!!", "role": "editor"},
    )
    editor = TestClient(main.app)
    editor.post("/api/auth/login", json={"username": "ed", "password": "hunter2!!"})
    assert editor.post("/api/auth/tokens", json={"name": "x"}).status_code == 403


def test_token_reads_but_never_writes(client):
    _admin(client)
    token = _mint(client)
    api = TestClient(main.app)  # no cookie
    h = {"Authorization": f"Bearer {token}"}

    assert api.get("/api/devices", headers=h).status_code == 200
    assert api.get("/api/stats", headers=h).status_code == 200
    # writes are refused exactly as they are for a read-only account
    assert api.patch("/api/devices/1", json={"name": "x"}, headers=h).status_code == 403
    assert api.post("/api/users", json={"name": "x"}, headers=h).status_code == 403


def test_token_cannot_reach_account_or_agent_management(client):
    _admin(client)
    token = _mint(client)
    api = TestClient(main.app)
    h = {"Authorization": f"Bearer {token}"}
    assert api.get("/api/auth/accounts", headers=h).status_code == 401
    assert api.get("/api/auth/tokens", headers=h).status_code == 401
    assert api.get("/api/agents", headers=h).status_code == 401


def test_a_bad_token_is_401(client):
    _admin(client)
    api = TestClient(main.app)
    assert api.get(
        "/api/devices", headers={"Authorization": "Bearer nsk_not-a-real-token"}
    ).status_code == 401


@pytest.mark.asyncio
async def test_only_the_hash_is_stored(client, session):
    _admin(client)
    token = _mint(client)
    rows = (await session.execute(select(ApiToken))).scalars().all()
    assert len(rows) == 1
    assert token not in rows[0].token_hash
    assert rows[0].token_hash != token


def test_revoking_a_token_stops_it(client):
    _admin(client)
    token = _mint(client)
    api = TestClient(main.app)
    h = {"Authorization": f"Bearer {token}"}
    assert api.get("/api/devices", headers=h).status_code == 200

    tid = client.get("/api/auth/tokens").json()[0]["id"]
    assert client.delete(f"/api/auth/tokens/{tid}").status_code == 204
    assert api.get("/api/devices", headers=h).status_code == 401


def test_metrics_accepts_an_api_token(client):
    _admin(client)
    token = _mint(client)
    api = TestClient(main.app)
    from app.config import settings

    settings.metrics_token = "prom-secret"
    try:
        assert api.get("/api/metrics").status_code == 401
        assert api.get(
            "/api/metrics", headers={"Authorization": f"Bearer {token}"}
        ).status_code == 200
    finally:
        settings.metrics_token = ""
