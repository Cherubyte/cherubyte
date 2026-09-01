"""Host temperature: read the panel machine's own sensor, store a sample every
minute, and serve the panel's + every agent's history back for the Monitor
chart.

The panel's reading is taken here because the panel is the one host no agent
reports for. Agents send theirs on every sweep (`AgentReport.host_temp_c`), and
`api/agents.py` writes those rows; this module only reads them back.

The sensor read is Linux-only and dependency-free — see the agent's twin of
this reader for the reasoning. A panel with no readable sensor simply never
inserts a row and drops off its own chart.
"""

from __future__ import annotations

import glob
import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import SessionLocal
from ..models import Agent, HostTempSample, iso_utc, utcnow

logger = logging.getLogger("cherubyte.hoststat")

_PREFERRED = ("x86_pkg_temp", "cpu-thermal", "cpu_thermal", "cpu", "soc")


def _read_zone(path: str) -> float | None:
    try:
        with open(f"{path}/temp") as fh:
            milli = int(fh.read().strip())
    except (OSError, ValueError):
        return None
    celsius = milli / 1000.0
    return round(celsius, 1) if 1.0 < celsius < 150.0 else None


def read_cpu_temp() -> float | None:
    """The panel host's CPU/SoC temperature in °C, or None if nothing readable."""
    typed: dict[str, float] = {}
    for zone in sorted(glob.glob("/sys/class/thermal/thermal_zone*")):
        value = _read_zone(zone)
        if value is None:
            continue
        try:
            with open(f"{zone}/type") as fh:
                kind = fh.read().strip().lower()
        except OSError:
            kind = ""
        typed[kind] = value
    if not typed:
        return None
    for want in _PREFERRED:
        for kind, value in typed.items():
            if want in kind:
                return value
    return max(typed.values())


async def record_panel_temp() -> None:
    """Scheduled entry point — one panel-host reading. Never raises: a missing
    sensor or a locked database must not kill the job."""
    temp = read_cpu_temp()
    if temp is None:
        return
    try:
        async with SessionLocal() as session:
            session.add(HostTempSample(agent_id=None, temp_c=temp))
            await session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not store panel temperature: %s", exc)


def _bucket(points: list[tuple], target: int = 240) -> list[dict]:
    """Average the (timestamp, temp) rows down to at most `target` points, so a
    week of minute samples is a few hundred, not ten thousand, over the wire."""
    if not points:
        return []
    if len(points) <= target:
        return [{"t": iso_utc(ts), "c": round(c, 1)} for ts, c in points]
    span = (points[-1][0] - points[0][0]).total_seconds() or 1.0
    width = span / target
    start = points[0][0]
    out: list[dict] = []
    acc: list[float] = []
    slot = 0
    for ts, c in points:
        idx = int((ts - start).total_seconds() / width)
        if idx != slot and acc:
            mid = start + timedelta(seconds=width * (slot + 0.5))
            out.append({"t": iso_utc(mid), "c": round(sum(acc) / len(acc), 1)})
            acc = []
            slot = idx
        acc.append(c)
    if acc:
        mid = start + timedelta(seconds=width * (slot + 0.5))
        out.append({"t": iso_utc(mid), "c": round(sum(acc) / len(acc), 1)})
    return out


def _stats(points: list[dict]) -> dict:
    if not points:
        return {"current": None, "min": None, "max": None, "avg": None}
    values = [p["c"] for p in points]
    return {
        "current": values[-1],
        "min": round(min(values), 1),
        "max": round(max(values), 1),
        "avg": round(sum(values) / len(values), 1),
    }


async def history(session: AsyncSession, hours: int = 24) -> dict:
    """The panel's series plus one per agent that has readings in the window."""
    since = utcnow() - timedelta(hours=hours)
    rows = (
        await session.execute(
            select(HostTempSample)
            .where(HostTempSample.timestamp >= since)
            .order_by(HostTempSample.timestamp)
        )
    ).scalars().all()

    names = dict(
        (await session.execute(select(Agent.id, Agent.name))).all()
    )

    by_key: dict[str, list[tuple]] = {}
    for r in rows:
        key = "panel" if r.agent_id is None else f"agent:{r.agent_id}"
        by_key.setdefault(key, []).append((r.timestamp, r.temp_c))

    series: list[dict] = []
    # Panel first, then agents by name.
    order = sorted(
        by_key,
        key=lambda k: (k != "panel", names.get(int(k.split(":")[1]), "") if ":" in k else ""),
    )
    for key in order:
        pts = _bucket(by_key[key])
        if key == "panel":
            label, kind = "panel", "panel"
        else:
            aid = int(key.split(":")[1])
            label, kind = names.get(aid, f"agent {aid}"), "agent"
        series.append({"key": key, "label": label, "kind": kind, **_stats(pts), "points": pts})

    return {"hours": hours, "series": series}
