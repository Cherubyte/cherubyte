"""Version check + self-update for the "Update" settings page."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main
from app.services import update


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setitem(update._status, "latest", None)
    monkeypatch.setitem(update._status, "checked_at", None)
    monkeypatch.setitem(update._status, "error", None)
    monkeypatch.setitem(update._apply, "status", "idle")
    monkeypatch.setitem(update._apply, "log", [])
    monkeypatch.setitem(update._apply, "error", None)


def _mock_get(monkeypatch, *, status_code: int = 200, payload: dict | None = None):
    class Resp:
        def __init__(self):
            self.status_code = status_code

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError("boom", request=None, response=self)

        def json(self):
            return payload or {}

    async def fake_get(self, url, **kwargs):
        return Resp()

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)


# --------------------------------------------------------------- version compare

@pytest.mark.parametrize(
    "latest,current,expected",
    [
        ("0.15.0", "0.14.1", True),
        ("v0.15.0", "0.14.1", True),
        ("0.14.1", "0.14.1", False),
        ("0.14.0", "0.14.1", False),
        ("1.0.0", "0.99.9", True),
        ("0.14.10", "0.14.9", True),
    ],
)
def test_version_comparison(latest, current, expected):
    assert update.is_newer(latest, current) is expected


def test_unparsable_segments_do_not_raise():
    assert update.is_newer("nightly", "0.14.1") is False


# --------------------------------------------------------------------- check()

async def test_check_records_the_latest_version(monkeypatch):
    _mock_get(monkeypatch, payload={"version": "9.9.9"})
    out = await update.check()
    assert out["latest"] == "9.9.9"
    assert out["error"] is None
    assert out["checked_at"] is not None


async def test_a_failed_check_keeps_the_last_good_state(monkeypatch):
    _mock_get(monkeypatch, payload={"version": "9.9.9"})
    await update.check()

    _mock_get(monkeypatch, status_code=500)
    out = await update.check()
    assert out["latest"] == "9.9.9", "a failed re-check must not blank out the last result"
    assert out["error"]


# ---------------------------------------------------------------- deploy_mode()

def test_deploy_mode_is_container_without_a_git_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(update, "ROOT", tmp_path)
    assert update.deploy_mode() == "container"


def test_deploy_mode_is_git_with_a_git_dir(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(update, "ROOT", tmp_path)
    assert update.deploy_mode() == "git"


async def test_apply_refuses_outside_a_git_checkout(tmp_path, monkeypatch):
    monkeypatch.setattr(update, "ROOT", tmp_path)
    with pytest.raises(RuntimeError):
        await update.apply()


# --------------------------------------------------------------------- the API

@pytest.fixture
def client():
    return TestClient(main.app)


def _admin(client):
    client.post("/api/auth/setup", json={"username": "admin", "password": "hunter2!!"})


def test_get_update_needs_no_admin(session, client, monkeypatch):
    _admin(client)
    r = client.get("/api/settings/update")
    assert r.status_code == 200
    body = r.json()
    assert body["current"] == update.APP_VERSION
    assert "deploy_mode" in body and "update_available" in body


def test_check_and_apply_are_admin_only(session, client, monkeypatch):
    _admin(client)
    client.post(
        "/api/auth/accounts",
        json={"username": "vic", "password": "hunter2!!", "role": "viewer"},
    )
    viewer = TestClient(main.app)
    viewer.post("/api/auth/login", json={"username": "vic", "password": "hunter2!!"})
    assert viewer.post("/api/settings/update/check").status_code == 403
    assert viewer.post("/api/settings/update/apply").status_code == 403


def test_apply_without_a_check_first_is_rejected(session, client):
    _admin(client)
    assert client.post("/api/settings/update/apply").status_code == 400


def test_apply_in_a_container_deployment_is_rejected(session, client, monkeypatch, tmp_path):
    _admin(client)
    monkeypatch.setitem(update._status, "latest", "99.0.0")
    monkeypatch.setattr(update, "ROOT", tmp_path)  # no .git -> "container"
    r = client.post("/api/settings/update/apply")
    assert r.status_code == 409
    assert "container" in r.json()["detail"].lower()


def test_check_endpoint_reaches_the_service(session, client, monkeypatch):
    _admin(client)
    _mock_get(monkeypatch, payload={"version": "42.0.0"})
    r = client.post("/api/settings/update/check")
    assert r.status_code == 200
    body = r.json()
    assert body["latest"] == "42.0.0"
    assert body["update_available"] is True
