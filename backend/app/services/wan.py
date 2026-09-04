"""Internet reachability, as reported by the agents.

The probe itself lives in the agent — it is a network operation, and the panel
may be nowhere near the network in question. What is left here is reading the
samples back and deciding that a transition is worth telling someone about.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import Agent, EventLevel, WanSample, utcnow

logger = logging.getLogger("cherubyte.wan")

# None until the first sample; then the last known state, to spot transitions.
_last_ok: bool | None = None


def reset_transition_state() -> None:
    """Forget the last known state, so the next sample is a baseline not a change."""
    global _last_ok
    _last_ok = None


async def history(session: AsyncSession, hours: int = 24) -> list[WanSample]:
    since = utcnow() - timedelta(hours=hours)
    rows = await session.execute(
        select(WanSample).where(WanSample.timestamp >= since).order_by(WanSample.timestamp)
    )
    return list(rows.scalars())


async def latest_public_ip(session: AsyncSession) -> tuple[str | None, datetime | None]:
    """The most recently confirmed egress address across all agents.

    One value for the dashboard; the per-agent addresses are on the agents list.
    """
    row = await session.execute(
        select(Agent.public_ip, Agent.public_ip_at)
        .where(Agent.public_ip.is_not(None))
        .order_by(Agent.public_ip_at.desc())
        .limit(1)
    )
    hit = row.first()
    return (hit[0], hit[1]) if hit else (None, None)


def summarise(samples: list[WanSample]) -> dict:
    total = len(samples)
    if not total:
        return {"samples": 0, "uptime": None, "avg_latency_ms": None, "online": None}
    ok = [s for s in samples if s.ok]
    latencies = [s.latency_ms for s in ok if s.latency_ms is not None]
    return {
        "samples": total,
        "uptime": round(len(ok) / total, 4),
        "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else None,
        "online": samples[-1].ok,
    }


async def record(samples: list, target: str = "") -> None:
    """Note a transition in the samples an agent just delivered.

    The agent is deliberately not told what the previous state was: it would
    have to be told per panel, and two agents watching the same internet would
    then disagree. The panel holds the state because the panel holds the alert.
    """
    global _last_ok
    for sample in samples:
        ok = bool(sample.ok)
        if _last_ok is not None and ok != _last_ok:
            await _announce("up" if ok else "down", sample.target or target, sample.latency_ms)
        _last_ok = ok


async def _announce(transition: str, target: str, latency: float | None) -> None:
    # imported here: monitor imports this module for the dashboard summary
    from .monitor import log_event_standalone, publish_event
    from .notify import broadcast

    if transition == "down":
        await log_event_standalone(
            f"Internet unreachable ({target} not responding)",
            level=EventLevel.alert,
            category="wan",
        )
        await broadcast(
            "wan_down",
            "Internet down",
            [f"{target} stopped responding."],
            emoji="🌐",
            tags=["warning"],
            prio=5,
        )
    else:
        detail = f"{latency:.0f} ms" if latency is not None else "reachable"
        await log_event_standalone(
            f"Internet recovered ({target}, {detail})",
            level=EventLevel.success,
            category="wan",
        )
        await broadcast(
            "wan_up",
            "Internet recovered",
            [f"{target} is responding again ({detail})."],
            emoji="✅",
            tags=["white_check_mark"],
        )
    publish_event("wan_change", {"transition": transition})


def local_now() -> datetime:
    return datetime.now(timezone.utc).astimezone()
