"""Port changes, ARP anomalies and the weekly digest — all driven off data the
scanner already collects.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import (
    ApprovalStatus,
    ConnectionHistory,
    Device,
    Event,
    IpAddress,
    MacAddress,
    OpenPort,
    User,
    utcnow,
)
from app.services import monitor
from cherubyte_protocol import HostObservation

MAC = "aa:bb:cc:dd:ee:01"
OTHER_MAC = "aa:bb:cc:dd:ee:02"


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    """No real notifications, and no policy or cooldown getting in the way."""
    sent: list[tuple] = []

    async def fake_broadcast(kind, title, lines, **kw):
        sent.append((kind, title, lines, kw))
        return {"ntfy": True}

    async def no_vendor(_mac):
        return None

    monkeypatch.setattr(monitor.notify, "broadcast", fake_broadcast)
    monkeypatch.setattr(monitor, "vendor_for", no_vendor)
    monitor.reset_notification_cooldowns()
    monitor.reset_watch_state()
    yield sent
    monitor.reset_notification_cooldowns()
    monitor.reset_watch_state()


async def _device_with_ports(session, ports: dict[int, str]) -> int:
    now = utcnow()
    device = Device(
        name="NAS",
        is_online=True,
        approval_status=ApprovalStatus.approved,
        first_seen=now,
        last_seen=now,
        macs=[MacAddress(address=MAC, first_seen=now, last_seen=now)],
        ips=[IpAddress(address="192.168.1.20", first_seen=now, last_seen=now)],
        open_ports=[OpenPort(port=p, service=s, last_seen=now) for p, s in ports.items()],
    )
    session.add(device)
    await session.commit()
    return device.id


async def _reload(session, device_id: int) -> Device:
    session.expire_all()
    return (
        await session.execute(
            select(Device)
            .where(Device.id == device_id)
            .options(selectinload(Device.open_ports), selectinload(Device.ips))
        )
    ).scalars().one()


# ------------------------------------------------------------- port change log

async def test_a_newly_opened_port_is_reported(session, _quiet):
    device_id = await _device_with_ports(session, {80: "http"})
    host = HostObservation(mac=MAC, ip="192.168.1.20", identified=True)
    host.open_ports = {80: "http", 22: "ssh"}

    await monitor._reconcile_host(session, host, False)
    await session.commit()

    device = await _reload(session, device_id)
    assert {p.port for p in device.open_ports} == {22, 80}
    kinds = [s[0] for s in _quiet]
    assert "port_change" in kinds
    assert any("22" in " ".join(s[2]) for s in _quiet)


async def test_a_closed_port_is_removed_and_reported(session, _quiet):
    device_id = await _device_with_ports(session, {22: "ssh", 80: "http"})
    host = HostObservation(mac=MAC, ip="192.168.1.20", identified=True)
    host.open_ports = {80: "http"}

    await monitor._reconcile_host(session, host, False)
    await session.commit()

    device = await _reload(session, device_id)
    assert {p.port for p in device.open_ports} == {80}, "closed ports should be dropped"
    assert "port_change" in [s[0] for s in _quiet]


async def test_a_discovery_only_cycle_never_reports_port_changes(session, _quiet):
    """The regression that matters: an unidentified sweep probes no ports, and
    must not be read as every port closing at once."""
    device_id = await _device_with_ports(session, {22: "ssh", 80: "http"})
    host = HostObservation(mac=MAC, ip="192.168.1.20", identified=False)

    await monitor._reconcile_host(session, host, False)
    await session.commit()

    device = await _reload(session, device_id)
    assert {p.port for p in device.open_ports} == {22, 80}
    assert _quiet == []


async def test_an_unchanged_port_set_is_silent(session, _quiet):
    await _device_with_ports(session, {80: "http"})
    host = HostObservation(mac=MAC, ip="192.168.1.20", identified=True)
    host.open_ports = {80: "http"}

    await monitor._reconcile_host(session, host, False)
    await session.commit()

    assert _quiet == []


# ------------------------------------------------------------- ARP anomalies

async def test_an_ip_moving_between_devices_is_reported(session, _quiet):
    await _device_with_ports(session, {80: "http"})   # owns 192.168.1.20
    host = HostObservation(mac=OTHER_MAC, ip="192.168.1.20", identified=True)

    await monitor._reconcile_host(session, host, False)
    await session.commit()

    assert "arp_anomaly" in [s[0] for s in _quiet]
    owner = (
        await session.execute(
            select(IpAddress).where(IpAddress.address == "192.168.1.20")
        )
    ).scalars().one()
    assert owner.device_id is not None


async def test_a_gateway_changing_mac_is_reported(session, _quiet):
    gateways = {"192.168.1.1"}
    first = [HostObservation(mac="aa:00:00:00:00:01", ip="192.168.1.1")]
    second = [HostObservation(mac="bb:00:00:00:00:02", ip="192.168.1.1")]

    await monitor._check_gateway_mac(first, gateways)
    assert _quiet == [], "the first sighting is the baseline, not an alert"

    await monitor._check_gateway_mac(second, gateways)
    assert [s[0] for s in _quiet] == ["arp_anomaly"]
    assert "Gateway MAC" in _quiet[0][1]


async def test_a_stable_gateway_is_silent(session, _quiet):
    hosts = [HostObservation(mac="aa:00:00:00:00:01", ip="192.168.1.1")]
    await monitor._check_gateway_mac(hosts, {"192.168.1.1"})
    await monitor._check_gateway_mac(hosts, {"192.168.1.1"})
    assert _quiet == []


# ---------------------------------------------------------------- weekly digest

async def test_digest_counts_what_happened(session):
    from app.services import digest

    now = datetime.now(timezone.utc)
    user = User(name="Sam")
    session.add(user)
    await session.flush()
    device = Device(
        name="Telemovel",
        user_id=user.id,
        counts_for_presence=True,
        first_seen=now - timedelta(days=2),
        last_seen=now,
    )
    session.add(device)
    await session.flush()
    session.add(ConnectionHistory(device_id=device.id, event="join", timestamp=now))
    session.add(Device(name="Antigo", first_seen=now - timedelta(days=90)))
    await session.commit()

    data = await digest.collect(session, days=7)

    assert data["total_devices"] == 2
    assert data["new_devices"] == ["Telemovel"], "only devices first seen in the window"
    assert data["top_users"] == [("Sam", 1)]

    lines = digest.format_lines(data)
    assert any("Telemovel" in line for line in lines)
    assert any("Sam" in line for line in lines)


async def test_digest_on_an_empty_network_still_formats(session):
    from app.services import digest

    data = await digest.collect(session)
    assert digest.format_lines(data)[0].startswith("Devices on the network: 0")
