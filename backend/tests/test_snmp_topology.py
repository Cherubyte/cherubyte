"""SNMP sysDescr feeds the OS guess; LLDP neighbours become topology edges."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from netscan_protocol import AgentReport, HostObservation, LldpNeighbor
from sqlalchemy import select

from app import main
from app.models import Device, TopologyEdge
from app.services import monitor


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    async def no_vendor(_mac):
        return None

    monkeypatch.setattr(monitor, "vendor_for", no_vendor)
    monitor.reset_notification_cooldowns()
    monitor.reset_watch_state()
    yield


@pytest.fixture
def client(session):
    return TestClient(main.app)


def _report(*hosts: HostObservation) -> AgentReport:
    return AgentReport(
        sent_at=datetime.now(timezone.utc),
        subnets=["192.168.1.0/24"],
        hosts=list(hosts),
        healthy=True,
    )


@pytest.mark.asyncio
async def test_sysdescr_sets_the_os(session):
    await monitor.ingest_report(
        _report(
            HostObservation(
                mac="aa:bb:cc:00:00:01",
                ip="192.168.1.2",
                identified=True,
                snmp_sysname="core-sw",
                snmp_sysdescr="Cisco IOS Software, C2960X Software",
            )
        ),
        agent_id=1,
    )
    dev = (await session.execute(select(Device))).scalars().one()
    assert dev.os_guess == "Cisco IOS"


@pytest.mark.asyncio
async def test_lldp_neighbours_become_edges(session):
    host = HostObservation(
        mac="aa:bb:cc:00:00:01",
        ip="192.168.1.2",
        identified=True,
        snmp_sysname="core-sw",
        lldp_neighbors=[
            LldpNeighbor(local_port="1", remote_name="edge-sw", remote_port="24"),
            LldpNeighbor(local_port="2", remote_name="ap-lobby", remote_port="1"),
        ],
    )
    await monitor.ingest_report(_report(host), agent_id=7)

    edges = (await session.execute(select(TopologyEdge))).scalars().all()
    assert len(edges) == 2
    assert {e.remote_label for e in edges} == {"edge-sw", "ap-lobby"}
    linked = [e for e in edges if e.local_device_id is not None]
    assert linked and all(e.local_label == "core-sw" for e in edges)


@pytest.mark.asyncio
async def test_edges_are_refreshed_not_appended(session):
    def host(*neigh):
        return HostObservation(
            mac="aa:bb:cc:00:00:01", ip="192.168.1.2", identified=True,
            snmp_sysname="core-sw", lldp_neighbors=list(neigh),
        )

    await monitor.ingest_report(
        _report(host(LldpNeighbor(local_port="1", remote_name="a"),
                     LldpNeighbor(local_port="2", remote_name="b"))),
        agent_id=1,
    )
    await monitor.ingest_report(
        _report(host(LldpNeighbor(local_port="1", remote_name="a"))), agent_id=1
    )
    edges = (await session.execute(select(TopologyEdge))).scalars().all()
    assert [e.remote_label for e in edges] == ["a"]


def test_topology_endpoint(client):
    client.post("/api/auth/setup", json={"username": "admin", "password": "hunter2!!"})
    r = client.get("/api/topology")
    assert r.status_code == 200
    assert r.json() == {"nodes": [], "edges": []}
