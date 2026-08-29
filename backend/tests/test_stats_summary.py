"""The dashboard summary — the numbers on the front page."""

from datetime import datetime, timedelta, timezone

import pytest

from app.api.stats import summary
from app.models import Device, User


async def _person(session, name, *, online, counts):
    user = User(name=name)
    session.add(user)
    await session.flush()
    session.add(Device(
        name=f"{name}-phone",
        user_id=user.id,
        is_online=online,
        counts_for_presence=counts,
        first_seen=datetime.now(timezone.utc) - timedelta(days=5),
    ))
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_present_count_ignores_always_on_devices(session):
    # genuinely present: an online phone that counts
    await _person(session, "Ana", online=True, counts=True)
    await _person(session, "Rui", online=True, counts=True)
    # only device online is an always-on one — NOT present
    await _person(session, "Eva", online=True, counts=False)
    # offline
    await _person(session, "Zé", online=False, counts=True)
    await session.commit()

    out = await summary(session)
    assert out.users_present == 2


@pytest.mark.asyncio
async def test_present_count_excludes_guests(session):
    await _person(session, "Ana", online=True, counts=True)
    guest = await _person(session, "Visitor", online=True, counts=True)
    guest.is_guest = True
    await session.commit()

    out = await summary(session)
    assert out.users_present == 1
