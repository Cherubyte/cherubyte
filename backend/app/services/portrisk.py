"""Ports worth flagging when they open on a device.

Not "vulnerable" — *exposed*. A database or a remote-desktop port answering on
the LAN is a standing risk whoever is behind it: an open Redis has no password by
default, Telnet has no encryption at all, an open Docker API is root on the host.

When one of these opens on a known device the panel raises a `risky_port` alert
on top of the ordinary port-change notice, and the device page marks it. The
operator can silence individual ports with `risky_ports_ignore`.
"""

from __future__ import annotations

from ..config import settings

# port -> a short reason, shown in the alert and on the device page
RISKY_PORTS: dict[int, str] = {
    21: "FTP — login and files in the clear",
    23: "Telnet — unencrypted remote shell",
    111: "rpcbind — RPC portmapper, an amplification vector",
    135: "MSRPC — Windows RPC, a remote-exec surface",
    139: "NetBIOS — legacy SMB, often unauthenticated",
    389: "LDAP — directory, often unauthenticated",
    445: "SMB — file shares, the classic ransomware path",
    512: "rexec — remote execution, no real auth",
    513: "rlogin — remote login, no real auth",
    514: "rsh — remote shell, no real auth",
    623: "IPMI — out-of-band management, weak by default",
    1433: "MS SQL Server — a database on the network",
    1900: "SSDP / UPnP — amplification, and it leaks the device model",
    2049: "NFS — network file shares",
    2375: "Docker API — unauthenticated is root on the host",
    3306: "MySQL / MariaDB — a database on the network",
    3389: "RDP — remote desktop, a brute-force target",
    5432: "PostgreSQL — a database on the network",
    5900: "VNC — remote desktop, often with no password",
    5985: "WinRM — Windows remote management",
    6379: "Redis — no authentication by default",
    9200: "Elasticsearch — no authentication by default",
    11211: "Memcached — no auth, an amplification vector",
    27017: "MongoDB — no authentication by default",
}


def _ignored() -> set[int]:
    out: set[int] = set()
    for chunk in (settings.risky_ports_ignore or "").replace(";", ",").split(","):
        chunk = chunk.strip()
        if chunk.isdigit():
            out.add(int(chunk))
    return out


def risk_for(port: int) -> str | None:
    """The reason `port` is risky, or None (unknown or operator-ignored)."""
    if port in _ignored():
        return None
    return RISKY_PORTS.get(port)


def risky(ports) -> list[tuple[int, str]]:
    """`[(port, reason), …]` for the risky ones among `ports`, in port order."""
    return [(p, r) for p in sorted(ports) if (r := risk_for(p))]
