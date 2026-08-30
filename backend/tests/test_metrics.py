"""The /api/metrics Prometheus endpoint."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import settings
from app.models import (
    Agent,
    ApprovalStatus,
    Device,
    DeviceType,
    Event,
    EventLevel,
    User,
    WanSample,
)
from app.services.metrics import build_exposition


@pytest.fixture
def client(session):
    return TestClient(main.app)


@pytest.fixture(autouse=True)
def _no_token():
    before = settings.metrics_token, settings.metrics_enabled
    settings.metrics_token = ""
    settings.metrics_enabled = True
    yield
    settings.metrics_token, settings.metrics_enabled = before


async def _seed(session):
    alex = User(name="Alex")
    sam = User(name="Sam")
    session.add_all([alex, sam])
    await session.flush()
    session.add_all(
        [
            Device(
                name="Alex phone",
                user_id=alex.id,
                device_type=DeviceType.phone,
                is_online=True,
                approval_status=ApprovalStatus.approved,
                first_seen=datetime.now(timezone.utc) - timedelta(days=3),
            ),
            Device(
                name="Sam laptop",
                user_id=sam.id,
                device_type=DeviceType.laptop,
                is_online=False,
                approval_status=ApprovalStatus.pending,
                first_seen=datetime.now(timezone.utc) - timedelta(days=1),
            ),
        ]
    )
    session.add(Agent(name="netscan-agent", key_hash="x", last_hosts=2, last_healthy=True))
    session.add(WanSample(ok=True, latency_ms=12.5, target="1.1.1.1"))
    session.add(Event(message="hi", level=EventLevel.alert, category="security"))
    await session.commit()


@pytest.mark.asyncio
async def test_exposition_reports_the_core_gauges(session):
    await _seed(session)
    text = await build_exposition(session, version="9.9.9")

    assert '# TYPE netscan_devices gauge' in text
    assert 'netscan_devices 2' in text
    assert 'netscan_devices_online 1' in text
    assert 'netscan_devices_pending 1' in text
    assert 'netscan_devices_by_type{type="phone"} 1' in text
    assert 'netscan_build_info{version="9.9.9"} 1' in text
    assert 'netscan_people 2' in text
    assert 'netscan_people_present 1' in text
    assert 'netscan_person_present{person="Alex"} 1' in text
    assert 'netscan_person_present{person="Sam"} 0' in text
    assert 'netscan_wan_up 1' in text
    assert 'netscan_events_created_total{level="alert"} 1' in text
    # every level present even at zero, so a counter never disappears
    assert 'netscan_events_created_total{level="info"} 0' in text


def test_endpoint_is_open_when_no_token_is_set(client):
    r = client.get("/api/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert "netscan_build_info" in r.text


def test_endpoint_requires_the_token_when_one_is_set(client):
    settings.metrics_token = "s3cr3t"
    assert client.get("/api/metrics").status_code == 401
    assert client.get("/api/metrics?token=wrong").status_code == 401
    assert client.get("/api/metrics?token=s3cr3t").status_code == 200
    assert (
        client.get(
            "/api/metrics", headers={"Authorization": "Bearer s3cr3t"}
        ).status_code
        == 200
    )


def test_endpoint_can_be_disabled(client):
    settings.metrics_enabled = False
    assert client.get("/api/metrics").status_code == 404


@pytest.mark.asyncio
async def test_label_values_are_escaped(session):
    session.add(User(name='weird"name\\here'))
    await session.commit()
    text = await build_exposition(session)
    assert 'person="weird\\"name\\\\here"' in text
