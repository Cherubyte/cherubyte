"""Enrolment and the agent channel.

An agent key is a bearer credential for somebody's entire home network
inventory, so most of these pin the refusals rather than the happy path.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from cherubyte_protocol import PROTOCOL_VERSION, AgentReport, HostObservation
from sqlalchemy import select

from app.models import Agent, Device, EnrolmentToken, WanSample
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


# --------------------------------------------------------------------- enrolment

@pytest.mark.asyncio
async def test_a_valid_token_admits_an_agent(session, client):
    token = await agent_service.issue_token(session, "sala")
    await session.commit()

    response = client.post(
        "/api/agents/enrol", json={"token": token, "name": "sala", "version": "1.0.0"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "sala"
    assert len(body["key"]) > 20


@pytest.mark.asyncio
async def test_the_key_is_never_stored_in_the_clear(session, client):
    """Read it out of the database rather than trusting the API's own answer."""
    token = await agent_service.issue_token(session, "sala")
    await session.commit()
    key = client.post("/api/agents/enrol", json={"token": token, "name": "sala"}).json()["key"]

    session.expire_all()
    stored = (await session.execute(select(Agent))).scalars().one()
    assert key not in (stored.key_hash or "")
    assert stored.key_hash == agent_service.hash_secret(key)


@pytest.mark.asyncio
async def test_an_unknown_token_is_refused(client):
    assert client.post("/api/agents/enrol", json={"token": "inventado", "name": "x"}).status_code == 403


@pytest.mark.asyncio
async def test_a_token_works_once(session, client):
    token = await agent_service.issue_token(session, "sala")
    await session.commit()

    assert client.post("/api/agents/enrol", json={"token": token, "name": "a"}).status_code == 200
    assert client.post("/api/agents/enrol", json={"token": token, "name": "b"}).status_code == 403


@pytest.mark.asyncio
async def test_an_expired_token_is_refused(session, client):
    token = agent_service.new_secret()
    session.add(
        EnrolmentToken(
            token_hash=agent_service.hash_secret(token),
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
    )
    await session.commit()

    assert client.post("/api/agents/enrol", json={"token": token, "name": "x"}).status_code == 403


# ------------------------------------------------------------------- reporting

@pytest.mark.asyncio
async def test_a_report_with_a_valid_key_is_ingested(session, client):
    agent_id, key = await _enrolled(session)

    response = client.post(
        f"/api/agents/{agent_id}/report",
        json=a_report(),
        headers={"Authorization": f"Bearer {key}"},
    )

    assert response.status_code == 200
    session.expire_all()
    devices = (await session.execute(select(Device))).scalars().all()
    assert len(devices) == 1, "the reported host should have become a device"


@pytest.mark.asyncio
async def test_a_report_without_a_key_is_refused(session, client):
    agent_id, _ = await _enrolled(session)

    assert client.post(f"/api/agents/{agent_id}/report", json=a_report()).status_code == 401

    session.expire_all()
    assert (await session.execute(select(Device))).scalars().first() is None


@pytest.mark.asyncio
async def test_a_wrong_key_is_refused(session, client):
    agent_id, _ = await _enrolled(session)

    response = client.post(
        f"/api/agents/{agent_id}/report",
        json=a_report(),
        headers={"Authorization": "Bearer nao-e-esta"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_one_agents_key_does_not_work_for_another(session, client):
    """The obvious mistake to make, and it must not be exploitable."""
    first_id, first_key = await _enrolled(session)
    second_id, _ = await _enrolled(session)

    response = client.post(
        f"/api/agents/{second_id}/report",
        json=a_report(),
        headers={"Authorization": f"Bearer {first_key}"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_a_disabled_agent_is_refused(session, client):
    agent_id, key = await _enrolled(session)
    agent = await session.get(Agent, agent_id)
    agent.enabled = False
    await session.commit()

    response = client.post(
        f"/api/agents/{agent_id}/report",
        json=a_report(),
        headers={"Authorization": f"Bearer {key}"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_an_unknown_protocol_version_is_refused_not_half_read(session, client):
    agent_id, key = await _enrolled(session)

    response = client.post(
        f"/api/agents/{agent_id}/report",
        json=a_report(protocol_version=PROTOCOL_VERSION + 99),
        headers={"Authorization": f"Bearer {key}"},
    )

    assert response.status_code == 409
    session.expire_all()
    assert (await session.execute(select(Device))).scalars().first() is None


@pytest.mark.asyncio
async def test_reporting_records_what_the_agent_swept(session, client):
    agent_id, key = await _enrolled(session)

    client.post(
        f"/api/agents/{agent_id}/report",
        json=a_report(dhcp_fingerprints=7),
        headers={"Authorization": f"Bearer {key}"},
    )

    session.expire_all()
    agent = await session.get(Agent, agent_id)
    assert agent.last_seen is not None
    assert agent.last_hosts == 1
    assert agent.last_fingerprints == 7
    assert agent_service.get_subnets(agent) == ["192.168.1.0/24"]


@pytest.mark.asyncio
async def test_wan_samples_ride_along_with_the_report(session, client):
    agent_id, key = await _enrolled(session)

    client.post(
        f"/api/agents/{agent_id}/report",
        json=a_report(
            wan=[{"target": "1.1.1.1", "ok": True, "latency_ms": 12.5, "at": None}]
        ),
        headers={"Authorization": f"Bearer {key}"},
    )

    session.expire_all()
    sample = (await session.execute(select(WanSample))).scalars().one()
    assert sample.ok is True
    assert sample.latency_ms == 12.5


@pytest.mark.asyncio
async def test_the_public_ip_from_a_report_lands_on_the_agent_and_the_wan_summary(
    session, client
):
    from app.services import wan as wan_service

    agent_id, key = await _enrolled(session)

    client.post(
        f"/api/agents/{agent_id}/report",
        json=a_report(
            wan=[
                {
                    "target": "1.1.1.1",
                    "ok": True,
                    "latency_ms": 9.0,
                    "at": None,
                    "public_ip": "203.0.113.7",
                }
            ]
        ),
        headers={"Authorization": f"Bearer {key}"},
    )

    session.expire_all()
    agent = (await session.execute(select(Agent))).scalars().one()
    assert agent.public_ip == "203.0.113.7"
    assert agent.public_ip_at is not None

    ip, at = await wan_service.latest_public_ip(session)
    assert ip == "203.0.113.7"
    assert at is not None


@pytest.mark.asyncio
async def test_the_panel_knows_which_subnets_exist_from_its_agents(session, client):
    agent_id, key = await _enrolled(session)
    client.post(
        f"/api/agents/{agent_id}/report",
        json=a_report(subnets=["10.0.0.0/24", "192.168.1.0/24"]),
        headers={"Authorization": f"Bearer {key}"},
    )

    session.expire_all()
    assert await agent_service.known_subnets(session) == [
        "10.0.0.0/24",
        "192.168.1.0/24",
    ]


# ------------------------------------------------------------- config push

@pytest.mark.asyncio
async def test_the_ack_carries_the_configuration_the_agent_should_run(session, client):
    agent_id, key = await _enrolled(session)

    response = client.post(
        f"/api/agents/{agent_id}/report",
        json=a_report(),
        headers={"Authorization": f"Bearer {key}"},
    )

    config = response.json()["config"]
    assert config["scan_interval_seconds"] > 0
    assert "wan_target" in config


@pytest.mark.asyncio
async def test_the_panel_sends_the_subnets_an_operator_configured(session, client):
    from app.config import settings as cfg

    agent_id, key = await _enrolled(session)
    cfg.subnets = [{"cidr": "10.0.0.0/24", "label": "cave"}]
    try:
        response = client.post(
            f"/api/agents/{agent_id}/report",
            json=a_report(),
            headers={"Authorization": f"Bearer {key}"},
        )
        assert response.json()["config"]["subnets"] == ["10.0.0.0/24"]
    finally:
        cfg.subnets = []
