"""A known MAC that starts presenting a different OS raises an alert."""

from datetime import datetime, timezone

import pytest
from cherubyte_protocol import HostObservation
from sqlalchemy import select

from app.models import ApprovalStatus, Device, Event, EventLevel
from app.services import monitor

MAC = "aa:bb:cc:dd:ee:ff"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    async def no_vendor(_mac):
        return None

    monkeypatch.setattr(monitor, "vendor_for", no_vendor)
    monitor.reset_notification_cooldowns()
    yield
    monitor.reset_notification_cooldowns()


def _host(**kw) -> HostObservation:
    return HostObservation(mac=MAC, ip="192.168.1.10", identified=True, **kw)


async def _security_events(session) -> list[Event]:
    rows = await session.execute(
        select(Event).where(Event.category == "security").order_by(Event.id)
    )
    return list(rows.scalars())


async def _fp(session) -> str | None:
    return (await session.execute(select(Device.fingerprint))).scalar_one()


@pytest.mark.asyncio
async def test_first_identification_sets_a_baseline_without_alerting(session):
    await monitor._reconcile_host(session, _host(ttl_os="Windows"), False)
    await session.commit()
    assert await _security_events(session) == []
    assert await _fp(session) is not None


@pytest.mark.asyncio
async def test_same_os_next_cycle_is_quiet(session):
    await monitor._reconcile_host(session, _host(ttl_os="Windows"), False)
    await monitor._reconcile_host(session, _host(ttl_os="Windows", open_ports={80: "http"}), False)
    await session.commit()
    assert await _security_events(session) == []


@pytest.mark.asyncio
async def test_os_family_flip_alerts(session):
    await monitor._reconcile_host(
        session, _host(mdns_services=["_smb"], ttl_os="unix"), False
    )  # -> macOS-ish
    await monitor._reconcile_host(session, _host(ttl_os="Windows"), False)
    await session.commit()

    events = await _security_events(session)
    assert len(events) == 1
    assert events[0].level == EventLevel.warning
    assert "→" in events[0].message


@pytest.mark.asyncio
async def test_only_ports_moving_does_not_alert(session):
    # non-risky ports, so the risky-port watchlist stays out of it
    await monitor._reconcile_host(session, _host(ttl_os="Windows", open_ports={8080: "http"}), False)
    await monitor._reconcile_host(
        session, _host(ttl_os="Windows", open_ports={8080: "http", 3000: "http", 8443: "https"}), False
    )
    await session.commit()
    assert await _security_events(session) == []
