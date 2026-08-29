#!/usr/bin/env python3
"""Entrypoint for the NetScan agent.

Needs CAP_NET_RAW for the ARP sweep and the DHCP sniffer, and host networking
to see the LAN at all — see the Docker section of the README.
"""

from __future__ import annotations

import uvicorn

from netscan_agent.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "netscan_agent.main:app", host=settings.health_host, port=settings.health_port
    )
