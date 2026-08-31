"""Which events notify, on which channel, and when to stay quiet.

Every outgoing notice names an alert kind. The policy decides whether that kind
is enabled at all and which channels it may use; quiet hours then silence the
non-urgent ones. Kinds the policy does not mention fall back to the defaults
below, so adding a new kind never silently disables it.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, time

from ..config import settings

logger = logging.getLogger("netscan.alerts")

CHANNELS = ("telegram", "ntfy")


@dataclass(frozen=True)
class AlertKind:
    key: str
    label: str
    urgent: bool = False       # urgent alerts ignore quiet hours
    default_on: bool = True


KINDS: tuple[AlertKind, ...] = (
    AlertKind("device_new", "Dispositivo novo na rede"),
    AlertKind("device_left", "Dispositivo não aprovado saiu"),
    AlertKind("device_online", "Dispositivo conhecido entrou", default_on=False),
    AlertKind("device_offline", "Dispositivo conhecido saiu", default_on=False),
    AlertKind("port_change", "Portas de um dispositivo mudaram"),
    AlertKind("arp_anomaly", "Anomalia na camada ARP", urgent=True),
    AlertKind("rogue_dhcp", "Servidor DHCP não autorizado", urgent=True),
    AlertKind("fingerprint_change", "Fingerprint de um dispositivo mudou"),
    AlertKind("risky_port", "Porta sensível aberta num dispositivo"),
    AlertKind("wan_down", "Internet em baixo", urgent=True),
    AlertKind("wan_up", "Internet recuperou"),
    AlertKind("scan_degraded", "Scan não encontrou nada", urgent=True),
    AlertKind("weekly_summary", "Resumo semanal", default_on=False),
)

_BY_KEY = {k.key: k for k in KINDS}


def kind(key: str) -> AlertKind:
    return _BY_KEY.get(key) or AlertKind(key, key)


def _policy() -> dict:
    if not settings.alert_policy:
        return {}
    try:
        loaded = json.loads(settings.alert_policy)
        return loaded if isinstance(loaded, dict) else {}
    except (ValueError, TypeError):
        logger.warning("alert_policy is not valid JSON; using defaults")
        return {}


def rule_for(key: str) -> dict:
    """The effective rule for one kind: {enabled: bool, channels: [...]}."""
    entry = _policy().get(key) or {}
    enabled = entry.get("enabled")
    if not isinstance(enabled, bool):
        enabled = kind(key).default_on
    channels = entry.get("channels")
    if not isinstance(channels, list) or not all(isinstance(c, str) for c in channels):
        channels = list(CHANNELS)
    return {"enabled": enabled, "channels": [c for c in channels if c in CHANNELS]}


def effective_policy() -> dict[str, dict]:
    return {k.key: rule_for(k.key) for k in KINDS}


def _parse_hhmm(raw: str) -> time | None:
    try:
        hh, mm = raw.strip().split(":")
        return time(int(hh), int(mm))
    except (ValueError, AttributeError):
        return None


def in_quiet_hours(now: datetime | None = None) -> bool:
    start = _parse_hhmm(settings.quiet_hours_start)
    end = _parse_hhmm(settings.quiet_hours_end)
    if start is None or end is None or start == end:
        return False
    current = (now or datetime.now().astimezone()).time()
    if start < end:
        return start <= current < end
    return current >= start or current < end  # window wraps past midnight


def channels_for(
    key: str, *, now: datetime | None = None, force: bool = False
) -> list[str]:
    """The channels this alert may go out on right now. Empty means stay silent.

    `force` (a per-device "always notify" override) ignores the policy's
    enabled flag, but quiet hours still apply to non-urgent kinds.
    """
    rule = rule_for(key)
    if not rule["enabled"] and not force:
        return []
    if in_quiet_hours(now) and not kind(key).urgent:
        logger.debug("alert %s suppressed by quiet hours", key)
        return []
    return rule["channels"] or (list(CHANNELS) if force else [])
