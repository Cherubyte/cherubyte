"""Internet monitoring and the MQTT / Home Assistant bridge."""

from datetime import timedelta

import pytest

from app.models import WanSample, utcnow
from app.services import mqtt, wan


# ------------------------------------------------------------------------ WAN

@pytest.fixture(autouse=True)
def _reset():
    wan.reset_transition_state()
    yield
    wan.reset_transition_state()


def sample(ok: bool, ms: float | None, minutes_ago: int = 0) -> WanSample:
    return WanSample(
        ok=ok, latency_ms=ms, target="1.1.1.1",
        timestamp=utcnow() - timedelta(minutes=minutes_ago),
    )


def test_summary_of_nothing_is_empty_rather_than_a_crash():
    assert wan.summarise([]) == {
        "samples": 0, "uptime": None, "avg_latency_ms": None, "online": None
    }


def test_summary_computes_uptime_and_latency():
    result = wan.summarise([
        sample(True, 10.0, 3), sample(True, 20.0, 2),
        sample(False, None, 1), sample(True, 30.0, 0),
    ])
    assert result["samples"] == 4
    assert result["uptime"] == 0.75
    assert result["avg_latency_ms"] == 20.0
    assert result["online"] is True


def test_summary_reports_the_latest_state_not_the_average():
    result = wan.summarise([sample(True, 10.0, 1), sample(False, None, 0)])
    assert result["online"] is False


def test_latency_is_ignored_for_failed_probes():
    result = wan.summarise([sample(False, None, 1), sample(True, 40.0, 0)])
    assert result["avg_latency_ms"] == 40.0


async def test_history_only_returns_the_requested_window(session):
    session.add(sample(True, 10.0, minutes_ago=5))
    session.add(sample(True, 11.0, minutes_ago=60 * 48))
    await session.commit()
    rows = await wan.history(session, hours=24)
    assert len(rows) == 1


# ----------------------------------------------------------------------- MQTT

class TestMqtt:
    @pytest.fixture(autouse=True)
    def _configured(self, monkeypatch):
        monkeypatch.setattr(mqtt.settings, "mqtt_enabled", True)
        monkeypatch.setattr(mqtt.settings, "mqtt_host", "broker.local")
        monkeypatch.setattr(mqtt.settings, "mqtt_base_topic", "netscan")
        monkeypatch.setattr(mqtt.settings, "mqtt_discovery_prefix", "homeassistant")
        mqtt.forget_announcements()
        yield
        mqtt.forget_announcements()

    def test_not_configured_without_a_host(self, monkeypatch):
        monkeypatch.setattr(mqtt.settings, "mqtt_host", "")
        assert mqtt.is_configured() is False

    def test_disabled_flag_wins(self, monkeypatch):
        monkeypatch.setattr(mqtt.settings, "mqtt_enabled", False)
        assert mqtt.is_configured() is False

    def test_slug_strips_characters_that_break_topics(self):
        assert mqtt.slug("Sala de Estar") == "sala_de_estar"
        assert mqtt.slug("a/b+c#d") == "a_b_c_d"
        assert mqtt.slug("") == "unknown"

    def test_base_topic_is_normalised(self, monkeypatch):
        monkeypatch.setattr(mqtt.settings, "mqtt_base_topic", "/casa/netscan/")
        assert mqtt.base_topic() == "casa/netscan"

    def test_user_discovery_creates_a_home_assistant_tracker(self):
        topic, payload = mqtt.user_discovery(7, "Sam")
        assert topic == "homeassistant/device_tracker/netscan_user_7/config"
        assert payload["state_topic"] == "netscan/user/7/state"
        assert payload["payload_home"] == "home"
        assert payload["unique_id"] == "netscan_user_7"
        assert payload["availability_topic"] == "netscan/status"

    def test_device_discovery_creates_a_connectivity_sensor(self):
        topic, payload = mqtt.device_discovery(3, "Portatil")
        assert topic == "homeassistant/binary_sensor/netscan_device_3/config"
        assert payload["device_class"] == "connectivity"
        assert payload["state_topic"] == "netscan/device/3/state"

    def test_everything_lands_under_one_home_assistant_device(self):
        _, user = mqtt.user_discovery(1, "A")
        _, dev = mqtt.device_discovery(1, "B")
        assert user["device"]["identifiers"] == dev["device"]["identifiers"] == ["netscan"]

    def test_publishing_without_a_running_worker_is_a_no_op(self):
        """The scan path calls this; a broker that is down must not raise."""
        mqtt.publish("netscan/x", "y")

    def test_discovery_is_announced_once_per_entity(self):
        sent: list[tuple[str, object]] = []
        mqtt.publish = lambda topic, payload, **kw: sent.append((topic, payload))  # type: ignore
        try:
            mqtt.publish_user_presence(1, "Sam", True)
            mqtt.publish_user_presence(1, "Sam", False)
            configs = [t for t, _ in sent if t.endswith("/config")]
            assert len(configs) == 1, "discovery should not be resent every cycle"
            assert [p for t, p in sent if not t.endswith("/config")] == ["home", "not_home"]
        finally:
            import importlib
            importlib.reload(mqtt)
