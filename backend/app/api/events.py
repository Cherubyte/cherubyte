from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models import ConnectionHistory, Event, EventLevel
from ..schemas import ConnectionOut, EventOut

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=list[EventOut])
async def list_events(
    session: AsyncSession = Depends(get_session),
    level: EventLevel | None = None,
    category: str | None = None,
    device_id: int | None = None,
    limit: int = Query(200, le=2000),
):
    stmt = select(Event).order_by(Event.timestamp.desc()).limit(limit)
    if level is not None:
        stmt = stmt.where(Event.level == level)
    if category is not None:
        stmt = stmt.where(Event.category == category)
    if device_id is not None:
        stmt = stmt.where(Event.device_id == device_id)
    res = await session.execute(stmt)
    return list(res.scalars())


@router.get("/connections", response_model=list[ConnectionOut])
async def connection_log(
    session: AsyncSession = Depends(get_session),
    device_id: int | None = None,
    limit: int = Query(200, le=2000),
):
    stmt = (
        select(ConnectionHistory)
        .order_by(ConnectionHistory.timestamp.desc())
        .limit(limit)
    )
    if device_id is not None:
        stmt = stmt.where(ConnectionHistory.device_id == device_id)
    res = await session.execute(stmt)
    return list(res.scalars())
