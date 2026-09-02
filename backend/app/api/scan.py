from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_session
from ..models import Agent, iso_utc, utcnow
from ..services.agent_nudge import poke as _poke

router = APIRouter(tags=["scan"])
logger = logging.getLogger("cherubyte.api.scan")


def _age_seconds(agent: Agent) -> float | None:
    if agent.last_seen is None:
        return None
    seen = agent.last_seen
    now = utcnow()
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=now.tzinfo)
    return (now - seen).total_seconds()


def _stale_after() -> float:
    """A monitor is "blind" once no agent has reported for noticeably longer
    than one sweep interval — three of them, floored at three minutes."""
    return max(180.0, 3.0 * settings.scan_interval_seconds)


@router.post("/scan")
async def trigger_scan(session: AsyncSession = Depends(get_session)):
    """Press Sweep: ask every enrolled agent to run a cycle now.

    The panel cannot see a LAN, so it does not scan — it nudges the agents that
    can. It reaches each agent's trigger port directly when it can (same-LAN,
    the common single-box install); when it cannot, it leaves a flag the agent
    picks up on its next check-in. Either way the answer says what actually
    happened, so the button never claims a sweep it did not cause.
    """
    agents = (
        await session.execute(select(Agent).where(Agent.enabled.is_(True)))
    ).scalars().all()

    if not agents:
        return {
            "ok": True,
            "status": "no-agents",
            "agents": 0,
            "triggered": 0,
            "queued": 0,
            "last_report": None,
            "stale": True,
            "detail": "No agent enrolled — enrol one to start receiving sweeps.",
        }

    poked = await asyncio.gather(*(_poke(a) for a in agents))
    triggered = 0
    queued = 0
    for agent, ok in zip(agents, poked):
        if ok:
            triggered += 1
        else:
            agent.scan_requested = True
            queued += 1
    await session.commit()

    ages = [s for s in (_age_seconds(a) for a in agents) if s is not None]
    youngest = min(ages) if ages else None
    stale = youngest is None or youngest > _stale_after()
    seen = [a.last_seen for a in agents if a.last_seen is not None]
    last_report = iso_utc(max(seen)) if seen else None

    if triggered:
        detail = f"Sweep requested from {triggered} agent(s)."
        if queued:
            detail += f" {queued} did not respond — they'll sweep on their next check-in."
    else:
        detail = (
            "The panel could not reach any agent directly — they'll sweep on "
            "their next check-in."
        )
        if stale:
            detail = (
                "No agent has reported in a while. Check that the agent "
                "service is running (systemctl status cherubyte-agent)."
            )

    return {
        "ok": True,
        "status": "triggered" if triggered else ("queued" if not stale else "stale"),
        "agents": len(agents),
        "triggered": triggered,
        "queued": queued,
        "last_report": last_report,
        "stale": stale,
        "detail": detail,
    }
