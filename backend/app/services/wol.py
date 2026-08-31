"""Wake-on-LAN request queue.

The panel never reaches into a monitored network, so it can't send the magic
packet itself. Instead it queues the target MAC; every agent that reports within
a short window sends the packet on its own segment. Only the agent on the
target's link reaches its NIC — the rest broadcast into the void, harmlessly.
"""

from __future__ import annotations

import re
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import PendingWake, iso_utc, utcnow

# how long a queued request is still handed to reporting agents
PICKUP_WINDOW = timedelta(seconds=90)
# rows are cleared once they are this old
TTL = timedelta(minutes=10)

_MAC_RE = re.compile(r"^([0-9a-f]{2}:){5}[0-9a-f]{2}$")


def normalise(mac: str) -> str | None:
    m = mac.strip().lower().replace("-", ":")
    return m if _MAC_RE.match(m) else None


async def queue(session: AsyncSession, mac: str, device_id: int | None) -> str | None:
    """Queue a wake for `mac`; returns the normalised MAC or None if it's not one."""
    norm = normalise(mac)
    if norm is None:
        return None
    existing = (
        await session.execute(select(PendingWake).where(PendingWake.mac == norm))
    ).scalar_one_or_none()
    if existing is not None:
        existing.requested_at = utcnow()
        existing.device_id = device_id
    else:
        session.add(PendingWake(mac=norm, device_id=device_id))
    return norm


async def take_pending(session: AsyncSession) -> list[str]:
    """The MACs an agent should wake right now. Also garbage-collects stale rows."""
    now = utcnow()
    await session.execute(
        delete(PendingWake).where(PendingWake.requested_at < now - TTL)
    )
    rows = (
        await session.execute(
            select(PendingWake.mac).where(PendingWake.requested_at >= now - PICKUP_WINDOW)
        )
    ).scalars().all()
    return list(rows)


async def recent(session: AsyncSession) -> list[dict]:
    """For debugging / the API — what's queued and when."""
    rows = (
        await session.execute(select(PendingWake).order_by(PendingWake.requested_at.desc()))
    ).scalars().all()
    return [{"mac": r.mac, "device_id": r.device_id, "requested_at": iso_utc(r.requested_at)} for r in rows]
