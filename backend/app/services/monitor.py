"""Reconciles scan results into the database and raises events / notifications."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..config import settings
from ..database import SessionLocal
from ..models import (
    ApprovalStatus,
    ConnectionHistory,
    Device,
    DeviceType,
    Event,
    EventLevel,
    IpAddress,
    MacAddress,
    OpenPort,
    utcnow,
)
from netscan_protocol import AgentReport, HostObservation

from . import action_tokens, fingerbank, mqtt, notify
from .enrichment import ICON_FOR_TYPE, classify
from .oui import is_locally_administered, vendor_for
from .naming import best_model, best_name

logger = logging.getLogger("netscan.monitor")


def _from_dhcp_hostname(name: str | None) -> str | None:
    if not name:
        return None
    n = name.strip().rstrip(".")
    low = n.lower()
    if not n or low in {"localhost", "unknown"} or low.startswith(("android-", "dhcp")):
        return None
    return n


def _resolve_os(
    ttl_hint: str | None,
    vendor: str | None,
    mdns_services: list[str] | None,
    name: str | None,
) -> str | None:
    if ttl_hint in ("Windows", "embedded"):
        return "Windows" if ttl_hint == "Windows" else None
    if ttl_hint != "unix":
        return None
    v = (vendor or "").lower()
    services = " ".join(mdns_services or []).lower()
    n = (name or "").lower()
    if "apple" in v:
        if any(k in n for k in ("iphone",)) or "phone" in n:
            return "iOS"
        if "ipad" in n:
            return "iPadOS"
        if any(k in n for k in ("macbook", "imac", "mac ", "mac-")) or "_smb" in services:
            return "macOS"
        if "appletv" in n or "apple tv" in n or "_airplay" in services:
            return "tvOS"
        return "Apple OS"
    if "android" in n or "_androidtvremote" in services:
        return "Android"
    if any(k in v for k in ("raspberry", "synology", "qnap")):
        return "Linux"
    return "Linux / Unix"


def _os_from_vendor_class(vci: str | None) -> str | None:
    if not vci:
        return None
    v = vci.lower()
    if "msft" in v or "windows" in v:
        return "Windows"
    if "android" in v:
        return "Android"
    if "dhcpcd" in v or "udhcp" in v:
        return "Linux"
    if v.startswith("aastra") or "voip" in v:
        return None
    return None


def _refine_type_from_os(dtype: "DeviceType", os_guess: str | None, vci: str | None) -> "DeviceType":
    if dtype != DeviceType.unknown:
        return dtype
    o = (os_guess or "").lower()
    if "windows" in o:
        return DeviceType.pc
    if "android" in o or "ios" in o:
        return DeviceType.phone
    if (vci or "").lower().startswith("msft"):
        return DeviceType.pc
    return dtype

# Per-device notification cooldown. A device with flaky Wi-Fi can bounce
# online/offline every cycle; without this each bounce fans out to Telegram and
# ntfy. Keyed by (kind, device_id) -> last time it was sent.
_last_notified: dict[tuple[str, int], datetime] = {}


def _notify_allowed(kind: str, device_id: int) -> bool:
    """True when this notice hasn't been sent for this device recently."""
    cooldown = settings.notify_cooldown_seconds
    if cooldown <= 0:
        return True
    now = utcnow()
    last = _last_notified.get((kind, device_id))
    if last is not None and (now - last).total_seconds() < cooldown:
        logger.debug("notification %s for device %s suppressed (cooldown)", kind, device_id)
        return False
    _last_notified[(kind, device_id)] = now
    return True


def reset_notification_cooldowns() -> None:
    _last_notified.clear()


async def _device_notify(
    kind: str, device: Device, title: str, lines: list[str], **kw
) -> dict[str, bool]:
    """Send a join/leave notice honouring the device's per-device override.

    "mute" silences it; "always" pushes it past a globally-disabled rule;
    "default" is the normal policy path. The cooldown always applies.
    """
    policy = getattr(device, "notify_policy", "default") or "default"
    if policy == "mute":
        return {}
    if not _notify_allowed(kind, device.id):
        return {}
    return await notify.broadcast(
        kind, title, lines, force=(policy == "always"), **kw
    )


# in-memory pub/sub for SSE clients
_subscribers: set = set()


def subscribe() -> "object":
    import asyncio

    q: asyncio.Queue = asyncio.Queue()
    _subscribers.add(q)
    return q


def unsubscribe(q) -> None:
    _subscribers.discard(q)


def _emit(kind: str, payload: dict | None = None) -> None:
    for q in list(_subscribers):
        try:
            q.put_nowait({"type": kind, "data": payload or {}})
        except Exception:  # noqa: BLE001
            pass


# While reconciling a report we buffer SSE events instead of sending them: a
# "device_new" that reaches the browser before the transaction commits makes the
# client refetch /api/devices and *not* see the device — it then only appears on
# the next poll. `_batch_publish()` holds the events until after the commit.
_deferred: ContextVar[list[tuple[str, dict | None]] | None] = ContextVar(
    "monitor_deferred", default=None
)


def _publish(kind: str, payload: dict | None = None) -> None:
    buf = _deferred.get()
    if buf is not None:
        buf.append((kind, payload))
    else:
        _emit(kind, payload)


@contextmanager
def _batch_publish():
    """Collect _publish() calls and flush them on exit — call so the flush lands
    after the DB commit."""
    buf: list[tuple[str, dict | None]] = []
    token = _deferred.set(buf)
    try:
        yield
    finally:
        _deferred.reset(token)
    for kind, payload in buf:
        _emit(kind, payload)


async def _log_event(
    session: AsyncSession,
    message: str,
    *,
    level: EventLevel = EventLevel.info,
    category: str = "system",
    device_id: int | None = None,
) -> None:
    session.add(
        Event(message=message, level=level, category=category, device_id=device_id)
    )
    logger.info("[event/%s] %s", level.value, message)


async def _find_device_by_mac(session: AsyncSession, mac: str) -> Device | None:
    res = await session.execute(
        select(Device)
        .join(MacAddress)
        .where(MacAddress.address == mac)
        .options(
            selectinload(Device.macs),
            selectinload(Device.ips),
            selectinload(Device.open_ports),
        )
    )
    return res.scalars().first()


async def _reconcile_host(
    session: AsyncSession, host: HostObservation, is_gateway: bool
) -> None:
    now = utcnow()
    mac = host.mac.lower()
    vendor = await vendor_for(mac)
    device = await _find_device_by_mac(session, mac)
    is_new = device is None

    # fall back to what we already know (MAC randomisation hides the live vendor)
    eff_vendor = vendor or host.ssdp_vendor or (device.vendor if device else None)
    eff_model = best_model(host) or (device.model if device else None)
    eff_name = (
        best_name(host)
        or _from_dhcp_hostname(host.dhcp_hostname)
        or (device.hostname if device else None)
    )
    os_guess = _resolve_os(
        host.ttl_os, eff_vendor, host.mdns_services, f"{eff_name or ''} {eff_model or ''}"
    )

    # Fingerbank (optional) — richest signal when a DHCP fingerprint is available
    if host.dhcp_param_list and fingerbank.is_enabled():
        fb = await fingerbank.lookup(
            host.dhcp_param_list,
            mac=mac,
            hostname=host.dhcp_hostname or eff_name,
            vendor_class=host.dhcp_vendor_class,
        )
        if fb:
            if fb.get("os"):
                os_guess = fb["os"]
            if fb.get("name") and not eff_model:
                eff_model = fb["name"]

    os_guess = os_guess or _os_from_vendor_class(host.dhcp_vendor_class)

    dtype = classify(
        eff_vendor,
        eff_name or host.hostname,
        host.open_ports,
        is_gateway,
        mdns_services=host.mdns_services,
        http_server=host.http_server,
        model=eff_model,
    )
    dtype = _refine_type_from_os(dtype, os_guess, host.dhcp_vendor_class)

    if is_new:
        device = Device(
            hostname=eff_name,
            vendor=eff_vendor,
            model=eff_model,
            os_guess=os_guess,
            device_type=dtype,
            icon=ICON_FOR_TYPE.get(dtype),
            approval_status=ApprovalStatus.pending,
            is_online=True,
            first_seen=now,
            last_seen=now,
            macs=[
                MacAddress(
                    address=mac,
                    vendor=vendor,
                    is_random=is_locally_administered(mac),
                    first_seen=now,
                    last_seen=now,
                )
            ],
            ips=[],
            open_ports=[],
            images=[],
        )
        session.add(device)
        await session.flush()
    else:
        locked = device.locked_fields  # fields the user pinned — never auto-touch
        for m in device.macs:
            if m.address == mac:
                m.last_seen = now
                if vendor and not m.vendor:
                    m.vendor = vendor
        if eff_name and eff_name != device.hostname:
            device.hostname = eff_name
        if eff_vendor and not device.vendor and "vendor" not in locked:
            device.vendor = eff_vendor
        if eff_model and not device.model and "model" not in locked:
            device.model = eff_model
        if os_guess and os_guess != device.os_guess and "os_guess" not in locked:
            device.os_guess = os_guess
        # keep the type fresh while it's still a weak guess
        _weak = {DeviceType.unknown, DeviceType.pc, DeviceType.server}
        if (
            "device_type" not in locked
            and dtype != DeviceType.unknown
            and dtype != device.device_type
            and device.device_type in _weak
        ):
            device.device_type = dtype
            device.icon = ICON_FOR_TYPE.get(dtype)
        was_online = device.is_online
        device.is_online = True
        device.last_seen = now
        if not was_online:
            session.add(
                ConnectionHistory(device_id=device.id, event="join", ip=host.ip, mac=mac)
            )
            await _log_event(
                session,
                f"{device.display_name} entrou na rede ({host.ip})",
                level=EventLevel.success,
                category="presence",
                device_id=device.id,
            )
            _publish("device_online", {"id": device.id})
            await _device_notify(
                "device_online",
                device,
                "Dispositivo entrou na rede",
                [f"Nome: {device.display_name}", f"IP: {host.ip}", f"MAC: {mac}"],
                emoji="📶",
                tags=["arrow_right"],
                prio=3,
            )

    # IP bookkeeping
    ip_row = next((i for i in device.ips if i.address == host.ip), None)
    if ip_row is None:
        existing = await session.execute(
            select(IpAddress).where(IpAddress.address == host.ip)
        )
        stray = existing.scalars().first()
        if stray is not None:
            previous_owner = stray.device_id
            stray.device_id = device.id
            stray.last_seen = now
            if previous_owner is not None and previous_owner != device.id:
                await _report_ip_takeover(session, device, host, previous_owner)
        else:
            device.ips.append(
                IpAddress(
                    address=host.ip,
                    is_primary=not device.ips,
                    first_seen=now,
                    last_seen=now,
                )
            )
    else:
        ip_row.last_seen = now

    # Ports
    existing_ports = {p.port: p for p in device.open_ports}
    for port, svc in host.open_ports.items():
        if port in existing_ports:
            existing_ports[port].last_seen = now
            existing_ports[port].service = svc
        else:
            device.open_ports.append(OpenPort(port=port, service=svc, last_seen=now))

    # A discovery-only cycle probes no ports, so an empty result there means
    # "not asked", not "all closed" — only diff when the host was identified.
    if host.identified and not is_new:
        opened = sorted(set(host.open_ports) - set(existing_ports))
        closed = sorted(set(existing_ports) - set(host.open_ports))
        for port in closed:
            await session.delete(existing_ports[port])
        if opened or closed:
            await _report_port_change(session, device, host, opened, closed)

    await session.flush()

    if is_new:
        await _reconcile_new_device_notice(session, device, host)


def _describe_ports(ports: list[int], services: dict[int, str]) -> str:
    return ", ".join(f"{p} ({services[p]})" if services.get(p) else str(p) for p in ports)


async def _report_port_change(
    session: AsyncSession,
    device: Device,
    host: HostObservation,
    opened: list[int],
    closed: list[int],
) -> None:
    """A service appearing or disappearing on a known device is worth knowing."""
    parts = []
    if opened:
        parts.append(f"abriu {_describe_ports(opened, host.open_ports)}")
    if closed:
        parts.append(f"fechou {', '.join(str(p) for p in closed)}")
    summary = " e ".join(parts)
    await _log_event(
        session,
        f"{device.display_name} {summary}",
        level=EventLevel.warning if opened else EventLevel.info,
        category="ports",
        device_id=device.id,
    )
    _publish("port_change", {"id": device.id, "opened": opened, "closed": closed})
    if not _notify_allowed("port_change", device.id):
        return
    lines = [f"Dispositivo: {device.display_name}", f"IP: {host.ip}"]
    if opened:
        lines.append(f"Abriu: {_describe_ports(opened, host.open_ports)}")
    if closed:
        lines.append(f"Fechou: {', '.join(str(p) for p in closed)}")
    await notify.broadcast(
        "port_change",
        "Portas mudaram",
        lines,
        emoji="🔌",
        tags=["electric_plug"],
        prio=4 if opened else 3,
    )


async def _report_ip_takeover(
    session: AsyncSession,
    device: Device,
    host: HostObservation,
    previous_owner: int,
) -> None:
    """The same IP moving between devices is normal after a DHCP lease expires,
    and is also what ARP spoofing looks like. Record it either way."""
    previous = await session.get(Device, previous_owner)
    previous_name = previous.display_name if previous else f"dispositivo {previous_owner}"
    await _log_event(
        session,
        f"{host.ip} passou de {previous_name} para {device.display_name}",
        level=EventLevel.warning,
        category="security",
        device_id=device.id,
    )
    _publish("arp_anomaly", {"id": device.id, "ip": host.ip})
    if not _notify_allowed(f"ip_takeover:{host.ip}", device.id):
        return
    await notify.broadcast(
        "arp_anomaly",
        "Endereço IP mudou de dispositivo",
        [
            f"IP: {host.ip}",
            f"Antes: {previous_name}",
            f"Agora: {device.display_name} ({host.mac})",
            "",
            "Normal após uma renovação de DHCP; suspeito se for repetido.",
        ],
        emoji="🛑",
        tags=["rotating_light"],
        prio=5,
    )


async def _reconcile_new_device_notice(
    session: AsyncSession, device: Device, host: HostObservation
) -> None:
    await _log_event(
        session,
        f"Novo dispositivo detetado: {device.display_name} "
        f"({host.ip} / {host.mac}){' — ' + device.vendor if device.vendor else ''}",
        level=EventLevel.warning,
        category="discovery",
        device_id=device.id,
    )
    _publish("device_new", {"id": device.id})
    lines = [
        f"Nome: {device.display_name}",
        f"IP: {host.ip}",
        f"MAC: {host.mac}",
    ]
    if device.vendor:
        lines.append(f"Fabricante: {device.vendor}")
    lines.append(f"Tipo (estimado): {device.device_type.value}")
    lines.append("")
    lines.append("Aprova ou ignora este dispositivo no NetScan.")
    if _notify_allowed("device_new", device.id):
        await notify.broadcast(
            "device_new",
            "Novo dispositivo na rede",
            lines,
            emoji="🆕",
            tags=["new"],
            prio=4,
            actions=_approval_actions(device.id),
        )


async def _expire_offline(session: AsyncSession) -> None:
    cutoff = utcnow() - timedelta(seconds=settings.offline_after_seconds)
    res = await session.execute(
        select(Device)
        .where(Device.is_online.is_(True), Device.last_seen < cutoff)
        .options(selectinload(Device.macs), selectinload(Device.ips))
    )
    for device in res.scalars():
        device.is_online = False
        last_ip = device.ips[0].address if device.ips else None
        last_mac = device.macs[0].address if device.macs else None
        session.add(
            ConnectionHistory(
                device_id=device.id, event="leave", ip=last_ip, mac=last_mac
            )
        )
        await _log_event(
            session,
            f"{device.display_name} saiu da rede",
            level=EventLevel.warning,
            category="presence",
            device_id=device.id,
        )
        _publish("device_offline", {"id": device.id})
        policy = getattr(device, "notify_policy", "default") or "default"
        # "always" / a globally-enabled device_offline rule: a plain leave notice
        await _device_notify(
            "device_offline",
            device,
            "Dispositivo saiu da rede",
            [f"Nome: {device.display_name}", f"MAC: {last_mac or '—'}"],
            emoji="📴",
            tags=["arrow_left"],
            prio=3,
        )
        # the louder "unapproved device left" nag — skipped when the device is
        # muted or already covered by its "always" override just above
        if (
            policy == "default"
            and device.approval_status != ApprovalStatus.approved
            and _notify_allowed("device_left", device.id)
        ):
            await notify.broadcast(
                "device_left",
                "Dispositivo não aprovado saiu da rede",
                [f"Nome: {device.display_name}", f"MAC: {last_mac or '—'}"],
                emoji="⚠️",
                tags=["warning"],
                prio=4,
            )


async def log_event_standalone(
    message: str, *, level: EventLevel = EventLevel.info, category: str = "system"
) -> None:
    """Log an event from code that has no session of its own (e.g. the WAN probe)."""
    async with SessionLocal() as session:
        await _log_event(session, message, level=level, category=category)
        await session.commit()


def publish_event(kind: str, payload: dict | None = None) -> None:
    _publish(kind, payload)


def _approval_actions(device_id: int) -> list[dict]:
    """ntfy buttons that approve or ignore straight from the notification.

    Needs a URL the phone can reach; without one the buttons are pointless, so
    they are simply left out.
    """
    base = (settings.public_base_url or "").rstrip("/")
    if not base:
        return []
    return [
        {
            "action": "http",
            "label": label,
            "method": "POST",
            "url": f"{base}/api/actions/{verb}/{device_id}"
            f"?t={action_tokens.make(verb, device_id)}",
            "clear": True,
        }
        for verb, label in (("approve", "Aprovar"), ("ignore", "Ignorar"))
    ]


# Last MAC seen answering for each gateway IP. The gateway's MAC changing under
# a live session is the classic ARP-spoofing signature; it also happens when the
# router is genuinely replaced, so this reports rather than blocks.
_gateway_macs: dict[str, str] = {}
# Last state pushed to MQTT, so a cycle only publishes what actually changed.
_mqtt_last: dict[str, str] = {}
# DHCP servers already reported, so an unexpected one alerts once, not per cycle.
_known_dhcp: set[str] = set()


def reset_watch_state() -> None:
    _gateway_macs.clear()
    _mqtt_last.clear()
    _known_dhcp.clear()


def _dhcp_allowlist() -> set[str]:
    raw = (settings.dhcp_allowlist or "").replace(";", ",").replace(" ", ",")
    return {p.strip().lower() for p in raw.split(",") if p.strip()}


async def _check_dhcp_servers(servers, gateways: set[str]) -> None:
    """Flag a DHCP server that is neither the gateway nor on the allowlist.

    A second DHCP server on a LAN hands out its own gateway and DNS to whichever
    client races to it first — a misconfigured spare router, or an attacker. The
    passive sniffer sees the OFFER/ACK; the panel decides it is unexpected.
    """
    allow = _dhcp_allowlist()
    for s in servers:
        ip = (s.ip or "").strip()
        if not ip or ip in _known_dhcp:
            continue
        _known_dhcp.add(ip)
        mac = (s.mac or "").lower()
        if ip in gateways or ip.lower() in allow or (mac and mac in allow):
            continue
        logger.warning("unexpected DHCP server %s (%s)", ip, mac or "?")
        await log_event_standalone(
            f"Servidor DHCP não autorizado a responder na rede: {ip}"
            + (f" ({mac})" if mac else ""),
            level=EventLevel.alert,
            category="security",
        )
        _publish("rogue_dhcp", {"ip": ip, "mac": mac or None})
        await notify.broadcast(
            "rogue_dhcp",
            "Servidor DHCP não autorizado",
            [
                f"IP: {ip}",
                f"MAC: {mac or '—'}",
                "",
                "Não é o gateway conhecido nem está na lista de permitidos.",
                "Um segundo servidor DHCP entrega configuração de rede a quem "
                "responder primeiro — pode ser um router a mais ou um ataque.",
            ],
            emoji="🛑",
            tags=["rotating_light"],
            prio=5,
        )


async def _check_gateway_mac(
    hosts: list[HostObservation], gateways: set[str]
) -> None:
    for host in hosts:
        if host.ip not in gateways:
            continue
        previous = _gateway_macs.get(host.ip)
        _gateway_macs[host.ip] = host.mac
        if previous is None or previous == host.mac:
            continue
        logger.warning("gateway %s changed MAC %s -> %s", host.ip, previous, host.mac)
        await log_event_standalone(
            f"O MAC do gateway {host.ip} mudou de {previous} para {host.mac}",
            level=EventLevel.alert,
            category="security",
        )
        _publish("arp_anomaly", {"ip": host.ip, "mac": host.mac})
        await notify.broadcast(
            "arp_anomaly",
            "MAC do gateway mudou",
            [
                f"Gateway: {host.ip}",
                f"Antes: {previous}",
                f"Agora: {host.mac}",
                "",
                "Se não trocaste de router, isto pode ser ARP spoofing.",
            ],
            emoji="🛑",
            tags=["rotating_light"],
            prio=5,
        )


async def _publish_mqtt_state(session: AsyncSession) -> None:
    """Push device and per-user presence to MQTT, changes only."""
    if not mqtt.is_configured():
        return
    res = await session.execute(select(Device).options(selectinload(Device.user)))
    devices = list(res.scalars().unique())

    for device in devices:
        key = f"device:{device.id}"
        state = "ON" if device.is_online else "OFF"
        if _mqtt_last.get(key) != state:
            mqtt.publish_device_state(device.id, device.display_name, device.is_online)
            _mqtt_last[key] = state

    present: dict[int, tuple[str, bool]] = {}
    for device in devices:
        if device.user is None or not device.counts_for_presence:
            continue
        name, was = present.get(device.user_id, (device.user.name, False))
        present[device.user_id] = (name, was or device.is_online)

    for user_id, (name, is_present) in present.items():
        key = f"user:{user_id}"
        state = "home" if is_present else "not_home"
        if _mqtt_last.get(key) != state:
            mqtt.publish_user_presence(user_id, name, is_present)
            _mqtt_last[key] = state


# A healthy sweep always finds at least the machine we run on, so an empty
# result means the scan itself is broken (interface down, capabilities lost) —
# not that the network emptied. Expiring devices on such a cycle would mark
# every device offline at once and fan out a notification per device.
_scan_health: dict[str, int] = {"consecutive_empty": 0}


def reset_scan_health() -> None:
    _scan_health["consecutive_empty"] = 0


async def ingest_report(report: AgentReport, agent_name: str = "agent") -> dict:
    """Reconcile one agent report into the database.

    This is what `run_scan_cycle` used to be, with the sweep taken out: the
    panel no longer looks at a network, it reads what an agent saw on one. The
    reconciliation below is unchanged, which is the point — moving the sweep
    across a wire must not change what the panel concludes from it.
    """
    subnets = [c for c in report.subnets if c]
    subnet = subnets[0] if subnets else ""

    if not report.healthy or not report.hosts:
        first_empty = _scan_health["consecutive_empty"] == 0
        _scan_health["consecutive_empty"] += 1
        logger.warning(
            "Agent %s reported a degraded sweep (%dx in a row) — skipping offline expiry",
            agent_name,
            _scan_health["consecutive_empty"],
        )
        if first_empty:  # log the transition only, not every cycle
            async with SessionLocal() as session:
                await _log_event(
                    session,
                    f"O agente {agent_name} não encontrou nenhum dispositivo — "
                    "verifica a interface de rede e as permissões. "
                    "Estado dos dispositivos mantido.",
                    level=EventLevel.alert,
                    category="scan",
                )
                await session.commit()
            await notify.broadcast(
                "scan_degraded",
                "Scan não encontrou nenhum dispositivo",
                [
                    f"Agente: {agent_name}",
                    "Nem sequer a própria máquina do agente respondeu.",
                    "Verifica a interface de rede e as permissões (CAP_NET_RAW).",
                    "",
                    "O estado dos dispositivos foi mantido.",
                ],
                emoji="🛑",
                tags=["rotating_light"],
                prio=5,
            )
        _publish("scan_empty", {"subnet": subnet, "agent": agent_name})
        return {"ok": True, "found": 0, "subnet": subnet, "degraded": True}

    _scan_health["consecutive_empty"] = 0

    # Heuristic: the .1 of each swept subnet is usually its gateway.
    gateways = {
        f"{c.split('/')[0].rsplit('.', 1)[0]}.1" for c in subnets if "/" in c
    }

    await _check_gateway_mac(report.hosts, gateways)
    await _check_dhcp_servers(report.dhcp_servers, gateways)

    # Buffer the SSE events raised during reconciliation and let them out only
    # once the block exits — i.e. after the commit below — so a client that
    # reacts to "device_new" sees the device when it refetches.
    with _batch_publish():
        async with SessionLocal() as session:
            for host in report.hosts:
                await _reconcile_host(session, host, host.ip in gateways)
            await _expire_offline(session)
            await session.commit()
            await _publish_mqtt_state(session)

        _publish("scan_complete", {"found": len(report.hosts), "subnet": subnet})
    logger.info(
        "Ingested %d hosts from agent %s on %s",
        len(report.hosts), agent_name, subnet or "?",
    )
    return {"ok": True, "found": len(report.hosts), "subnet": subnet}
