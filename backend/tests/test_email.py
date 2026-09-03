"""Email (SMTP) channel: config gating, the message that goes on the wire, and
the branded HTML part that rides alongside the plain text."""

import pytest

from app.services import alerts, email, notify


@pytest.fixture(autouse=True)
def _reset_email():
    email._runtime.clear()
    yield
    email._runtime.clear()


@pytest.fixture
def sent(monkeypatch):
    """Capture the EmailMessage instead of opening a socket."""
    box: dict = {}

    def fake_send_blocking(msg):
        box["msg"] = msg

    monkeypatch.setattr(email, "_send_blocking", fake_send_blocking)
    return box


def _configure_ok():
    email.configure(
        host="smtp.example.com",
        port=587,
        security="starttls",
        username="panel@example.com",
        password="pw",
        to_addrs="me@example.com, you@example.com",
    )


async def test_unconfigured_sends_nothing(sent):
    assert await email.send("subject", "body") is False
    assert sent == {}


async def test_missing_recipient_is_not_configured():
    email.configure(host="smtp.example.com", username="panel@example.com")
    assert email.is_configured() is False


async def test_send_builds_a_multipart_message(sent):
    _configure_ok()
    assert email.is_configured() is True

    ok = await email.send("Hi", "plain body", "<p>rich body</p>")
    assert ok is True

    msg = sent["msg"]
    assert msg["Subject"] == "Hi"
    assert msg["To"] == "me@example.com, you@example.com"
    assert "panel@example.com" in msg["From"]
    parts = {p.get_content_type() for p in msg.walk()}
    assert {"text/plain", "text/html"} <= parts


async def test_from_defaults_to_the_auth_username(sent):
    email.configure(
        host="smtp.example.com", username="bot@example.com", to_addrs="me@example.com"
    )
    await email.send("s", "b")
    assert "bot@example.com" in sent["msg"]["From"]


async def test_disabling_stops_delivery(sent):
    _configure_ok()
    email.configure(enabled=False)
    assert await email.send("s", "b") is False
    assert sent == {}


async def test_bad_security_mode_falls_back_to_starttls():
    email.configure(security="banana")
    assert email.security() == "starttls"


def test_render_marks_urgent_alerts():
    plain = email.render("All good", ["line one", "  indented"])
    urgent = email.render("Rogue DHCP", ["something bad"], urgent=True)
    assert email._PALETTE["alert"] in urgent
    assert email._PALETTE["alert"] not in plain
    # indentation becomes a muted, padded row
    assert "padding-left:16px" in plain


def test_render_escapes_device_names():
    html = email.render("New device: <script>", ["Name: a & b"])
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "a &amp; b" in html


async def test_broadcast_reaches_email_when_the_policy_allows(monkeypatch):
    captured: dict = {}

    async def fake_email_send(subject, text, html=None):
        captured.update(subject=subject, text=text, html=html)
        return True

    monkeypatch.setattr(alerts.settings, "alert_policy", "")
    monkeypatch.setattr(notify.email, "send", fake_email_send)
    monkeypatch.setattr(notify.email, "is_configured", lambda: True)
    monkeypatch.setattr(notify.telegram, "is_configured", lambda: False)
    monkeypatch.setattr(notify.ntfy, "is_configured", lambda: False)

    result = await notify.broadcast(
        "rogue_dhcp", "Rogue DHCP server", ["IP: 10.0.0.9"], emoji="🚨"
    )

    assert result.get("email") is True
    assert captured["subject"] == "🚨 Rogue DHCP server"
    assert "IP: 10.0.0.9" in captured["text"]
    assert email._PALETTE["alert"] in captured["html"]  # rogue_dhcp is urgent


def test_email_is_a_known_channel():
    assert "email" in alerts.CHANNELS
    # a brand-new deployment offers it on every kind by default
    assert "email" in alerts.rule_for("device_new")["channels"]
