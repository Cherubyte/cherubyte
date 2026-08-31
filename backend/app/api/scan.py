from __future__ import annotations

import asyncio
import logging

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_session
from ..models import Agent, iso_utc, utcnow

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


async def _poke(agent: Agent) -> bool:
    """Ask one agent to sweep now, directly. True if it accepted."""
    if not agent.last_ip:
        return False
    url = f"http://{agent.last_ip}:{agent.health_port or 1002}/trigger"
    try:
        async with httpx.AsyncClient(timeout=2.5) as client:
            r = await client.post(url)
        return r.status_code < 400
    except Exception as exc:  # noqa: BLE001
        logger.info("Could not reach agent %s at %s: %s", agent.id, url, exc)
        return False


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
            "detail": "Nenhum agente inscrito — inscreve um para começar a receber varrimentos.",
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
        detail = f"Varrimento pedido a {triggered} agente(s)."
        if queued:
            detail += f" {queued} não respondeu(ram) — vão varrer no próximo check-in."
    else:
        detail = (
            "O painel não alcançou nenhum agente diretamente — vão varrer no "
            "próximo check-in."
        )
        if stale:
            detail = (
                "Nenhum agente reporta há algum tempo. Verifica se o serviço do "
                "agente está a correr (systemctl status cherubyte-agent)."
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
