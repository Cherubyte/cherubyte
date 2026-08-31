"""`online_since` on the device list — when an online device last joined."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.api.devices import list_devices
from app.models import ConnectionHistory, Device, DeviceType

# SQLite hands datetimes back naive; match that here.
NOW = datetime.utcnow()


async def _device(session, *, online: bool, first_seen: datetime) -> Device:
    d = Device(
        device_type=DeviceType.unknown,
        approval_status="approved",
        is_online=online,
        first_seen=first_seen,
        last_seen=NOW - timedelta(minutes=1 if online else 300),
    )
    session.add(d)
    await session.flush()
    return d


def _close(a: datetime, b: datetime, secs: float = 2) -> bool:
    return abs((a.replace(tzinfo=None) - b.replace(tzinfo=None)).total_seconds()) < secs


@pytest.mark.asyncio
async def test_online_since_is_the_latest_join(session):
    d = await _device(session, online=True, first_seen=NOW - timedelta(days=30))
    for mins in (60 * 24 * 10, 60 * 24 * 3, 45):  # oldest → newest join
        session.add(
            ConnectionHistory(
                device_id=d.id, event="join", timestamp=NOW - timedelta(minutes=mins)
            )
        )
    # a leave in between must not be picked
    session.add(
        ConnectionHistory(
            device_id=d.id, event="leave", timestamp=NOW - timedelta(minutes=20)
        )
    )
    await session.commit()

    (out,) = await list_devices(session=session, q=None)
    assert out.online_since is not None
    assert _close(out.online_since, NOW - timedelta(minutes=45))


@pytest.mark.asyncio
async def test_online_without_history_falls_back_to_first_seen(session):
    first = NOW - timedelta(days=5)
    await _device(session, online=True, first_seen=first)
    await session.commit()

    (out,) = await list_devices(session=session, q=None)
    assert out.online_since is not None
    assert _close(out.online_since, first)


@pytest.mark.asyncio
async def test_offline_device_has_no_online_since(session):
    d = await _device(session, online=False, first_seen=NOW - timedelta(days=5))
    session.add(
        ConnectionHistory(
            device_id=d.id, event="join", timestamp=NOW - timedelta(days=4)
        )
    )
    await session.commit()

    (out,) = await list_devices(session=session, q=None)
    assert out.online_since is None
