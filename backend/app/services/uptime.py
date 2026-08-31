"""How much of the last N days a single device was online.

Reuses the interval reconstruction from `presence` — a device is "up" whenever
it is online, which is the same shape as a person being "present" via one
device. The ratio is covered time over the window.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ConnectionHistory, Device, iso_utc
from .presence import _aware, _merge, _open_at_window_start


async def device_uptime(session: AsyncSession, device_id: int, days: int = 30) -> dict:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)

    device = (
        await session.execute(select(Device).where(Device.id == device_id))
    ).scalar_one_or_none()
    if device is None:
        return {"days": days, "ratio": None, "since": iso_utc(start), "now": iso_utc(now), "samples": 0}

    evs = (
        await session.execute(
            select(ConnectionHistory)
            .where(
                ConnectionHistory.device_id == device_id,
                ConnectionHistory.timestamp >= start,
            )
            .order_by(ConnectionHistory.timestamp)
        )
    ).scalars().all()

    prior_ts = (
        select(func.max(ConnectionHistory.timestamp))
        .where(
            ConnectionHistory.device_id == device_id,
            ConnectionHistory.timestamp < start,
        )
        .scalar_subquery()
    )
    prior_row = (
        await session.execute(
            select(ConnectionHistory).where(
                and_(
                    ConnectionHistory.device_id == device_id,
                    ConnectionHistory.timestamp == prior_ts,
                )
            )
        )
    ).scalars().first()
    prior = prior_row.event if prior_row is not None else None

    # No history at all and never online → nothing to report yet.
    if not evs and prior is None and not device.is_online:
        first = _aware(device.first_seen)
        if first > start:
            return {
                "days": days,
                "ratio": None,
                "since": iso_utc(start),
                "now": iso_utc(now),
                "samples": 0,
            }

    intervals: list[tuple[datetime, datetime]] = []
    open_at = _open_at_window_start(device, list(evs), prior, start)
    for ev in evs:
        if ev.event == "join" and open_at is None:
            open_at = _aware(ev.timestamp)
        elif ev.event == "leave" and open_at is not None:
            intervals.append((open_at, _aware(ev.timestamp)))
            open_at = None
    if open_at is not None:
        end = now if device.is_online else (_aware(evs[-1].timestamp) if evs else start)
        if end > open_at:
            intervals.append((open_at, end))

    merged = _merge([(max(a, start), min(b, now)) for a, b in intervals if b > start])
    covered = sum((b - a).total_seconds() for a, b in merged)
    window = (now - start).total_seconds()

    return {
        "days": days,
        "ratio": round(covered / window, 4) if window else None,
        "since": iso_utc(start),
        "now": iso_utc(now),
        "samples": len(evs),
    }
