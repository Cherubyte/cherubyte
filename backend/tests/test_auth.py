"""Login, roles, and first-run setup.

Every /api route except the auth flow and the signed-token action endpoints
now needs a session cookie; writes need at least an `editor`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main
from app.services import auth


@pytest.fixture
def client(session):
    auth._failures.clear()
    return TestClient(main.app)


def _setup_admin(client: TestClient) -> TestClient:
    r = client.post("/api/auth/setup", json={"username": "admin", "password": "hunter2!!"})
    assert r.status_code == 201
    return client


# --- setup ---------------------------------------------------------------

def test_status_asks_for_setup_when_there_are_no_accounts(client):
    r = client.get("/api/auth/status")
    assert r.status_code == 200
    assert r.json() == {"setup_required": True, "account": None}


def test_setup_creates_the_first_admin_and_logs_in(client):
    r = client.post("/api/auth/setup", json={"username": "Admin", "password": "hunter2!!"})
    assert r.status_code == 201
    assert r.json()["role"] == "admin"
    assert auth.COOKIE_NAME in r.cookies
    assert client.get("/api/auth/status").json()["account"]["username"] == "admin"


def test_setup_is_refused_once_an_account_exists(client):
    _setup_admin(client)
    r = client.post("/api/auth/setup", json={"username": "x", "password": "hunter2!!"})
    assert r.status_code == 409


# --- login / access -----------------------------------------------------

def test_api_is_closed_without_a_session(client):
    _setup_admin(client)
    fresh = TestClient(main.app)
    assert fresh.get("/api/devices").status_code == 401


def test_login_rejects_a_bad_password(client):
    _setup_admin(client)
    fresh = TestClient(main.app)
    assert fresh.post(
        "/api/auth/login", json={"username": "admin", "password": "nope"}
    ).status_code == 401


def test_login_opens_the_api(client):
    _setup_admin(client)
    fresh = TestClient(main.app)
    fresh.post("/api/auth/login", json={"username": "admin", "password": "hunter2!!"})
    assert fresh.get("/api/devices").status_code == 200


def test_logout_invalidates_the_session(client):
    _setup_admin(client)
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/devices").status_code == 401


# --- roles -------------------------------------------------------------

def _make(client: TestClient, username: str, role: str) -> None:
    r = client.post(
        "/api/auth/accounts",
        json={"username": username, "password": "hunter2!!", "role": role},
    )
    assert r.status_code == 201


def _as(username: str) -> TestClient:
    c = TestClient(main.app)
    c.post("/api/auth/login", json={"username": username, "password": "hunter2!!"})
    return c


def test_a_viewer_cannot_write(client):
    _setup_admin(client)
    _make(client, "vic", "viewer")
    viewer = _as("vic")
    assert viewer.get("/api/devices").status_code == 200
    assert viewer.patch("/api/devices/1", json={"name": "x"}).status_code == 403


def test_an_editor_can_write_but_not_manage_accounts(client):
    _setup_admin(client)
    _make(client, "ed", "editor")
    editor = _as("ed")
    # 404 (no such device) proves the write guard passed
    assert editor.patch("/api/devices/999", json={"name": "x"}).status_code == 404
    assert editor.get("/api/auth/accounts").status_code == 403


def test_only_an_admin_manages_accounts(client):
    _setup_admin(client)
    assert client.get("/api/auth/accounts").status_code == 200


def test_the_last_admin_cannot_be_demoted(client):
    _setup_admin(client)
    me = client.get("/api/auth/status").json()["account"]["id"]
    assert client.patch(f"/api/auth/accounts/{me}", json={"role": "viewer"}).status_code == 409


# --- editing your own account ----------------------------------------

def test_me_changes_username_and_password_with_the_current_password(client):
    _setup_admin(client)
    r = client.patch(
        "/api/auth/me",
        json={"current": "hunter2!!", "username": "boss", "new_password": "newpass!!"},
    )
    assert r.status_code == 200
    assert r.json()["username"] == "boss"
    fresh = TestClient(main.app)
    assert fresh.post(
        "/api/auth/login", json={"username": "boss", "password": "newpass!!"}
    ).status_code == 200


def test_me_rejects_a_wrong_current_password(client):
    _setup_admin(client)
    assert client.patch(
        "/api/auth/me", json={"current": "nope", "username": "boss"}
    ).status_code == 403


def test_me_refuses_a_username_already_taken(client):
    _setup_admin(client)
    _make(client, "taken", "viewer")
    assert client.patch(
        "/api/auth/me", json={"current": "hunter2!!", "username": "taken"}
    ).status_code == 409


# --- the signed-token action endpoints stay open -----------------------

def test_action_endpoints_do_not_require_a_session(client):
    _setup_admin(client)
    fresh = TestClient(main.app)
    # no token -> 403 from the token check, not 401 from the session guard
    assert fresh.post("/api/actions/approve/1").status_code == 403
