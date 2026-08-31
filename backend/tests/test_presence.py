"""Presence reads a bounded window of history, so the cases that matter are the
ones where the state is decided by events *outside* it. The endpoint returns a
list of UTC intervals; the client renders them."""

from datetime import datetime, timedelta, timezone

import pytest

from app.models import ConnectionHistory, Device, User
from app.services.presence import presence_intervals

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


async def _data(session, user_id):
    return await presence_intervals(session, user_id, days=DAYS)


def _spans(data):
    return [
        (
            datetime.fromisoformat(a).astimezone(timezone.utc),
            datetime.fromisoformat(b).astimezone(timezone.utc),
        )
        for a, b in data["intervals"]
    ]


def _covers(data, moment: datetime) -> bool:
    return any(a <= moment <= b for a, b in _spans(data))


def _total_seconds(data) -> float:
    return sum((b - a).total_seconds() for a, b in _spans(data))


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

    data = await _data(session, user.id)
    assert _covers(data, now - timedelta(hours=4))
    assert not _covers(data, now - timedelta(hours=1))
    # the interval tracks the events to the minute, not to the hour
    (a, b), = _spans(data)
    assert abs((a - join).total_seconds()) < 1
    assert abs((b - leave).total_seconds()) < 1


@pytest.mark.asyncio
async def test_device_already_online_before_the_window_opened(session):
    """The join is older than the window — presence must still show.

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

    data = await _data(session, user.id)
    since = datetime.fromisoformat(data["since"]).astimezone(timezone.utc)
    assert _covers(data, since + timedelta(seconds=1)), "presence starts at the window edge"
    assert _covers(data, now - timedelta(seconds=1))


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

    assert _total_seconds(await _data(session, user.id)) == 0


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

    data = await _data(session, user.id)
    since = datetime.fromisoformat(data["since"]).astimezone(timezone.utc)
    assert _covers(data, since + timedelta(seconds=1))
    assert not _covers(data, now)
    (_, b), = _spans(data)
    assert abs((b - leave).total_seconds()) < 1


@pytest.mark.asyncio
async def test_online_device_with_no_history_at_all(session):
    # online, first seen before the window, no join/leave rows: present since the
    # window opened, right up to now
    user, _ = await _user_with_device(session, online=True, first_seen_days_ago=30)
    await session.commit()
    data = await _data(session, user.id)
    assert _covers(data, datetime.now(timezone.utc) - timedelta(minutes=1))


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
    assert _total_seconds(await _data(session, user.id)) == 0


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

    assert _total_seconds(await _data(session, user.id)) == 0


@pytest.mark.asyncio
async def test_overlapping_intervals_from_two_devices_are_merged(session):
    user, laptop = await _user_with_device(session, online=False)
    phone = Device(
        name="Telemovel",
        user_id=user.id,
        is_online=False,
        counts_for_presence=True,
        first_seen=datetime.now(timezone.utc) - timedelta(days=30),
    )
    session.add(phone)
    await session.flush()
    now = datetime.now(timezone.utc)
    session.add_all(
        [
            ConnectionHistory(device_id=laptop.id, event="join", timestamp=now - timedelta(hours=6)),
            ConnectionHistory(device_id=laptop.id, event="leave", timestamp=now - timedelta(hours=4)),
            ConnectionHistory(device_id=phone.id, event="join", timestamp=now - timedelta(hours=5)),
            ConnectionHistory(device_id=phone.id, event="leave", timestamp=now - timedelta(hours=3)),
        ]
    )
    await session.commit()

    spans = _spans(await _data(session, user.id))
    assert len(spans) == 1, "the two overlapping stays are one interval"
    a, b = spans[0]
    assert abs((a - (now - timedelta(hours=6))).total_seconds()) < 1
    assert abs((b - (now - timedelta(hours=3))).total_seconds()) < 1
