from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..config import settings
from ..database import get_session
from ..models import Agent, ApprovalStatus, Brand, Device, User, utcnow
from ..schemas import StatsOut
from ..scheduler import last_scan
from ..services import agents as agent_service

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("", response_model=StatsOut)
async def summary(session: AsyncSession = Depends(get_session)):
    total = await session.scalar(select(func.count(Device.id)))
    online = await session.scalar(
        select(func.count(Device.id)).where(Device.is_online.is_(True))
    )
    pending = await session.scalar(
        select(func.count(Device.id)).where(
            Device.approval_status == ApprovalStatus.pending
        )
    )
    approved = await session.scalar(
        select(func.count(Device.id)).where(
            Device.approval_status == ApprovalStatus.approved
        )
    )
    present = await session.scalar(
        select(func.count(func.distinct(Device.user_id)))
        .join(User, User.id == Device.user_id)
        .where(
            Device.user_id.is_not(None),
            Device.is_online.is_(True),
            # an always-on device (a desktop that never leaves) keeps a person
            # off the presence count — same rule as User.is_present everywhere else
            Device.counts_for_presence.is_(True),
            User.is_guest.is_(False),
        )
    )
    agent_rows = (
        await session.execute(select(Agent).where(Agent.enabled.is_(True)))
    ).scalars().all()
    seen = [a.last_seen for a in agent_rows if a.last_seen is not None]
    last_report = max(seen) if seen else None
    stale_after = max(180.0, 3.0 * settings.scan_interval_seconds)
    if last_report is None:
        agents_stale = bool(agent_rows)
    else:
        ref = last_report
        now = utcnow()
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=now.tzinfo)
        agents_stale = (now - ref).total_seconds() > stale_after

    return StatsOut(
        total=total or 0,
        online=online or 0,
        pending=pending or 0,
        approved=approved or 0,
        users_present=present or 0,
        subnet=", ".join(await agent_service.known_subnets(session)),
        last_scan=last_scan(),
        agents_configured=len(agent_rows),
        last_report=last_report,
        agents_stale=agents_stale,
    )


@router.get("/timeline")
async def timeline(
    session: AsyncSession = Depends(get_session),
    days: int = Query(30, ge=7, le=180),
):
    """New devices discovered per day + running total, oldest-first."""
    since = datetime.now(timezone.utc) - timedelta(days=days - 1)
    rows = (
        await session.execute(
            select(Device.first_seen).where(Device.first_seen >= since)
        )
    ).scalars().all()
    before = await session.scalar(
        select(func.count(Device.id)).where(Device.first_seen < since)
    ) or 0

    # Buckets are UTC calendar days: this is an aggregate series, not a wall
    # clock, so it is not worth threading the viewer's offset through here.
    per_day: Counter[str] = Counter()
    for ts in rows:
        per_day[ts.date().isoformat()] += 1

    out = []
    running = before
    start = date.today() - timedelta(days=days - 1)
    for i in range(days):
        d = (start + timedelta(days=i)).isoformat()
        n = per_day.get(d, 0)
        running += n
        out.append({"date": d, "new_devices": n, "total": running})
    return {"days": days, "starting_total": before, "series": out}


@router.get("/by-type")
async def by_type(session: AsyncSession = Depends(get_session)):
    rows = (
        await session.execute(
            select(Device.device_type, func.count(Device.id)).group_by(Device.device_type)
        )
    ).all()
    return sorted(
        [{"type": t.value, "count": c} for t, c in rows],
        key=lambda r: r["count"],
        reverse=True,
    )


@router.get("/by-brand")
async def by_brand(session: AsyncSession = Depends(get_session)):
    devices = (
        await session.execute(select(Device).options(selectinload(Device.macs)))
    ).scalars().all()
    brands = {
        b.name.lower(): b
        for b in (await session.execute(select(Brand))).scalars().all()
    }

    agg: dict[str, dict] = {}
    for d in devices:
        name = d.short_vendor or "Desconhecido"
        key = name.lower()
        entry = agg.setdefault(
            name, {"brand": name, "count": 0, "online": 0, "logo": None}
        )
        entry["count"] += 1
        if d.is_online:
            entry["online"] += 1
        b = brands.get(key)
        if b and b.logo:
            entry["logo"] = f"/uploads/{b.logo}"

    return sorted(agg.values(), key=lambda r: r["count"], reverse=True)
