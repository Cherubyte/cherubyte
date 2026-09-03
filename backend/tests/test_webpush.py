"""Web Push: VAPID key lifecycle, subscription storage, and the broadcast that
prunes a subscription the push service has forgotten."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import main
from app.database import SessionLocal
from app.models import PushSubscription, Setting
from app.services import auth, notify, webpush


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    webpush._runtime.clear()
    yield
    webpush._runtime.clear()


@pytest.fixture
def client(session):
    auth._failures.clear()
    c = TestClient(main.app)
    assert c.post(
        "/api/auth/setup", json={"username": "admin", "password": "hunter2!!"}
    ).status_code == 201
    return c


SUB = {
    "endpoint": "https://push.example.com/abc123",
    "keys": {"p256dh": "BUp; a fake key", "auth": "fake-auth"},
}


async def test_keys_are_generated_once_and_persisted(session):
    async with SessionLocal() as s:
        await webpush.ensure_keys(s)
        first = webpush.public_key()
        assert first
        webpush._runtime.clear()
        await webpush.ensure_keys(s)
        assert webpush.public_key() == first, "a second call must reuse the stored key"

    async with SessionLocal() as s:
        stored = {r.key for r in (await s.execute(select(Setting))).scalars()}
    assert {"vapid_private_pem", "vapid_public_key"} <= stored


def test_key_endpoint_exposes_the_public_key(client):
    r = client.get("/api/push/key")
    assert r.status_code == 200
    assert r.json()["key"]
    assert r.json()["enabled"] is True


def test_subscribe_then_unsubscribe(client):
    assert client.post("/api/push/subscribe", json=SUB).json() == {"ok": True}
    # idempotent upsert on the endpoint
    client.post("/api/push/subscribe", json=SUB)

    r = client.get("/api/settings")
    assert r.json()["webpush_subscriptions"] == 1

    client.post("/api/push/unsubscribe", json={"endpoint": SUB["endpoint"]})
    assert client.get("/api/settings").json()["webpush_subscriptions"] == 0


def test_subscribe_rejects_a_non_https_endpoint(client):
    bad = {**SUB, "endpoint": "http://push.example.com/x"}
    assert client.post("/api/push/subscribe", json=bad).status_code == 422


async def test_broadcast_sends_and_prunes_gone_subscriptions(session, monkeypatch):
    from pywebpush import WebPushException

    class FakeResponse:
        def __init__(self, code):
            self.status_code = code

    calls: list[str] = []

    def fake_send(info, payload):
        calls.append(info["endpoint"])
        if info["endpoint"].endswith("dead"):
            raise WebPushException("gone", response=FakeResponse(410))

    monkeypatch.setattr(webpush, "_send_blocking", fake_send)

    async with SessionLocal() as s:
        await webpush.ensure_keys(s)
        s.add(PushSubscription(endpoint="https://p/live", p256dh="k", auth="a"))
        s.add(PushSubscription(endpoint="https://p/dead", p256dh="k", auth="a"))
        await s.commit()

    result = await webpush.broadcast("Title", "Body", url="/")
    assert result == {"sent": 1, "removed": 1}
    assert set(calls) == {"https://p/live", "https://p/dead"}

    async with SessionLocal() as s:
        left = [r.endpoint for r in (await s.execute(select(PushSubscription))).scalars()]
    assert left == ["https://p/live"]


async def test_broadcast_is_a_noop_without_subscriptions(session, monkeypatch):
    monkeypatch.setattr(webpush, "_send_blocking", lambda *a: None)
    async with SessionLocal() as s:
        await webpush.ensure_keys(s)
    assert await webpush.broadcast("t", "b") == {"sent": 0, "removed": 0}


async def test_notify_broadcast_reaches_webpush(session, monkeypatch):
    seen: dict = {}

    async def fake_wp_broadcast(title, body, *, url=None):
        seen.update(title=title, body=body)
        return {"sent": 2, "removed": 0}

    monkeypatch.setattr(notify.webpush, "broadcast", fake_wp_broadcast)
    monkeypatch.setattr(notify.alerts.settings, "alert_policy", "")
    monkeypatch.setattr(notify.telegram, "is_configured", lambda: False)
    monkeypatch.setattr(notify.ntfy, "is_configured", lambda: False)

    result = await notify.broadcast("device_new", "New device", ["Name: x"], emoji="🆕")
    assert result.get("webpush") is True
    assert seen["title"] == "🆕 New device"


def test_webpush_is_a_known_channel():
    from app.services import alerts

    assert "webpush" in alerts.CHANNELS
    assert "webpush" in alerts.rule_for("device_new")["channels"]
