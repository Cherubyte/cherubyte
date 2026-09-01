from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..services import hoststat

router = APIRouter(prefix="/host-metrics", tags=["host-metrics"])


@router.get("")
async def host_temperature(
    hours: int = Query(24, ge=1, le=168),
    session: AsyncSession = Depends(get_session),
):
    """CPU/SoC temperature history for the panel host and every reporting agent."""
    return await hoststat.history(session, hours=hours)
