"""The onboarding-wizard dismissal flag — one shared setting, not per-account."""

import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture
def client(session):
    return TestClient(main.app)


def _admin(client: TestClient) -> TestClient:
    r = client.post("/api/auth/setup", json={"username": "admin", "password": "hunter2!!"})
    assert r.status_code == 201
    return client


def test_onboarding_is_not_dismissed_by_default(client):
    _admin(client)
    assert client.get("/api/settings").json()["onboarding_dismissed"] is False


def test_dismissing_onboarding_persists(client):
    _admin(client)
    r = client.patch("/api/settings", json={"onboarding_dismissed": True})
    assert r.status_code == 200
    assert r.json()["onboarding_dismissed"] is True
    # a fresh read sees it too, not just the response echoing the request back
    assert client.get("/api/settings").json()["onboarding_dismissed"] is True
