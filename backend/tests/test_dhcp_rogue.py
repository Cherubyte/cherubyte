"""A DHCP server that is not the gateway (and not allowlisted) raises an alert."""

from datetime import datetime, timezone

import pytest
from netscan_protocol import AgentReport, DhcpServerObservation, HostObservation
from sqlalchemy import select

from app.config import settings
from app.models import Event, EventLevel
from app.services import monitor


@pytest.fixture(autouse=True)
def _clean():
    monitor.reset_scan_health()
    monitor.reset_notification_cooldowns()
    monitor.reset_watch_state()
    before = settings.dhcp_allowlist
    settings.dhcp_allowlist = ""
    yield
    settings.dhcp_allowlist = before
    monitor.reset_watch_state()


def _report(*servers: DhcpServerObservation) -> AgentReport:
    return AgentReport(
        sent_at=datetime.now(timezone.utc),
        subnets=["192.168.1.0/24"],
        hosts=[HostObservation(mac="aa:bb:cc:00:00:01", ip="192.168.1.5")],
        dhcp_servers=list(servers),
        healthy=True,
    )


async def _security_events(session) -> list[Event]:
    rows = await session.execute(
        select(Event).where(Event.category == "security").order_by(Event.id)
    )
    return list(rows.scalars())


@pytest.mark.asyncio
async def test_the_gateway_answering_dhcp_is_fine(session):
    await monitor.ingest_report(_report(DhcpServerObservation(ip="192.168.1.1")))
    assert await _security_events(session) == []


@pytest.mark.asyncio
async def test_an_unexpected_dhcp_server_alerts(session):
    await monitor.ingest_report(
        _report(DhcpServerObservation(ip="192.168.1.66", mac="de:ad:be:ef:00:01"))
    )
    events = await _security_events(session)
    assert len(events) == 1
    assert events[0].level == EventLevel.alert
    assert "192.168.1.66" in events[0].message


@pytest.mark.asyncio
async def test_it_alerts_once_not_every_cycle(session):
    rogue = DhcpServerObservation(ip="192.168.1.66")
    await monitor.ingest_report(_report(rogue))
    await monitor.ingest_report(_report(rogue))
    await monitor.ingest_report(_report(rogue))
    assert len(await _security_events(session)) == 1


@pytest.mark.asyncio
async def test_the_allowlist_silences_a_known_server(session):
    settings.dhcp_allowlist = "192.168.1.66, aa:aa:aa:aa:aa:aa"
    await monitor.ingest_report(_report(DhcpServerObservation(ip="192.168.1.66")))
    await monitor.ingest_report(
        _report(DhcpServerObservation(ip="192.168.1.70", mac="aa:aa:aa:aa:aa:aa"))
    )
    assert await _security_events(session) == []


@pytest.mark.asyncio
async def test_a_v1_agent_sending_no_dhcp_servers_is_fine(session):
    # dhcp_servers defaults to [] — an older report simply carries none
    await monitor.ingest_report(_report())
    assert await _security_events(session) == []
