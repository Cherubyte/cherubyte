"""On-demand per-device probes: ping, a port scan, or a traceroute.

Same delivery as Wake-on-LAN (see `wol.py`) and for the same reason: the
panel never reaches into a monitored network, so it queues the request and
every agent reporting in soon after is handed it. Only the one on the
target's segment can actually run it; the rest are expected to no-op. The
first result to come back for a row wins — later ones (an off-segment agent
timing out, say) are ignored rather than clobbering a real answer.
"""

from __future__ import annotations

import json
from datetime import timedelta

from cherubyte_protocol import DeviceActionRequest, DeviceActionResult
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ActionKind, ActionStatus, DeviceAction, utcnow

# how long a queued request is still handed to reporting agents
PICKUP_WINDOW = timedelta(seconds=90)
# a pending row older than this without a result is given up on
TTL = timedelta(minutes=5)


def queue(device_id: int, kind: ActionKind, ip: str) -> DeviceAction:
    """Build a new queued action row. The caller adds it to the session and
    commits, same as `wol.queue`."""
    return DeviceAction(device_id=device_id, kind=kind, ip=ip)


async def _expire_stale(session: AsyncSession) -> None:
    await session.execute(
        update(DeviceAction)
        .where(
            DeviceAction.status == ActionStatus.pending,
            DeviceAction.requested_at < utcnow() - TTL,
        )
        .values(status=ActionStatus.expired, completed_at=utcnow())
    )


async def take_pending(session: AsyncSession) -> list[DeviceActionRequest]:
    """The actions an agent should attempt right now. Also expires rows no
    agent picked up in time."""
    await _expire_stale(session)
    now = utcnow()
    rows = (
        await session.execute(
            select(DeviceAction).where(
                DeviceAction.status == ActionStatus.pending,
                DeviceAction.requested_at >= now - PICKUP_WINDOW,
            )
        )
    ).scalars().all()
    return [DeviceActionRequest(id=r.id, kind=r.kind.value, ip=r.ip) for r in rows]


async def record_results(session: AsyncSession, results: list[DeviceActionResult]) -> None:
    """Store the agent's outcome for each id still pending. Anything already
    done/failed/expired, or naming a row that no longer exists, is ignored."""
    if not results:
        return
    ids = [r.id for r in results]
    rows = {
        row.id: row
        for row in (
            await session.execute(
                select(DeviceAction).where(
                    DeviceAction.id.in_(ids), DeviceAction.status == ActionStatus.pending
                )
            )
        ).scalars()
    }
    for result in results:
        row = rows.get(result.id)
        if row is None:
            continue
        row.status = ActionStatus.done if result.ok else ActionStatus.failed
        row.result = json.dumps(result.model_dump(exclude={"id"}))
        row.completed_at = utcnow()


async def recent_for_device(session: AsyncSession, device_id: int, limit: int = 20) -> list[DeviceAction]:
    rows = (
        await session.execute(
            select(DeviceAction)
            .where(DeviceAction.device_id == device_id)
            .order_by(DeviceAction.requested_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return list(rows)
