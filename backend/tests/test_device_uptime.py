"""Per-device uptime — fraction of the window the device was online."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.models import ConnectionHistory, Device, DeviceType
from app.services.uptime import device_uptime

NOW = datetime.utcnow()


async def _device(session, *, online: bool, first_seen: datetime) -> Device:
    d = Device(
        device_type=DeviceType.unknown,
        approval_status="approved",
        is_online=online,
        first_seen=first_seen,
        last_seen=NOW,
    )
    session.add(d)
    await session.flush()
    return d


def _ev(device_id: int, event: str, mins_ago: float) -> ConnectionHistory:
    return ConnectionHistory(
        device_id=device_id, event=event, timestamp=NOW - timedelta(minutes=mins_ago)
    )


@pytest.mark.asyncio
async def test_always_online_since_before_the_window(session):
    d = await _device(session, online=True, first_seen=NOW - timedelta(days=90))
    session.add(_ev(d.id, "join", 60 * 24 * 60))  # joined 60 days ago, never left
    await session.commit()

    out = await device_uptime(session, d.id, days=30)
    assert out["ratio"] == pytest.approx(1.0, abs=0.001)


@pytest.mark.asyncio
async def test_half_the_window(session):
    d = await _device(session, online=False, first_seen=NOW - timedelta(days=40))
    # online for the first 15 of the last 30 days, offline since
    session.add(_ev(d.id, "join", 60 * 24 * 30))
    session.add(_ev(d.id, "leave", 60 * 24 * 15))
    await session.commit()

    out = await device_uptime(session, d.id, days=30)
    assert out["ratio"] == pytest.approx(0.5, abs=0.01)


@pytest.mark.asyncio
async def test_no_history_yet_is_null(session):
    d = await _device(session, online=False, first_seen=NOW - timedelta(hours=2))
    await session.commit()
    out = await device_uptime(session, d.id, days=30)
    assert out["ratio"] is None
    assert out["samples"] == 0


@pytest.mark.asyncio
async def test_unknown_device(session):
    out = await device_uptime(session, 999, days=30)
    assert out["ratio"] is None
