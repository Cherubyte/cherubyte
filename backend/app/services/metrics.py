"""Prometheus exposition for the panel.

A read-only text endpoint (`/api/metrics`) so a Prometheus / VictoriaMetrics /
Grafana Agent scrape can graph the same numbers the dashboard shows. Hand-rolled
rather than pulling in `prometheus_client`: the output is a handful of gauges and
one counter, and the text format is a few lines of rules.

Everything here is a read of the same tables the API already exposes — the
endpoint's own auth (an optional `metrics_token`) lives in `api/metrics.py`.
"""

from __future__ import annotations

from datetime import timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import (
    Agent,
    ApprovalStatus,
    Device,
    DeviceType,
    Event,
    EventLevel,
    HostTempSample,
    User,
    WanSample,
    utcnow,
)


def _escape(value: str) -> str:
    """Escape a label value per the Prometheus text format."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _render_labels(labels: dict[str, str] | None) -> str:
    if not labels:
        return ""
    inner = ",".join(f'{k}="{_escape(str(v))}"' for k, v in labels.items())
    return f"{{{inner}}}"


def _num(value: float) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    return repr(float(value))


class _Exposition:
    """Accumulates metric families with their HELP/TYPE headers, once each."""

    def __init__(self) -> None:
        self._lines: list[str] = []
        self._declared: set[str] = set()

    def _declare(self, name: str, kind: str, help_text: str) -> None:
        if name in self._declared:
            return
        self._declared.add(name)
        self._lines.append(f"# HELP {name} {help_text}")
        self._lines.append(f"# TYPE {name} {kind}")

    def sample(
        self,
        name: str,
        kind: str,
        value: float,
        *,
        help: str = "",
        labels: dict[str, str] | None = None,
    ) -> None:
        self._declare(name, kind, help or name)
        self._lines.append(f"{name}{_render_labels(labels)} {_num(value)}")

    def gauge(self, name: str, value: float, **kw) -> None:
        self.sample(name, "gauge", value, **kw)

    def counter(self, name: str, value: float, **kw) -> None:
        self.sample(name, "counter", value, **kw)

    def render(self) -> str:
        return "\n".join(self._lines) + "\n"


def _epoch(dt) -> float | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


async def build_exposition(session: AsyncSession, *, version: str = "unknown") -> str:
    m = _Exposition()
    now = utcnow()

    m.gauge(
        "cherubyte_build_info",
        1,
        help="Panel build, version carried as a label.",
        labels={"version": version},
    )

    # --- devices ---------------------------------------------------------
    total = await session.scalar(select(func.count(Device.id))) or 0
    online = await session.scalar(
        select(func.count(Device.id)).where(Device.is_online.is_(True))
    ) or 0
    pending = await session.scalar(
        select(func.count(Device.id)).where(
            Device.approval_status == ApprovalStatus.pending
        )
    ) or 0
    m.gauge("cherubyte_devices", total, help="Devices known to the panel.")
    m.gauge("cherubyte_devices_online", online, help="Devices currently online.")
    m.gauge(
        "cherubyte_devices_pending",
        pending,
        help="Devices awaiting approval in the review queue.",
    )

    by_type = await session.execute(
        select(Device.device_type, func.count(Device.id)).group_by(Device.device_type)
    )
    for dtype, count in by_type:
        name = dtype.value if isinstance(dtype, DeviceType) else str(dtype)
        m.gauge(
            "cherubyte_devices_by_type",
            count,
            help="Devices by classified type.",
            labels={"type": name},
        )

    # --- people / presence ---------------------------------------------
    people = await session.scalar(
        select(func.count(User.id)).where(User.is_guest.is_(False))
    ) or 0
    m.gauge("cherubyte_people", people, help="Non-guest people.")

    named = (
        await session.execute(
            select(User.id, User.name).where(User.is_guest.is_(False))
        )
    ).all()
    present_ids = set(
        (
            await session.execute(
                select(Device.user_id)
                .where(
                    Device.user_id.is_not(None),
                    Device.is_online.is_(True),
                    Device.counts_for_presence.is_(True),
                )
                .distinct()
            )
        ).scalars()
    )
    present_count = 0
    for uid, name in named:
        is_present = 1 if uid in present_ids else 0
        present_count += is_present
        m.gauge(
            "cherubyte_person_present",
            is_present,
            help="1 when a person has a presence-counting device online.",
            labels={"person": name},
        )
    m.gauge(
        "cherubyte_people_present",
        present_count,
        help="People currently counted as present.",
    )

    # --- agents --------------------------------------------------------
    agents = (
        await session.execute(select(Agent).where(Agent.enabled.is_(True)))
    ).scalars().all()
    m.gauge("cherubyte_agents", len(agents), help="Enabled scanning agents.")
    stale_after = max(180.0, 3.0 * settings.scan_interval_seconds)
    for agent in agents:
        labels = {"agent": agent.name}
        epoch = _epoch(agent.last_seen)
        fresh = epoch is not None and (now.timestamp() - epoch) <= stale_after
        m.gauge(
            "cherubyte_agent_up",
            1 if fresh else 0,
            help="1 when the agent reported within 3 scan intervals.",
            labels={**labels, "version": agent.version or ""},
        )
        if epoch is not None:
            m.gauge(
                "cherubyte_agent_last_report_timestamp_seconds",
                epoch,
                help="Unix time of the agent's last report.",
                labels=labels,
            )
        m.gauge(
            "cherubyte_agent_last_hosts",
            agent.last_hosts or 0,
            help="Hosts in the agent's last report.",
            labels=labels,
        )
        m.gauge(
            "cherubyte_agent_healthy",
            1 if agent.last_healthy else 0,
            help="1 when the agent's last sweep was not degraded.",
            labels=labels,
        )

    # --- host temperature -------------------------------------------
    agent_names = {a.id: a.name for a in agents}
    recent_temps = (
        await session.execute(
            select(HostTempSample)
            .where(HostTempSample.timestamp >= now - timedelta(minutes=15))
            .order_by(HostTempSample.timestamp.desc())
        )
    ).scalars().all()
    seen_hosts: set[int | None] = set()
    for sample in recent_temps:
        if sample.agent_id in seen_hosts:
            continue
        seen_hosts.add(sample.agent_id)
        host = "panel" if sample.agent_id is None else agent_names.get(sample.agent_id, str(sample.agent_id))
        m.gauge(
            "cherubyte_host_temperature_celsius",
            sample.temp_c,
            help="Most recent CPU/SoC temperature of a panel/agent host, °C.",
            labels={"host": host},
        )

    # --- internet -----------------------------------------------------
    last_wan = (
        await session.execute(
            select(WanSample).order_by(WanSample.timestamp.desc()).limit(1)
        )
    ).scalars().first()
    if last_wan is not None:
        m.gauge(
            "cherubyte_wan_up",
            1 if last_wan.ok else 0,
            help="1 when the last internet probe succeeded.",
        )
        if last_wan.latency_ms is not None:
            m.gauge(
                "cherubyte_wan_latency_ms",
                last_wan.latency_ms,
                help="Latency of the last successful internet probe, ms.",
            )
    since = now - timedelta(hours=24)
    day_samples = (
        await session.execute(
            select(WanSample.ok).where(WanSample.timestamp >= since)
        )
    ).scalars().all()
    if day_samples:
        up = sum(1 for ok in day_samples if ok)
        m.gauge(
            "cherubyte_wan_uptime_ratio",
            up / len(day_samples),
            help="Fraction of successful internet probes in the last 24h.",
        )

    # --- events -----------------------------------------------------
    by_level: dict[str, int] = {}
    for level, count in (
        await session.execute(
            select(Event.level, func.count(Event.id)).group_by(Event.level)
        )
    ).all():
        key = level.value if isinstance(level, EventLevel) else str(level)
        by_level[key] = count
    for level in EventLevel:
        m.counter(
            "cherubyte_events_created_total",
            by_level.get(level.value, 0),
            help="Events logged, by level (subject to history retention).",
            labels={"level": level.value},
        )

    return m.render()
