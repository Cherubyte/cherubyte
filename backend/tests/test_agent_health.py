"""The silent-agent watch: one alert when an agent stops reporting, one when it
comes back, and the flag on the row that survives a restart mid-outage."""

from datetime import timedelta

import pytest

from app.models import Agent, Event, EventLevel, utcnow
from app.services import agent_health
from sqlalchemy import select


@pytest.fixture(autouse=True)
def _capture(monkeypatch):
    sent: list[tuple] = []

    async def fake_broadcast(kind, title, lines, **kw):
        sent.append((kind, title, lines))
        return {"ntfy": True}

    monkeypatch.setattr("app.services.notify.broadcast", fake_broadcast)
    return sent


def _mins_ago(m: int):
    return utcnow() - timedelta(minutes=m)


async def _run(monkeypatch, threshold=600):
    monkeypatch.setattr(agent_health.settings, "agent_offline_after_seconds", threshold)
    return await agent_health.check_agents()


async def test_a_silent_agent_alerts_once(session, monkeypatch, _capture):
    session.add(Agent(name="attic", key_hash="x", last_seen=_mins_ago(30)))
    await session.commit()

    first = await _run(monkeypatch)
    assert first["offline"] == ["attic"]
    assert _capture[0][0] == "agent_offline"

    # a second pass while it is still silent says nothing new
    second = await _run(monkeypatch)
    assert second == {"offline": [], "online": []}
    assert len(_capture) == 1

    row = (await session.execute(select(Agent))).scalar_one()
    assert row.offline_alerted is True


async def test_recovery_clears_the_flag_and_notifies(session, monkeypatch, _capture):
    session.add(
        Agent(name="attic", key_hash="x", last_seen=_mins_ago(30), offline_alerted=True)
    )
    await session.commit()

    # it reported again a moment ago
    (await session.execute(select(Agent))).scalar_one().last_seen = _mins_ago(0)
    await session.commit()

    result = await _run(monkeypatch)
    assert result["online"] == ["attic"]
    assert _capture[0][0] == "agent_online"
    assert (await session.execute(select(Agent))).scalar_one().offline_alerted is False


async def test_fresh_agent_is_left_alone(session, monkeypatch, _capture):
    session.add(Agent(name="attic", key_hash="x", last_seen=_mins_ago(1)))
    await session.commit()
    assert await _run(monkeypatch) == {"offline": [], "online": []}
    assert _capture == []


async def test_never_reported_agent_is_not_an_outage(session, monkeypatch, _capture):
    session.add(Agent(name="attic", key_hash="x", last_seen=None))
    await session.commit()
    assert await _run(monkeypatch) == {"offline": [], "online": []}


async def test_disabled_agent_is_ignored(session, monkeypatch, _capture):
    session.add(
        Agent(name="old", key_hash="x", last_seen=_mins_ago(999), enabled=False)
    )
    await session.commit()
    assert await _run(monkeypatch) == {"offline": [], "online": []}


async def test_threshold_of_zero_disables_the_check(session, monkeypatch, _capture):
    session.add(Agent(name="attic", key_hash="x", last_seen=_mins_ago(99)))
    await session.commit()
    assert await _run(monkeypatch, threshold=0) == {"offline": [], "online": []}


async def test_a_single_missed_sweep_never_trips_it(session, monkeypatch, _capture):
    # operator sets an absurdly low threshold; the 120s floor still protects them
    session.add(Agent(name="attic", key_hash="x", last_seen=_mins_ago(1)))
    await session.commit()
    assert await _run(monkeypatch, threshold=5) == {"offline": [], "online": []}


async def test_it_logs_an_event(session, monkeypatch, _capture):
    session.add(Agent(name="attic", key_hash="x", last_seen=_mins_ago(30)))
    await session.commit()
    await _run(monkeypatch)

    events = list((await session.execute(select(Event))).scalars())
    assert any(
        e.category == "agent" and e.level == EventLevel.alert for e in events
    )


def test_agent_offline_is_an_urgent_alert_kind():
    from app.services import alerts

    assert alerts.kind("agent_offline").urgent is True
    assert alerts.kind("agent_online").default_on is False
