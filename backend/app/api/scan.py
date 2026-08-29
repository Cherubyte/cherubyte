from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models import Agent
from ..scheduler import last_scan

router = APIRouter(tags=["scan"])


@router.post("/scan")
async def trigger_scan(session: AsyncSession = Depends(get_session)):
    """There is nothing to trigger here any more.

    Scanning belongs to the agents, which run their own cadence and push. The
    panel has no way to reach into a LAN and start one — that is the whole
    reason the split exists. Kept as a route so an older UI gets an honest
    answer rather than a 404 it would show as a broken button.
    """
    agents = (await session.execute(select(Agent).where(Agent.enabled.is_(True)))).scalars().all()
    return {
        "ok": True,
        "status": "agent-driven",
        "agents": len(agents),
        "last_report": last_scan(),
        "detail": (
            "Os agentes varrem no seu próprio intervalo e enviam para o painel."
            if agents
            else "Nenhum agente inscrito — inscreve um para começar a receber varrimentos."
        ),
    }
