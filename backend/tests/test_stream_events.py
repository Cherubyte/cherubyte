"""SSE events raised while reconciling a report must not reach a subscriber
before the transaction commits — otherwise a client that refetches on
"device_new" queries /api/devices and does not see the device yet."""

from datetime import datetime, timezone

import pytest
from netscan_protocol import AgentReport, HostObservation
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Device, MacAddress
from app.services import monitor


@pytest.fixture(autouse=True)
def _clean_state():
    monitor.reset_scan_health()
    monitor.reset_notification_cooldowns()
    monitor.reset_watch_state()
    yield
    monitor.reset_scan_health()
    monitor.reset_notification_cooldowns()
    monitor.reset_watch_state()


def _report(hosts):
    return AgentReport(
        sent_at=datetime.now(timezone.utc),
        subnets=["192.168.1.0/24"],
        hosts=hosts,
        healthy=True,
    )


def test_batch_publish_holds_events_until_it_exits():
    q = monitor.subscribe()
    try:
        with monitor._batch_publish():
            monitor._publish("device_new", {"id": 1})
            monitor._publish("device_online", {"id": 1})
            assert q.empty(), "events must not be emitted while the batch is open"
        assert [q.get_nowait()["type"] for _ in range(2)] == [
            "device_new",
            "device_online",
        ]
    finally:
        monitor.unsubscribe(q)


@pytest.mark.asyncio
async def test_new_device_is_committed_by_the_time_its_event_fires(session):
    mac = "aa:bb:cc:00:00:41"
    q = monitor.subscribe()
    try:
        await monitor.ingest_report(
            _report([HostObservation(mac=mac, ip="192.168.1.41")])
        )
        kinds = []
        while not q.empty():
            kinds.append(q.get_nowait()["type"])
    finally:
        monitor.unsubscribe(q)

    assert "device_new" in kinds

    # A fresh session — as the API would use for the refetch — sees the device.
    async with SessionLocal() as s2:
        found = (
            await s2.execute(
                select(Device).join(MacAddress).where(MacAddress.address == mac)
            )
        ).scalars().first()
    assert found is not None
