#!/usr/bin/env python3
"""Entrypoint for the NetScan service (port 1001 by default).

Port 1001 is privileged and ARP scanning needs raw sockets, so the process
needs CAP_NET_BIND_SERVICE + CAP_NET_RAW/ADMIN. Pick one:

  * systemd (recommended, persistent):  ./scripts/install-service.sh
  * capabilities on the venv python:
        sudo setcap 'cap_net_raw,cap_net_admin,cap_net_bind_service+eip' \\
          "$(readlink -f backend/.venv/bin/python)"
  * just run as root:  sudo backend/.venv/bin/python backend/run.py
"""

from __future__ import annotations

import os
import sys

import uvicorn

from app.config import settings


def _warn_if_no_raw_socket() -> None:
    if os.geteuid() == 0:
        return
    try:
        import socket

        s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW)  # type: ignore[attr-defined]
        s.close()
    except (PermissionError, OSError):
        print(
            "[netscan] WARNING: no raw-socket permission — ARP scans will fail.\n"
            "          Run as root or: sudo setcap cap_net_raw,cap_net_admin+eip "
            f"{sys.executable}",
            file=sys.stderr,
        )
    except AttributeError:
        pass


if __name__ == "__main__":
    _warn_if_no_raw_socket()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload="--reload" in sys.argv,
    )
