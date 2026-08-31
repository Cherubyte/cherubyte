"""`/api/topology` — the links between devices, from LLDP.

Empty until an SNMP-enabled agent reads an LLDP-MIB off a managed switch. On a
flat LAN there is nothing to draw: everything hangs off the one router.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models import TopologyEdge, iso_utc

router = APIRouter(prefix="/topology", tags=["topology"])


@router.get("")
async def topology(session: AsyncSession = Depends(get_session)):
    rows = (
        await session.execute(select(TopologyEdge).order_by(TopologyEdge.id))
    ).scalars().all()
    labels: set[str] = set()
    edges = []
    for e in rows:
        if e.local_label:
            labels.add(e.local_label)
        if e.remote_label:
            labels.add(e.remote_label)
        edges.append(
            {
                "local": e.local_label,
                "local_device_id": e.local_device_id,
                "local_port": e.local_port,
                "remote": e.remote_label,
                "remote_port": e.remote_port,
                "seen_at": iso_utc(e.seen_at),
            }
        )
    return {"nodes": sorted(labels), "edges": edges}
