"""Weekly digest of what happened on the network.

Everything here comes from data already collected; it just gets read back once
a week and sent through the same channels as the alerts.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import SessionLocal
from ..models import (
    ApprovalStatus,
    ConnectionHistory,
    Device,
    Event,
    EventLevel,
    User,
    utcnow,
)
from . import wan
from .notify import broadcast

logger = logging.getLogger("cherubyte.digest")


async def collect(session: AsyncSession, days: int = 7) -> dict:
    since = utcnow() - timedelta(days=days)

    new_devices = list(
        (
            await session.execute(
                select(Device).where(Device.first_seen >= since).order_by(Device.first_seen)
            )
        ).scalars()
    )
    pending = await session.scalar(
        select(func.count(Device.id)).where(
            Device.approval_status == ApprovalStatus.pending
        )
    )
    total = await session.scalar(select(func.count(Device.id)))
    alerts = await session.scalar(
        select(func.count(Event.id)).where(
            Event.timestamp >= since, Event.level == EventLevel.alert
        )
    )

    # who joined most often — a cheap proxy for "most present"
    joins = await session.execute(
        select(User.name, func.count(ConnectionHistory.id))
        .select_from(ConnectionHistory)
        .join(Device, Device.id == ConnectionHistory.device_id)
        .join(User, User.id == Device.user_id)
        .where(
            ConnectionHistory.timestamp >= since,
            ConnectionHistory.event == "join",
            Device.counts_for_presence.is_(True),
            User.is_guest.is_(False),
        )
        .group_by(User.name)
        .order_by(func.count(ConnectionHistory.id).desc())
        .limit(5)
    )

    return {
        "days": days,
        "total_devices": total or 0,
        "new_devices": [d.display_name for d in new_devices],
        "pending": pending or 0,
        "alerts": alerts or 0,
        "top_users": [(name, count) for name, count in joins],
        "wan": wan.summarise(await wan.history(session, hours=days * 24)),
    }


def format_lines(data: dict) -> list[str]:
    lines = [
        f"Dispositivos na rede: {data['total_devices']}",
        f"Novos nos últimos {data['days']} dias: {len(data['new_devices'])}",
    ]
    for name in data["new_devices"][:8]:
        lines.append(f"  • {name}")
    if len(data["new_devices"]) > 8:
        lines.append(f"  … e mais {len(data['new_devices']) - 8}")
    if data["pending"]:
        lines.append(f"Por aprovar: {data['pending']}")
    if data["alerts"]:
        lines.append(f"Alertas registados: {data['alerts']}")

    wan_data = data.get("wan") or {}
    if wan_data.get("samples"):
        uptime = wan_data["uptime"]
        line = f"Internet: {uptime * 100:.1f}% disponível"
        if wan_data.get("avg_latency_ms") is not None:
            line += f", {wan_data['avg_latency_ms']:.0f} ms em média"
        lines.append(line)

    if data["top_users"]:
        lines.append("")
        lines.append("Mais presentes:")
        for name, count in data["top_users"]:
            lines.append(f"  • {name} ({count} entradas)")
    return lines


async def run_weekly() -> dict | None:
    """Scheduled entry point. Never raises."""
    if not settings.weekly_summary_enabled:
        return None
    try:
        async with SessionLocal() as session:
            data = await collect(session)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Weekly digest failed: %s", exc)
        return None
    await broadcast(
        "weekly_summary",
        "Resumo semanal do Cherubyte",
        format_lines(data),
        emoji="📊",
        tags=["bar_chart"],
        prio=2,
    )
    return data
