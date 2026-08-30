"""Pressing Sweep.

The panel cannot reach into a LAN, so Sweep nudges the agents that can. These
pin the promise that the button never claims a sweep it did not cause: an
unreachable agent is *queued* (a flag it picks up on its next check-in), a
silent agent is reported as *stale*, and the flag fires exactly once.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from netscan_protocol import AgentReport, HostObservation
from sqlalchemy import select

from app.api.scan import trigger_scan
from app.api.stats import summary
from app.models import Agent
from app.services import agents as agent_service


@pytest.fixture
def client():
    import app.main

    return TestClient(app.main.app)


def a_report(**kw) -> dict:
    base = AgentReport(
        sent_at=datetime.now(timezone.utc),
        subnets=["192.168.1.0/24"],
        hosts=[HostObservation(mac="aa:bb:cc:00:00:01", ip="192.168.1.5", identified=True)],
    )
    payload = base.model_dump(mode="json")
    payload.update(kw)
    return payload


async def _enrolled(session) -> tuple[int, str]:
    token = await agent_service.issue_token(session, "test")
    await session.commit()
    agent, key = await agent_service.enrol(session, token=token, name="casa")
    await session.commit()
    return agent.id, key


def _report(client, agent_id, key, **kw):
    return client.post(
        f"/api/agents/{agent_id}/report",
        json=a_report(**kw),
        headers={"Authorization": f"Bearer {key}"},
    )


@pytest.mark.asyncio
async def test_sweep_with_no_agents_is_honest_about_it(session):
    body = await trigger_scan(session)
    assert body["status"] == "no-agents"
    assert body["agents"] == 0
    assert body["stale"] is True


@pytest.mark.asyncio
async def test_an_unreachable_agent_is_queued_not_claimed(session, client):
    agent_id, key = await _enrolled(session)
    # a fresh report so the agent is not "stale", but its trigger port is not
    # actually listening on the test host
    _report(client, agent_id, key)

    body = await trigger_scan(session)
    assert body["status"] == "queued"
    assert body["triggered"] == 0
    assert body["queued"] == 1

    session.expire_all()
    agent = await session.get(Agent, agent_id)
    assert agent.scan_requested is True
    assert agent.last_ip is not None  # recorded from the report


@pytest.mark.asyncio
async def test_the_queued_flag_rides_one_ack_then_clears(session, client):
    agent_id, key = await _enrolled(session)
    _report(client, agent_id, key)
    await trigger_scan(session)  # queues it

    first = _report(client, agent_id, key).json()
    assert first["scan_now"] is True

    second = _report(client, agent_id, key).json()
    assert second["scan_now"] is False


@pytest.mark.asyncio
async def test_a_reachable_agent_is_triggered_directly(session, client, monkeypatch):
    agent_id, key = await _enrolled(session)
    _report(client, agent_id, key)

    async def _ok(_agent):
        return True

    monkeypatch.setattr("app.api.scan._poke", _ok)
    body = await trigger_scan(session)
    assert body["status"] == "triggered"
    assert body["triggered"] == 1
    assert body["queued"] == 0

    session.expire_all()
    agent = await session.get(Agent, agent_id)
    assert agent.scan_requested is False


@pytest.mark.asyncio
async def test_a_silent_agent_reads_as_stale_in_scan_and_stats(session, client):
    agent_id, key = await _enrolled(session)
    _report(client, agent_id, key)
    # wind its last check-in back well past the stale threshold
    session.expire_all()
    agent = await session.get(Agent, agent_id)
    agent.last_seen = datetime.now(timezone.utc) - timedelta(hours=2)
    await session.commit()

    scan = await trigger_scan(session)
    assert scan["stale"] is True
    assert scan["status"] == "stale"

    stats = await summary(session)
    assert stats.agents_configured == 1
    assert stats.agents_stale is True
    assert stats.last_report is not None
