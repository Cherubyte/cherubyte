"""The presence grid reads a bounded window of history, so the cases that
matter are the ones where the state is decided by events *outside* it."""

from datetime import datetime, timedelta, timezone

import pytest

from app.models import ConnectionHistory, Device, User
from app.services.presence import hourly_grid

DAYS = 3


async def _user_with_device(session, *, online: bool, first_seen_days_ago: int = 30):
    user = User(name="Sam")
    session.add(user)
    await session.flush()
    device = Device(
        name="Portatil",
        user_id=user.id,
        is_online=online,
        counts_for_presence=True,
        first_seen=datetime.now(timezone.utc) - timedelta(days=first_seen_days_ago),
    )
    session.add(device)
    await session.flush()
    return user, device


def _cell_of(grid: dict, moment: datetime) -> int:
    """Index of the cell covering `moment`, from the grid's own start."""
    start = datetime.fromisoformat(grid["start"]).astimezone(timezone.utc)
    return int((moment - start).total_seconds() // 3600)


async def _grid(session, user_id):
    return await hourly_grid(session, user_id, days=DAYS)


@pytest.mark.asyncio
async def test_join_and_leave_inside_the_window(session):
    user, device = await _user_with_device(session, online=False)
    now = datetime.now(timezone.utc)
    join, leave = now - timedelta(hours=5), now - timedelta(hours=3)
    session.add_all(
        [
            ConnectionHistory(device_id=device.id, event="join", timestamp=join),
            ConnectionHistory(device_id=device.id, event="leave", timestamp=leave),
        ]
    )
    await session.commit()

    grid = await _grid(session, user.id)
    cells = grid["cells"]
    assert cells[_cell_of(grid, join)] == 1
    assert cells[_cell_of(grid, now - timedelta(hours=4))] == 1
    assert cells[_cell_of(grid, now - timedelta(hours=1))] == 0


@pytest.mark.asyncio
async def test_device_already_online_before_the_window_opened(session):
    """The join is older than the window — the grid must still show presence.

    This is the case a naive `timestamp >= start` filter silently loses.
    """
    user, device = await _user_with_device(session, online=True)
    now = datetime.now(timezone.utc)
    session.add(
        ConnectionHistory(
            device_id=device.id, event="join", timestamp=now - timedelta(days=10)
        )
    )
    await session.commit()

    grid = await _grid(session, user.id)
    assert grid["cells"][0] == 1, "presence should start at the window edge"
    assert grid["cells"][_cell_of(grid, now)] == 1


@pytest.mark.asyncio
async def test_leave_before_the_window_means_absent(session):
    user, device = await _user_with_device(session, online=False)
    now = datetime.now(timezone.utc)
    session.add_all(
        [
            ConnectionHistory(
                device_id=device.id, event="join", timestamp=now - timedelta(days=11)
            ),
            ConnectionHistory(
                device_id=device.id, event="leave", timestamp=now - timedelta(days=10)
            ),
        ]
    )
    await session.commit()

    grid = await _grid(session, user.id)
    assert sum(grid["cells"]) == 0


@pytest.mark.asyncio
async def test_leave_inside_window_closes_a_stay_that_began_before_it(session):
    user, device = await _user_with_device(session, online=False)
    now = datetime.now(timezone.utc)
    leave = now - timedelta(hours=2)
    session.add_all(
        [
            ConnectionHistory(
                device_id=device.id, event="join", timestamp=now - timedelta(days=5)
            ),
            ConnectionHistory(device_id=device.id, event="leave", timestamp=leave),
        ]
    )
    await session.commit()

    grid = await _grid(session, user.id)
    assert grid["cells"][0] == 1
    assert grid["cells"][_cell_of(grid, now)] == 0


@pytest.mark.asyncio
async def test_online_device_with_no_history_at_all(session):
    user, _ = await _user_with_device(session, online=True, first_seen_days_ago=0)
    await session.commit()
    grid = await _grid(session, user.id)
    assert grid["cells"][_cell_of(grid, datetime.now(timezone.utc))] == 1


@pytest.mark.asyncio
async def test_devices_excluded_from_presence_are_ignored(session):
    user, device = await _user_with_device(session, online=True)
    device.counts_for_presence = False
    session.add(
        ConnectionHistory(
            device_id=device.id,
            event="join",
            timestamp=datetime.now(timezone.utc) - timedelta(days=10),
        )
    )
    await session.commit()
    grid = await _grid(session, user.id)
    assert sum(grid["cells"]) == 0


@pytest.mark.asyncio
async def test_stale_online_flag_does_not_override_a_leave_before_the_window(session):
    """A device row can say `is_online` while the last recorded event is a leave
    (the service was killed before it could expire the device). The event wins.

    Without the "last event before the window" lookup this paints the whole grid.
    """
    user, device = await _user_with_device(session, online=True)
    session.add(
        ConnectionHistory(
            device_id=device.id,
            event="leave",
            timestamp=datetime.now(timezone.utc) - timedelta(days=6),
        )
    )
    await session.commit()

    grid = await _grid(session, user.id)
    assert sum(grid["cells"]) == 0
