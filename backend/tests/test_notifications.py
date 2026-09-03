"""Notification fan-out: per-channel formatting, auth, and the cooldown that
stops a flapping device from spamming every channel."""

import base64
from types import SimpleNamespace

import httpx
import pytest

from app.services import monitor, notify, ntfy, telegram


@pytest.fixture
def captured(monkeypatch):
    """Intercept the outgoing HTTP POST and hand back what was sent."""
    box: dict = {}

    class FakeResponse:
        status_code = 200
        text = "ok"

    async def fake_post(self, url, **kwargs):
        box["url"] = url
        box["json"] = kwargs.get("json")
        box["headers"] = kwargs.get("headers")
        return FakeResponse()

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    return box


@pytest.fixture(autouse=True)
def _reset_ntfy():
    ntfy._runtime.clear()
    yield
    ntfy._runtime.clear()


async def test_unconfigured_ntfy_sends_nothing(captured):
    assert await ntfy.send("olá") is False
    assert captured == {}


async def test_ntfy_publishes_json_with_title_and_tags(captured):
    ntfy.configure(server="https://ntfy.example.com/", topic="cherubyte", priority=4)

    assert await ntfy.send("corpo", title="🆕 Título", tags=["new"]) is True

    assert captured["url"] == "https://ntfy.example.com", "trailing slash trimmed"
    assert captured["json"] == {
        "topic": "cherubyte",
        "message": "corpo",
        "priority": 4,
        "title": "🆕 Título",
        "tags": ["new"],
    }


async def test_ntfy_token_auth(captured):
    ntfy.configure(topic="cherubyte", token="tk_123")
    await ntfy.send("x")
    assert captured["headers"]["Authorization"] == "Bearer tk_123"


async def test_ntfy_basic_auth(captured):
    ntfy.configure(topic="cherubyte", username="user", password="pw")
    await ntfy.send("x")
    expected = base64.b64encode(b"user:pw").decode()
    assert captured["headers"]["Authorization"] == f"Basic {expected}"


async def test_ntfy_priority_is_clamped():
    ntfy.configure(topic="cherubyte", priority=99)
    assert ntfy.priority() == 5
    ntfy.configure(priority=-3)
    assert ntfy.priority() == 1


async def test_disabling_or_clearing_the_topic_stops_delivery(captured):
    ntfy.configure(topic="cherubyte")
    assert ntfy.is_configured()

    ntfy.configure(enabled=False)
    assert await ntfy.send("x") is False

    ntfy.configure(enabled=True, topic="")
    assert await ntfy.send("x") is False
    assert captured == {}


async def test_broadcast_escapes_html_for_telegram_but_not_for_ntfy(
    captured, monkeypatch
):
    """A device named with `<` or `&` would otherwise break Telegram's parser."""
    sent: dict = {}

    async def fake_telegram(text: str) -> bool:
        sent["text"] = text
        return True

    monkeypatch.setattr(telegram, "send", fake_telegram)
    ntfy.configure(topic="cherubyte")

    result = await notify.broadcast(
        "device_new", "Novo & <teste>", ["Nome: a<b>", "MAC: aa"], emoji="🆕", prio=4
    )

    assert result == {"telegram": True, "ntfy": True, "email": False}
    assert sent["text"] == "🆕 <b>Novo &amp; &lt;teste&gt;</b>\nNome: a&lt;b&gt;\nMAC: aa"
    assert captured["json"]["title"] == "🆕 Novo & <teste>"
    assert captured["json"]["message"] == "Nome: a<b>\nMAC: aa"


class TestPerDeviceOverride:
    """Issue #9 — a device can override the global join/leave alert rules."""

    @pytest.fixture(autouse=True)
    def _clean(self):
        from app.services import alerts

        monitor.reset_notification_cooldowns()
        alerts.settings.alert_policy = ""
        yield
        monitor.reset_notification_cooldowns()
        alerts.settings.alert_policy = ""

    def test_force_ignores_a_disabled_rule_but_default_does_not(self):
        from app.services import alerts

        # device_online defaults to off
        assert alerts.channels_for("device_online") == []
        assert alerts.channels_for("device_online", force=True) == list(alerts.CHANNELS)

    async def test_always_notifies_even_when_the_rule_is_off(self, monkeypatch):
        sent: dict = {}

        async def fake_broadcast(kind, title, lines, **kw):
            sent.update(kind=kind, force=kw.get("force"))
            return {"ntfy": True}

        monkeypatch.setattr(monitor.notify, "broadcast", fake_broadcast)
        device = SimpleNamespace(id=1, notify_policy="always")
        await monitor._device_notify("device_online", device, "t", ["l"])
        assert sent == {"kind": "device_online", "force": True}

    async def test_mute_sends_nothing(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            monitor.notify, "broadcast", lambda *a, **k: calls.append(a)
        )
        device = SimpleNamespace(id=2, notify_policy="mute")
        assert await monitor._device_notify("device_offline", device, "t", []) == {}
        assert calls == []

    async def test_default_defers_to_the_policy(self, monkeypatch):
        seen: dict = {}

        async def fake_broadcast(kind, title, lines, **kw):
            seen["force"] = kw.get("force")
            return {}

        monkeypatch.setattr(monitor.notify, "broadcast", fake_broadcast)
        device = SimpleNamespace(id=3, notify_policy="default")
        await monitor._device_notify("device_online", device, "t", [])
        assert seen["force"] is False


class TestNotificationCooldown:
    @pytest.fixture(autouse=True)
    def _clean(self):
        monitor.reset_notification_cooldowns()
        yield
        monitor.reset_notification_cooldowns()

    def test_first_notice_passes_and_the_repeat_is_suppressed(self):
        assert monitor._notify_allowed("device_left", 1) is True
        assert monitor._notify_allowed("device_left", 1) is False

    def test_the_cooldown_is_per_device(self):
        assert monitor._notify_allowed("device_left", 1) is True
        assert monitor._notify_allowed("device_left", 2) is True

    def test_the_cooldown_is_per_kind(self):
        assert monitor._notify_allowed("device_left", 1) is True
        assert monitor._notify_allowed("device_new", 1) is True

    def test_it_can_be_disabled(self, monkeypatch):
        monkeypatch.setattr(monitor.settings, "notify_cooldown_seconds", 0)
        assert monitor._notify_allowed("device_left", 1) is True
        assert monitor._notify_allowed("device_left", 1) is True

    def test_it_expires(self, monkeypatch):
        monkeypatch.setattr(monitor.settings, "notify_cooldown_seconds", 60)
        assert monitor._notify_allowed("device_left", 1) is True

        from datetime import timedelta

        stale = monitor.utcnow() - timedelta(seconds=61)
        monitor._last_notified[("device_left", 1)] = stale
        assert monitor._notify_allowed("device_left", 1) is True
