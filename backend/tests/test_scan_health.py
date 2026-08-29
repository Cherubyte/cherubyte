"""A report that found nothing means the agent's sweep broke, not that the
network emptied — the panel must not mark every device offline on it."""

from datetime import datetime, timedelta, timezone

import pytest
from netscan_protocol import AgentReport, HostObservation
from sqlalchemy import select

from app.models import ApprovalStatus, ConnectionHistory, Device, Event, EventLevel
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


def report(*, hosts=None, healthy=True) -> AgentReport:
    return AgentReport(
        sent_at=datetime.now(timezone.utc),
        subnets=["192.168.1.0/24"],
        hosts=hosts or [],
        healthy=healthy,
    )


async def _stale_online_device(session) -> int:
    """Online, but last seen long enough ago to be expired by the next sweep."""
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    device = Device(
        name="Telemovel",
        is_online=True,
        last_seen=old,
        approval_status=ApprovalStatus.approved,
    )
    session.add(device)
    await session.commit()
    return device.id


@pytest.mark.asyncio
async def test_an_empty_report_does_not_expire_devices(session):
    device_id = await _stale_online_device(session)

    result = await monitor.ingest_report(report(hosts=[]))

    assert result["degraded"] is True
    session.expire_all()
    refreshed = await session.get(Device, device_id)
    assert refreshed.is_online is True, "an empty report must not mark devices offline"
    assert (
        await session.scalar(
            select(ConnectionHistory).where(ConnectionHistory.device_id == device_id)
        )
    ) is None, "and must not write a leave to the history"


@pytest.mark.asyncio
async def test_an_agent_flagged_unhealthy_is_trusted_over_its_host_list(session):
    """The agent says its sweep broke. Believe it, even though hosts came with it."""
    device_id = await _stale_online_device(session)
    hosts = [HostObservation(mac="aa:bb:cc:00:00:01", ip="192.168.1.5")]

    result = await monitor.ingest_report(report(hosts=hosts, healthy=False))

    assert result["degraded"] is True
    session.expire_all()
    assert (await session.get(Device, device_id)).is_online is True


@pytest.mark.asyncio
async def test_a_degraded_report_is_logged_once_not_every_cycle(session):
    for _ in range(3):
        await monitor.ingest_report(report(hosts=[]))

    session.expire_all()
    alerts = (
        await session.execute(
            select(Event).where(Event.level == EventLevel.alert, Event.category == "scan")
        )
    ).scalars().all()
    assert len(alerts) == 1, "the alert should mark the transition, not repeat"


@pytest.mark.asyncio
async def test_a_healthy_report_expires_what_it_did_not_see(session):
    """The other direction: a good sweep must still be able to mark a device gone."""
    device_id = await _stale_online_device(session)
    hosts = [HostObservation(mac="aa:bb:cc:00:00:09", ip="192.168.1.9")]

    result = await monitor.ingest_report(report(hosts=hosts))

    assert result.get("degraded") is None
    session.expire_all()
    assert (await session.get(Device, device_id)).is_online is False
