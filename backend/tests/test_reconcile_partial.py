"""Identification is now spread across cycles, so most sweeps hand the
reconciler a host carrying only an IP and a MAC. That must never erase what an
earlier, fully identified sweep already learned.
"""

from datetime import datetime, timezone

import pytest

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import Device, DeviceType, MacAddress, OpenPort
from app.services import monitor
from cherubyte_protocol import HostObservation

MAC = "aa:bb:cc:dd:ee:ff"


async def _reload(session, device_id: int) -> Device:
    """Re-read with the collections eagerly loaded — a lazy load would fire IO
    outside the async context."""
    session.expire_all()
    return (
        await session.execute(
            select(Device)
            .where(Device.id == device_id)
            .options(selectinload(Device.open_ports), selectinload(Device.macs))
        )
    ).scalars().one()


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """The OUI lookup would otherwise reach for its vendor database."""
    async def no_vendor(_mac):
        return None

    monkeypatch.setattr(monitor, "vendor_for", no_vendor)
    monitor.reset_notification_cooldowns()
    yield
    monitor.reset_notification_cooldowns()


async def _identified_device(session) -> int:
    now = datetime.now(timezone.utc)
    device = Device(
        hostname="Sams-MacBook",
        vendor="Apple",
        model="MacBookPro18,3",
        os_guess="macOS",
        device_type=DeviceType.laptop,
        is_online=True,
        first_seen=now,
        last_seen=now,
        macs=[MacAddress(address=MAC, first_seen=now, last_seen=now)],
        open_ports=[OpenPort(port=22, service="ssh", last_seen=now)],
    )
    session.add(device)
    await session.commit()
    return device.id


@pytest.mark.asyncio
async def test_an_unidentified_sweep_keeps_the_known_identity(session):
    device_id = await _identified_device(session)

    # what a cheap cycle produces: discovery only, no probing
    bare = HostObservation(mac=MAC, ip="192.168.1.10")
    await monitor._reconcile_host(session, bare, False)
    await session.commit()

    device = await _reload(session, device_id)
    assert device.hostname == "Sams-MacBook"
    assert device.vendor == "Apple"
    assert device.model == "MacBookPro18,3"
    assert device.os_guess == "macOS"
    assert device.device_type == DeviceType.laptop


@pytest.mark.asyncio
async def test_an_unidentified_sweep_keeps_the_known_open_ports(session):
    device_id = await _identified_device(session)

    await monitor._reconcile_host(session, HostObservation(mac=MAC, ip="192.168.1.10"), False)
    await session.commit()

    device = await _reload(session, device_id)
    assert {p.port for p in device.open_ports} == {22}


@pytest.mark.asyncio
async def test_an_unidentified_sweep_still_refreshes_presence(session):
    """Discovery is the point of a cheap cycle: the device must stay online."""
    device_id = await _identified_device(session)
    device = await session.get(Device, device_id)
    device.is_online = False
    await session.commit()

    await monitor._reconcile_host(session, HostObservation(mac=MAC, ip="192.168.1.10"), False)
    await session.commit()

    refreshed = await _reload(session, device_id)
    assert refreshed.is_online is True


@pytest.mark.asyncio
async def test_a_later_identified_sweep_still_fills_gaps(session):
    """The cadence delays identification; it must not prevent it."""
    device_id = await _identified_device(session)
    device = await session.get(Device, device_id)
    device.os_guess = None
    await session.commit()

    rich = HostObservation(mac=MAC, ip="192.168.1.10", ttl_os="Windows")
    rich.open_ports = {3389: "rdp"}
    await monitor._reconcile_host(session, rich, False)
    await session.commit()

    refreshed = await _reload(session, device_id)
    assert refreshed.os_guess == "Windows"
    assert {p.port for p in refreshed.open_ports} == {22, 3389}
