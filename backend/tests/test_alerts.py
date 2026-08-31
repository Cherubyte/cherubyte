"""Alert policy: which kinds notify, on which channel, and quiet hours."""

from datetime import datetime

import pytest

from app.services import alerts


@pytest.fixture(autouse=True)
def _defaults(monkeypatch):
    monkeypatch.setattr(alerts.settings, "alert_policy", "")
    monkeypatch.setattr(alerts.settings, "quiet_hours_start", "")
    monkeypatch.setattr(alerts.settings, "quiet_hours_end", "")


def test_kinds_fall_back_to_their_default(monkeypatch):
    assert alerts.rule_for("device_new")["enabled"] is True
    assert alerts.rule_for("device_online")["enabled"] is False


def test_an_unknown_kind_is_allowed_rather_than_silently_dropped():
    """A kind added in code but missing from a stored policy must still fire."""
    assert alerts.channels_for("some_future_kind") == list(alerts.CHANNELS)


def test_policy_can_disable_a_kind(monkeypatch):
    monkeypatch.setattr(
        alerts.settings, "alert_policy", '{"device_new": {"enabled": false}}'
    )
    assert alerts.channels_for("device_new") == []


def test_policy_can_restrict_channels(monkeypatch):
    monkeypatch.setattr(
        alerts.settings,
        "alert_policy",
        '{"device_new": {"enabled": true, "channels": ["ntfy"]}}',
    )
    assert alerts.channels_for("device_new") == ["ntfy"]


def test_unknown_channels_are_ignored(monkeypatch):
    monkeypatch.setattr(
        alerts.settings,
        "alert_policy",
        '{"device_new": {"enabled": true, "channels": ["ntfy", "carrier_pigeon"]}}',
    )
    assert alerts.channels_for("device_new") == ["ntfy"]


def test_a_corrupt_policy_falls_back_to_defaults(monkeypatch):
    monkeypatch.setattr(alerts.settings, "alert_policy", "{not json")
    assert alerts.rule_for("device_new")["enabled"] is True


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 3, 10, hour, minute).astimezone()


class TestQuietHours:
    def test_off_when_unset(self):
        assert alerts.in_quiet_hours(_at(3)) is False

    def test_window_that_wraps_past_midnight(self, monkeypatch):
        monkeypatch.setattr(alerts.settings, "quiet_hours_start", "23:00")
        monkeypatch.setattr(alerts.settings, "quiet_hours_end", "07:30")
        assert alerts.in_quiet_hours(_at(3)) is True
        assert alerts.in_quiet_hours(_at(23, 30)) is True
        assert alerts.in_quiet_hours(_at(7, 45)) is False
        assert alerts.in_quiet_hours(_at(12)) is False

    def test_daytime_window(self, monkeypatch):
        monkeypatch.setattr(alerts.settings, "quiet_hours_start", "09:00")
        monkeypatch.setattr(alerts.settings, "quiet_hours_end", "18:00")
        assert alerts.in_quiet_hours(_at(12)) is True
        assert alerts.in_quiet_hours(_at(20)) is False

    def test_equal_bounds_disable_it(self, monkeypatch):
        monkeypatch.setattr(alerts.settings, "quiet_hours_start", "22:00")
        monkeypatch.setattr(alerts.settings, "quiet_hours_end", "22:00")
        assert alerts.in_quiet_hours(_at(22, 30)) is False

    def test_a_normal_alert_is_silenced(self, monkeypatch):
        monkeypatch.setattr(alerts.settings, "quiet_hours_start", "23:00")
        monkeypatch.setattr(alerts.settings, "quiet_hours_end", "07:00")
        assert alerts.channels_for("device_new", now=_at(3)) == []

    def test_an_urgent_alert_still_gets_through(self, monkeypatch):
        """Being woken at 3am by ARP spoofing is the entire point."""
        monkeypatch.setattr(alerts.settings, "quiet_hours_start", "23:00")
        monkeypatch.setattr(alerts.settings, "quiet_hours_end", "07:00")
        assert alerts.channels_for("arp_anomaly", now=_at(3)) == list(alerts.CHANNELS)
