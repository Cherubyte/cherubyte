from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..services import wan as wan_service

router = APIRouter(prefix="/wan", tags=["wan"])


@router.get("")
async def wan_history(
    hours: int = Query(24, ge=1, le=720),
    session: AsyncSession = Depends(get_session),
):
    samples = await wan_service.history(session, hours=hours)
    public_ip, public_ip_at = await wan_service.latest_public_ip(session)
    return {
        **wan_service.summarise(samples),
        "target": samples[-1].target if samples else "",
        "public_ip": public_ip,
        "public_ip_at": public_ip_at.isoformat() if public_ip_at else None,
        "points": [
            {
                "t": s.timestamp.isoformat(),
                "ok": s.ok,
                "ms": round(s.latency_ms, 1) if s.latency_ms is not None else None,
            }
            for s in samples
        ],
    }
