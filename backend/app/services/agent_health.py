"""Notice when a scanning agent goes silent, and when it comes back.

An agent pushes a report every sweep (default: once a minute). If one stops —
the host went down, the process crashed, the network it sits on lost its uplink
— the panel is blind to that whole segment but nothing else says so. This job
watches every enabled agent's ``last_seen`` and raises one alert on the way out
and one on the way back.

The "already alerted" state lives on the row (`Agent.offline_alerted`), not in
memory, so a panel restart during an outage does not re-notify.

Hosted, the scheduler runs this once per tenant inside `scoped_to`, so both
the session and `agent_offline_after_seconds` are that tenant's own.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import select

from ..config import settings
from ..database import open_session
from ..models import Agent, EventLevel, as_utc, utcnow

logger = logging.getLogger("cherubyte.agent_health")

# A single missed sweep must never trip the alert, whatever the operator sets.
MIN_THRESHOLD_SECONDS = 120


def _threshold() -> timedelta | None:
    secs = settings.agent_offline_after_seconds
    if not secs or secs <= 0:
        return None
    return timedelta(seconds=max(MIN_THRESHOLD_SECONDS, int(secs)))


async def check_agents() -> dict[str, list[str]]:
    """Scheduled entry point. Never raises. Returns {"offline": [...], "online": [...]}."""
    threshold = _threshold()
    if threshold is None:
        return {"offline": [], "online": []}

    went_offline: list[str] = []
    came_back: list[str] = []
    try:
        async with open_session() as session:
            agents = list(
                (
                    await session.execute(select(Agent).where(Agent.enabled.is_(True)))
                ).scalars()
            )
            now = utcnow()
            for agent in agents:
                if agent.last_seen is None:
                    # Never reported since enrolment — that is the Agents page's
                    # job to surface, not an outage alert.
                    continue
                silent_for = now - as_utc(agent.last_seen)
                stale = silent_for >= threshold

                if stale and not agent.offline_alerted:
                    agent.offline_alerted = True
                    went_offline.append(agent.name)
                    await _announce(
                        "offline", agent, minutes=int(silent_for.total_seconds() // 60)
                    )
                elif not stale and agent.offline_alerted:
                    agent.offline_alerted = False
                    came_back.append(agent.name)
                    await _announce("online", agent, minutes=0)

            if went_offline or came_back:
                await session.commit()
    except Exception as exc:  # noqa: BLE001  — a scheduled job must not die
        logger.warning("agent health check failed: %s", exc)
        return {"offline": [], "online": []}

    return {"offline": went_offline, "online": came_back}


async def _announce(transition: str, agent: Agent, *, minutes: int) -> None:
    from .agents import get_subnets
    from .monitor import log_event_standalone, publish_event
    from .notify import broadcast

    subnets = ", ".join(get_subnets(agent))
    where = f" ({subnets})" if subnets else ""

    if transition == "offline":
        span = f"{minutes} min" if minutes else "a while"
        await log_event_standalone(
            f"Agent {agent.name} went silent (no report for {span})",
            level=EventLevel.alert,
            category="agent",
        )
        await broadcast(
            "agent_offline",
            "A scanning agent went silent",
            [
                f"{agent.name}{where} has not reported for {span}.",
                "Its part of the network is not being scanned.",
            ],
            emoji="📡",
            tags=["warning"],
            prio=5,
        )
    else:
        await log_event_standalone(
            f"Agent {agent.name} is reporting again",
            level=EventLevel.success,
            category="agent",
        )
        await broadcast(
            "agent_online",
            "A scanning agent came back",
            [f"{agent.name}{where} is reporting again."],
            emoji="✅",
            tags=["white_check_mark"],
        )
    publish_event("agent_health", {"agent_id": agent.id, "transition": transition})
