"""On-demand per-device probes: queue, hand to reporting agents, record the
result — same shape as Wake-on-LAN (test_wake.py), plus the extra step of an
agent reporting a result back."""

from __future__ import annotations

from datetime import timedelta

import pytest
from cherubyte_protocol import DeviceActionResult
from fastapi import HTTPException

from app.api.devices import list_device_actions, queue_device_action
from app.models import ActionKind, Device, DeviceAction, DeviceType, IpAddress, utcnow
from app.services import device_actions


async def _device(session, *, ip: str = "192.168.1.42") -> Device:
    d = Device(
        device_type=DeviceType.unknown,
        approval_status="approved",
        is_online=True,
        ips=[IpAddress(address=ip, is_primary=True)],
    )
    session.add(d)
    await session.flush()
    return d


@pytest.mark.asyncio
async def test_queue_creates_a_pending_row_agents_pick_up(session):
    d = await _device(session)
    out = await queue_device_action(d.id, ActionKind.ping, session=session)
    assert out["kind"] == "ping"
    assert out["status"] == "pending"
    assert out["result"] is None

    pending = await device_actions.take_pending(session)
    assert len(pending) == 1
    assert pending[0].kind == "ping"
    assert pending[0].ip == "192.168.1.42"


@pytest.mark.asyncio
async def test_a_pending_row_stays_on_offer_between_slow_report_cycles(session):
    """On a busy Wi-Fi /24 an agent's sweep-and-report cycle runs minutes
    apart. An action queued just after one report must still be handed out at
    the next — not dropped for being a couple of minutes old."""
    d = await _device(session)
    queued = await queue_device_action(d.id, ActionKind.ping, session=session)
    await session.execute(
        DeviceAction.__table__.update()
        .where(DeviceAction.id == queued["id"])
        .values(requested_at=utcnow() - timedelta(minutes=4))
    )
    await session.commit()

    pending = await device_actions.take_pending(session)
    assert [p.id for p in pending] == [queued["id"]]


@pytest.mark.asyncio
async def test_device_with_no_ip_is_refused(session):
    d = Device(device_type=DeviceType.unknown, approval_status="approved", is_online=False)
    session.add(d)
    await session.flush()
    with pytest.raises(HTTPException) as e:
        await queue_device_action(d.id, ActionKind.ping, session=session)
    assert e.value.status_code == 422


@pytest.mark.asyncio
async def test_a_reported_result_marks_the_row_done_and_stops_the_pickup(session):
    d = await _device(session)
    queued = await queue_device_action(d.id, ActionKind.ping, session=session)

    result = DeviceActionResult(id=queued["id"], ok=True, latency_ms=12.5, packet_loss=0)
    await device_actions.record_results(session, [result])
    await session.commit()

    assert await device_actions.take_pending(session) == []
    rows = await list_device_actions(d.id, session=session)
    assert rows[0]["status"] == "done"
    assert rows[0]["result"]["latency_ms"] == 12.5


@pytest.mark.asyncio
async def test_a_failed_result_is_recorded_as_failed(session):
    d = await _device(session)
    queued = await queue_device_action(d.id, ActionKind.traceroute, session=session)

    result = DeviceActionResult(id=queued["id"], ok=False, error="no route to host")
    await device_actions.record_results(session, [result])
    await session.commit()

    rows = await list_device_actions(d.id, session=session)
    assert rows[0]["status"] == "failed"
    assert rows[0]["result"]["error"] == "no route to host"


@pytest.mark.asyncio
async def test_a_second_result_for_an_already_done_row_is_ignored(session):
    d = await _device(session)
    queued = await queue_device_action(d.id, ActionKind.ping, session=session)

    first = DeviceActionResult(id=queued["id"], ok=True, latency_ms=5.0)
    await device_actions.record_results(session, [first])
    await session.commit()

    # a second, slower agent reports back after the first already answered
    second = DeviceActionResult(id=queued["id"], ok=False, error="timeout")
    await device_actions.record_results(session, [second])
    await session.commit()

    rows = await list_device_actions(d.id, session=session)
    assert rows[0]["status"] == "done"
    assert rows[0]["result"]["latency_ms"] == 5.0


@pytest.mark.asyncio
async def test_stale_pending_rows_expire_and_stop_being_handed_out(session):
    d = await _device(session)
    await queue_device_action(d.id, ActionKind.port_scan_quick, session=session)
    row = (await session.execute(DeviceAction.__table__.select())).first()
    await session.execute(
        DeviceAction.__table__.update()
        .where(DeviceAction.id == row.id)
        .values(requested_at=utcnow() - timedelta(minutes=20))
    )
    await session.commit()

    assert await device_actions.take_pending(session) == []
    rows = await list_device_actions(d.id, session=session)
    assert rows[0]["status"] == "expired"
