"""Settings ▸ Monitor — panel + agent host temperature history."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import main
from app.models import Agent, HostTempSample
from app.services import hoststat


@pytest.fixture
def client():
    return TestClient(main.app)


def _admin(client):
    client.post("/api/auth/setup", json={"username": "admin", "password": "hunter2!!"})


async def _seed(session):
    now = datetime.now(timezone.utc)
    agent = Agent(name="raspi", key_hash="x")
    session.add(agent)
    await session.flush()
    for i in range(5):
        ts = now - timedelta(minutes=i * 5)
        session.add(HostTempSample(agent_id=None, temp_c=45 + i, timestamp=ts))
        session.add(HostTempSample(agent_id=agent.id, temp_c=60 + i, timestamp=ts))
    await session.commit()
    return agent


@pytest.mark.asyncio
async def test_history_groups_panel_and_agent(session):
    await _seed(session)
    out = await hoststat.history(session, hours=24)

    keys = {s["key"]: s for s in out["series"]}
    assert set(keys) == {"panel", "agent:1"}
    assert keys["panel"]["kind"] == "panel"
    assert keys["agent:1"]["label"] == "raspi"
    # newest sample is i=0 -> 45 for the panel, 60 for the agent
    assert keys["panel"]["current"] == 45.0
    assert keys["agent:1"]["max"] == 64.0
    assert len(keys["panel"]["points"]) == 5


@pytest.mark.asyncio
async def test_history_window_excludes_old_rows(session):
    now = datetime.now(timezone.utc)
    session.add(HostTempSample(agent_id=None, temp_c=40.0, timestamp=now))
    session.add(HostTempSample(agent_id=None, temp_c=99.0, timestamp=now - timedelta(days=3)))
    await session.commit()

    out = await hoststat.history(session, hours=24)
    pts = out["series"][0]["points"]
    assert [p["c"] for p in pts] == [40.0]


@pytest.mark.asyncio
async def test_bucketing_caps_the_point_count(session):
    now = datetime.now(timezone.utc)
    for i in range(4000):
        session.add(
            HostTempSample(agent_id=None, temp_c=50.0, timestamp=now - timedelta(minutes=i))
        )
    await session.commit()

    out = await hoststat.history(session, hours=168)
    assert len(out["series"][0]["points"]) <= 260


def test_endpoint_requires_login(session, client):
    assert client.get("/api/host-metrics").status_code in (401, 403)


def test_endpoint_returns_series(session, client):
    _admin(client)
    r = client.get("/api/host-metrics?hours=24")
    assert r.status_code == 200
    assert r.json() == {"hours": 24, "series": []}
