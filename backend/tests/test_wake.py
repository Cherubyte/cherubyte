"""Wake-on-LAN: queue a MAC, hand it to reporting agents, age it out."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import HTTPException

from app.api.devices import wake_device
from app.models import Device, DeviceType, MacAddress, PendingWake, utcnow
from app.services import wol


async def _device(session, *, mac: str = "a4:83:e7:1c:2d:9f", is_random: bool = False):
    d = Device(
        device_type=DeviceType.unknown,
        approval_status="approved",
        is_online=False,
        macs=[MacAddress(address=mac, is_random=is_random)],
    )
    session.add(d)
    await session.flush()
    return d


@pytest.mark.asyncio
async def test_wake_queues_the_mac_and_agents_pick_it_up(session):
    d = await _device(session)
    out = await wake_device(d.id, session=session)
    assert out == {"ok": True, "mac": "a4:83:e7:1c:2d:9f"}

    assert await wol.take_pending(session) == ["a4:83:e7:1c:2d:9f"]


@pytest.mark.asyncio
async def test_second_wake_refreshes_rather_than_duplicates(session):
    d = await _device(session)
    await wake_device(d.id, session=session)
    await wake_device(d.id, session=session)
    rows = (await session.execute(PendingWake.__table__.select())).all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_stale_requests_are_dropped(session):
    d = await _device(session)
    await wake_device(d.id, session=session)
    row = (await session.execute(PendingWake.__table__.select())).first()
    # age it past both the pickup window and the TTL
    await session.execute(
        PendingWake.__table__.update()
        .where(PendingWake.id == row.id)
        .values(requested_at=utcnow() - timedelta(minutes=20))
    )
    await session.commit()
    assert await wol.take_pending(session) == []
    assert (await session.execute(PendingWake.__table__.select())).first() is None


@pytest.mark.asyncio
async def test_random_mac_is_refused(session):
    d = await _device(session, mac="b2:9e:44:1a:7f:03", is_random=True)
    with pytest.raises(HTTPException) as e:
        await wake_device(d.id, session=session)
    assert e.value.status_code == 422


@pytest.mark.asyncio
async def test_wake_uses_the_first_stable_mac_when_the_primary_is_random(session):
    # a phone-like device: rotating MAC first, real MAC second
    d = Device(
        device_type=DeviceType.laptop,
        approval_status="approved",
        is_online=False,
        macs=[
            MacAddress(address="7a:11:22:33:44:55", is_random=True),
            MacAddress(address="a4:83:e7:1c:2d:9f", is_random=False),
        ],
    )
    session.add(d)
    await session.flush()
    out = await wake_device(d.id, session=session)
    assert out == {"ok": True, "mac": "a4:83:e7:1c:2d:9f"}


@pytest.mark.asyncio
async def test_no_mac_is_refused(session):
    d = Device(device_type=DeviceType.unknown, approval_status="approved", is_online=False)
    session.add(d)
    await session.flush()
    with pytest.raises(HTTPException) as e:
        await wake_device(d.id, session=session)
    assert e.value.status_code == 422
