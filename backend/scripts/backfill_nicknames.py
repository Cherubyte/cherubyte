#!/usr/bin/env python3
"""One-shot: enrich the devices already in the DB and give each a nickname.

Runs the same identity probes as a live scan (mDNS / SSDP / NetBIOS / reverse-DNS
/ HTTP banner) against every known device IP — no ARP, so no raw sockets needed —
then fills `Device.name` (the nickname) from the best label we can derive.

    backend/.venv/bin/python backend/scripts/backfill_nicknames.py [--force] [--dry-run]

--force overwrites nicknames that are already set; default only fills empty ones.
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.orm import selectinload

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from app.database import SessionLocal, init_db  # noqa: E402
from app.models import Device, DeviceType  # noqa: E402
from app.services import discovery  # noqa: E402
from app.services.enrichment import ICON_FOR_TYPE, classify  # noqa: E402
from app.services.oui import vendor_for  # noqa: E402
from app.services.scanner import Host, _reverse_dns  # noqa: E402


async def main(force: bool, dry: bool) -> None:
    await init_db()

    print("· mDNS / DNS-SD …", flush=True)
    mdns = discovery.mdns_scan(6.0)
    print("· SSDP / UPnP …", flush=True)
    ssdp = discovery.ssdp_scan(3.0)

    async with SessionLocal() as session:
        devices = (
            await session.execute(
                select(Device).options(
                    selectinload(Device.ips),
                    selectinload(Device.macs),
                    selectinload(Device.open_ports),
                )
            )
        ).scalars().all()

        changed = 0
        for d in devices:
            ip = (d.ips[0].address if d.ips else None)
            if not ip:
                continue
            mac = d.macs[0].address if d.macs else ""
            h = Host(mac=mac, ip=ip)
            h.hostname = _reverse_dns(ip)
            h.netbios_name = discovery.netbios_name(ip, timeout=1.0)
            banner = discovery.http_banner(ip)
            if banner:
                h.http_server = banner.http_server
                if banner.names:
                    h.http_title = banner.names[0]

            m = mdns.get(ip)
            if m:
                h.mdns_name = m.names[0] if m.names else None
                h.mdns_model = m.model
                h.mdns_services = sorted(m.services)
                h.ssdp_vendor = m.vendor
            sd = ssdp.get(ip)
            if sd:
                h.ssdp_name = sd.names[0] if sd.names else None
                h.ssdp_vendor = h.ssdp_vendor or sd.vendor
                h.ssdp_model = sd.model

            oui = await vendor_for(mac) if mac else None
            eff_vendor = oui or h.ssdp_vendor or d.vendor
            eff_model = h.best_model or d.model
            eff_name = h.best_name

            if eff_name:
                d.hostname = eff_name
            if eff_vendor:
                d.vendor = eff_vendor
            if eff_model and not d.model:
                d.model = eff_model

            ports = {p.port: (p.service or "") for p in d.open_ports}
            new_type = classify(
                eff_vendor,
                eff_name or d.hostname,
                ports,
                mdns_services=h.mdns_services,
                http_server=h.http_server,
                model=eff_model,
            )
            if d.device_type == DeviceType.unknown and new_type != DeviceType.unknown:
                d.device_type = new_type
                d.icon = ICON_FOR_TYPE.get(new_type)

            if force or not d.name:
                label = d.default_label
                if label and label != d.name:
                    d.name = label
                    changed += 1

            print(
                f"  {ip:<15} {d.name or d.default_label:<28} "
                f"[{d.device_type.value}] {d.vendor or '—'}"
                f"{' / ' + d.model if d.model else ''}"
            )

        if dry:
            print(f"\n(dry-run) {changed} nickname(s) would change")
            return
        await session.commit()
        print(f"\n✓ {changed} nickname(s) definidos, {len(devices)} dispositivos revistos")


if __name__ == "__main__":
    asyncio.run(
        main(force="--force" in sys.argv, dry="--dry-run" in sys.argv)
    )
