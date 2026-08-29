"""Passive DHCP fingerprinting.

Runs a background sniffer for the life of the service, capturing DHCP
DISCOVER/REQUEST packets (broadcast, so no promiscuous mode needed) and keeping
the latest fingerprint per MAC:

  * option 55  -> Parameter Request List  (the actual "DHCP fingerprint")
  * option 60  -> Vendor Class Identifier
  * option 12  -> hostname the client asked for

Needs CAP_NET_RAW (same as the ARP scan).
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger("netscan.dhcp")


@dataclass
class DhcpFingerprint:
    mac: str
    param_list: str = ""            # e.g. "1,3,6,15,31,33,43,44,46,47,121,249,252"
    vendor_class: str | None = None
    requested_hostname: str | None = None
    last_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


_prints: dict[str, DhcpFingerprint] = {}
_sniffer = None
_lock = threading.Lock()


def get(mac: str) -> DhcpFingerprint | None:
    return _prints.get(mac.lower())


def all_fingerprints() -> dict[str, DhcpFingerprint]:
    return dict(_prints)


def _handle(pkt) -> None:
    try:
        from scapy.all import DHCP, Ether

        if DHCP not in pkt:
            return
        mac = pkt[Ether].src.lower() if Ether in pkt else None
        opts = {}
        for opt in pkt[DHCP].options:
            if isinstance(opt, tuple) and len(opt) >= 2:
                opts[opt[0]] = opt[1]

        msg_type = opts.get("message-type")
        if msg_type not in (1, 3):  # DISCOVER / REQUEST
            return

        prl = opts.get("param_req_list")
        param_list = (
            ",".join(str(x) for x in prl) if isinstance(prl, (list, tuple, bytes)) else ""
        )
        if isinstance(prl, bytes):
            param_list = ",".join(str(b) for b in prl)

        vendor = opts.get("vendor_class_id")
        if isinstance(vendor, bytes):
            vendor = vendor.decode("utf-8", "ignore")
        hostname = opts.get("hostname")
        if isinstance(hostname, bytes):
            hostname = hostname.decode("utf-8", "ignore")

        if not mac:
            return
        with _lock:
            _prints[mac] = DhcpFingerprint(
                mac=mac,
                param_list=param_list,
                vendor_class=vendor or None,
                requested_hostname=hostname or None,
            )
        logger.debug("DHCP fp %s prl=%s vci=%s", mac, param_list, vendor)
    except Exception as exc:  # noqa: BLE001
        logger.debug("DHCP parse error: %s", exc)


def start() -> None:
    global _sniffer
    if _sniffer is not None:
        return
    try:
        from scapy.all import AsyncSniffer

        _sniffer = AsyncSniffer(
            filter="udp and (port 67 or port 68)", store=False, prn=_handle
        )
        _sniffer.start()
        logger.info("DHCP sniffer started")
    except Exception as exc:  # noqa: BLE001
        logger.warning("DHCP sniffer could not start: %s", exc)
        _sniffer = None


def stop() -> None:
    global _sniffer
    if _sniffer is not None:
        try:
            _sniffer.stop()
        except Exception:  # noqa: BLE001
            pass
        _sniffer = None
