"""A watchlisted port opening on a known device raises a louder alert."""

from datetime import datetime, timezone

import pytest
from netscan_protocol import HostObservation
from sqlalchemy import select

from app.config import settings
from app.models import Device, Event, EventLevel, MacAddress, OpenPort
from app.services import monitor, portrisk

MAC = "aa:bb:cc:dd:ee:ff"


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    async def no_vendor(_mac):
        return None

    monkeypatch.setattr(monitor, "vendor_for", no_vendor)
    monitor.reset_notification_cooldowns()
    before = settings.risky_ports_ignore
    settings.risky_ports_ignore = ""
    yield
    settings.risky_ports_ignore = before
    monitor.reset_notification_cooldowns()


async def _device(session, *, ports=()) -> int:
    now = datetime.now(timezone.utc)
    d = Device(
        hostname="nas",
        is_online=True,
        first_seen=now,
        last_seen=now,
        macs=[MacAddress(address=MAC, first_seen=now, last_seen=now)],
        open_ports=[OpenPort(port=p, service="x", last_seen=now) for p in ports],
    )
    session.add(d)
    await session.commit()
    return d.id


def _host(ports) -> HostObservation:
    return HostObservation(
        mac=MAC, ip="192.168.1.10", identified=True, open_ports={p: "x" for p in ports}
    )


async def _security(session) -> list[Event]:
    rows = await session.execute(
        select(Event).where(Event.category == "security").order_by(Event.id)
    )
    return list(rows.scalars())


def test_risk_table_covers_the_usual_suspects():
    for p in (23, 445, 3389, 6379, 27017, 2375):
        assert portrisk.risk_for(p)
    assert portrisk.risk_for(8080) is None


@pytest.mark.asyncio
async def test_opening_telnet_alerts(session):
    dev = await _device(session, ports=[80])
    await monitor._reconcile_host(session, _host([80, 23]), False)
    await session.commit()
    events = await _security(session)
    assert len(events) == 1
    assert events[0].level == EventLevel.alert
    assert "23" in events[0].message


@pytest.mark.asyncio
async def test_opening_an_ordinary_port_does_not(session):
    await _device(session, ports=[80])
    await monitor._reconcile_host(session, _host([80, 8080]), False)
    await session.commit()
    assert await _security(session) == []


@pytest.mark.asyncio
async def test_a_port_already_open_is_not_re_alerted(session):
    await _device(session, ports=[22, 445])
    await monitor._reconcile_host(session, _host([22, 445]), False)  # no change
    await session.commit()
    assert await _security(session) == []


@pytest.mark.asyncio
async def test_the_ignore_list_silences_a_port(session):
    settings.risky_ports_ignore = "445, 3389"
    await _device(session, ports=[80])
    await monitor._reconcile_host(session, _host([80, 445]), False)
    await session.commit()
    assert await _security(session) == []
