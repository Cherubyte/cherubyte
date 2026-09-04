"""Retention for the append-only tables.

`events` and `connection_history` only ever grow. On a Pi scanning every
minute that is thousands of rows a week, which bloats the database and slows
every history read. A scheduled purge keeps the last N days.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import open_session
from ..models import (
    Agent,
    ConnectionHistory,
    Event,
    HostTempSample,
    PushSubscription,
    WanSample,
    utcnow,
)

logger = logging.getLogger("cherubyte.retention")


async def purge(session: AsyncSession, days: int | None = None) -> dict[str, int]:
    """Delete history older than `days`. 0 (or negative) keeps everything."""
    keep_days = settings.retention_days if days is None else days
    if keep_days <= 0:
        return {"events": 0, "connections": 0, "wan": 0, "host_temp": 0}
    cutoff = utcnow() - timedelta(days=keep_days)
    events = await session.execute(delete(Event).where(Event.timestamp < cutoff))
    conns = await session.execute(
        delete(ConnectionHistory).where(ConnectionHistory.timestamp < cutoff)
    )
    # WAN samples are the densest table of all — one row per minute per target
    wan = await session.execute(delete(WanSample).where(WanSample.timestamp < cutoff))
    # host temperatures are just as dense — one row per minute per host
    temps = await session.execute(
        delete(HostTempSample).where(HostTempSample.timestamp < cutoff)
    )
    return {
        "events": events.rowcount or 0,
        "connections": conns.rowcount or 0,
        "wan": wan.rowcount or 0,
        "host_temp": temps.rowcount or 0,
    }


async def counts(session: AsyncSession) -> dict[str, int]:
    return {
        "events": await session.scalar(select(func.count(Event.id))) or 0,
        "connections": await session.scalar(select(func.count(ConnectionHistory.id))) or 0,
        # DHCP fingerprinting is passive and happens at the agent; the panel
        # only ever sees the count each one reports.
        "fingerprints": await session.scalar(select(func.sum(Agent.last_fingerprints))) or 0,
        "push_subscriptions": await session.scalar(
            select(func.count(PushSubscription.id))
        ) or 0,
    }


async def run_purge() -> dict[str, int]:
    """Scheduled entry point. Never raises — a failed purge must not kill the job."""
    try:
        async with open_session() as session:
            removed = await purge(session)
            await session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Retention purge failed: %s", exc)
        return {"events": 0, "connections": 0, "wan": 0, "host_temp": 0}
    if any(removed.values()):
        logger.info(
            "Retention purge: %d events, %d connection rows, %d WAN samples, "
            "%d host-temp samples removed",
            removed["events"],
            removed["connections"],
            removed["wan"],
            removed["host_temp"],
        )
    return removed
