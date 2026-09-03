"""History retention — the tables are append-only and would otherwise grow
without bound on a box scanning every minute."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.models import ConnectionHistory, Device, Event, EventLevel
from app.services import retention


async def _seed(session, *, ages_in_days: list[int]) -> Device:
    device = Device(name="Portatil")
    session.add(device)
    await session.flush()
    now = datetime.now(timezone.utc)
    for age in ages_in_days:
        ts = now - timedelta(days=age)
        session.add(Event(message=f"há {age}d", level=EventLevel.info, timestamp=ts))
        session.add(
            ConnectionHistory(device_id=device.id, event="join", timestamp=ts)
        )
    await session.commit()
    return device


@pytest.mark.asyncio
async def test_purge_removes_only_rows_past_the_cutoff(session):
    await _seed(session, ages_in_days=[1, 10, 100, 200])

    removed = await retention.purge(session, days=90)
    await session.commit()

    assert removed == {"events": 2, "connections": 2, "wan": 0, "host_temp": 0}
    assert await session.scalar(select(func.count(Event.id))) == 2
    assert await session.scalar(select(func.count(ConnectionHistory.id))) == 2


@pytest.mark.asyncio
async def test_zero_days_keeps_everything(session):
    await _seed(session, ages_in_days=[1, 500])

    removed = await retention.purge(session, days=0)
    await session.commit()

    assert removed == {"events": 0, "connections": 0, "wan": 0, "host_temp": 0}
    assert await session.scalar(select(func.count(Event.id))) == 2


@pytest.mark.asyncio
async def test_counts_reports_what_is_stored(session):
    await _seed(session, ages_in_days=[1, 2, 3])
    assert await retention.counts(session) == {
        "events": 3,
        "connections": 3,
        "fingerprints": 0,
        "push_subscriptions": 0,
    }


@pytest.mark.asyncio
async def test_purge_on_an_empty_database_is_a_no_op(session):
    assert await retention.purge(session, days=30) == {
        "events": 0,
        "connections": 0,
        "wan": 0,
        "host_temp": 0,
    }


@pytest.mark.asyncio
async def test_purge_also_prunes_wan_samples(session):
    """WAN sampling writes a row a minute — the densest table in the schema."""
    from app.models import WanSample

    now = datetime.now(timezone.utc)
    session.add(WanSample(ok=True, latency_ms=12.0, timestamp=now))
    session.add(WanSample(ok=False, latency_ms=None, timestamp=now - timedelta(days=120)))
    await session.commit()

    removed = await retention.purge(session, days=90)
    await session.commit()

    assert removed["wan"] == 1
    assert await session.scalar(select(func.count(WanSample.id))) == 1


@pytest.mark.asyncio
async def test_purge_also_prunes_host_temp_samples(session):
    """Host-temperature sampling is a row a minute per host, like WAN."""
    from app.models import HostTempSample

    now = datetime.now(timezone.utc)
    session.add(HostTempSample(agent_id=None, temp_c=47.0, timestamp=now))
    session.add(HostTempSample(agent_id=None, temp_c=51.0, timestamp=now - timedelta(days=120)))
    await session.commit()

    removed = await retention.purge(session, days=90)
    await session.commit()

    assert removed["host_temp"] == 1
    assert await session.scalar(select(func.count(HostTempSample.id))) == 1
