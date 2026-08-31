"""Reconstruct when a user was present, as a list of continuous intervals.

Presence is "at least one of the user's presence-devices online". The window is
the last `days` days; everything is returned in UTC (ISO-8601) and the client
buckets it into its own local calendar days and renders it to the minute.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ConnectionHistory, Device


def _aware(dt: datetime) -> datetime:
    """SQLite hands back naive datetimes; history is stored in UTC."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _open_at_window_start(
    device: Device,
    window_events: list[ConnectionHistory],
    prior_event: str | None,
    start_utc: datetime,
) -> datetime | None:
    """When the device was already online as the window opened, the instant its
    presence should start counting from — otherwise None."""
    if prior_event == "join":
        return start_utc
    if prior_event == "leave":
        return None
    # Nothing recorded before the window. A leave as the first event in it means
    # the device was online but joined before any history existed; with no events
    # at all, fall back to the live state.
    already_on = window_events[0].event == "leave" if window_events else device.is_online
    return max(start_utc, _aware(device.first_seen)) if already_on else None


def _merge(intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    """Union of possibly-overlapping intervals, sorted."""
    out: list[tuple[datetime, datetime]] = []
    for a, b in sorted(intervals):
        if b <= a:
            continue
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


async def presence_intervals(
    session: AsyncSession, user_id: int, days: int = 7
) -> dict:
    now = datetime.now(timezone.utc)
    # one day of slack so the client's oldest local calendar day is fully covered
    # whatever its timezone offset
    start_utc = now - timedelta(days=days + 1)

    devices = (
        await session.execute(
            select(Device).where(
                Device.user_id == user_id, Device.counts_for_presence.is_(True)
            )
        )
    ).scalars().all()

    if not devices:
        return {
            "now": now.isoformat(),
            "since": start_utc.isoformat(),
            "intervals": [],
        }

    dev_ids = [d.id for d in devices]

    # Only the events inside the window — the history table grows without bound,
    # so reading all of it made this endpoint slower every month.
    history = (
        await session.execute(
            select(ConnectionHistory)
            .where(
                ConnectionHistory.device_id.in_(dev_ids),
                ConnectionHistory.timestamp >= start_utc,
            )
            .order_by(ConnectionHistory.timestamp)
        )
    ).scalars().all()

    # The window alone can't say whether a device was already online when it
    # opened, so pull the single latest event before it, per device.
    latest_before = (
        select(
            ConnectionHistory.device_id.label("device_id"),
            func.max(ConnectionHistory.timestamp).label("ts"),
        )
        .where(
            ConnectionHistory.device_id.in_(dev_ids),
            ConnectionHistory.timestamp < start_utc,
        )
        .group_by(ConnectionHistory.device_id)
        .subquery()
    )
    prior: dict[int, str] = {}
    for row in (
        await session.execute(
            select(ConnectionHistory).join(
                latest_before,
                and_(
                    ConnectionHistory.device_id == latest_before.c.device_id,
                    ConnectionHistory.timestamp == latest_before.c.ts,
                ),
            )
        )
    ).scalars():
        prior[row.device_id] = row.event

    by_dev: dict[int, list[ConnectionHistory]] = {}
    for h in history:
        by_dev.setdefault(h.device_id, []).append(h)

    intervals: list[tuple[datetime, datetime]] = []
    for d in devices:
        evs = by_dev.get(d.id, [])
        open_at: datetime | None = _open_at_window_start(d, evs, prior.get(d.id), start_utc)
        for ev in evs:
            if ev.event == "join" and open_at is None:
                open_at = _aware(ev.timestamp)
            elif ev.event == "leave" and open_at is not None:
                intervals.append((open_at, _aware(ev.timestamp)))
                open_at = None
        if open_at is not None:
            if d.is_online:
                end = now
            elif evs:
                end = _aware(evs[-1].timestamp)
            else:
                # an open join from before the window with no later event and the
                # device offline: nothing in this window can be painted
                end = start_utc
            if end > open_at:
                intervals.append((open_at, end))

    merged = _merge(
        [(max(a, start_utc), min(b, now)) for a, b in intervals if b > start_utc]
    )
    return {
        "now": now.isoformat(),
        "since": start_utc.isoformat(),
        "intervals": [[a.isoformat(), b.isoformat()] for a, b in merged],
    }
