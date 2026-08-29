"""Internet reachability, probed from where the agent sits.

Only the probe lives here. Storing the samples, drawing the chart and deciding
that a transition is worth waking someone over are the panel's, which is why
this returns a reading rather than writing one anywhere.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import re

import httpx

logger = logging.getLogger("netscan.agent.wan")

_RTT = re.compile(rb"time[=<]\s*([\d.]+)\s*ms")

# Asked in order until one answers. Cloudflare first — it is already the default
# ping target, so it adds no new party to trust; the others are fallbacks for
# networks that block it.
_PUBLIC_IP_SOURCES: tuple[tuple[str, str | None], ...] = (
    ("https://one.one.one.one/cdn-cgi/trace", "ip"),
    ("https://api.ipify.org", None),
    ("https://ifconfig.co/ip", None),
)

_TRACE_IP = re.compile(r"^ip=(.+)$", re.MULTILINE)


def parse_rtt(output: bytes) -> float | None:
    """The round-trip time in ms from `ping` output, or None if absent."""
    match = _RTT.search(output)
    return float(match.group(1)) if match else None


async def probe(target: str, timeout: float = 3.0) -> tuple[bool, float | None]:
    """One ping. Returns (reachable, round-trip in ms).

    Any failure — an unreachable host, a timeout, or no `ping` binary at all —
    reports unreachable rather than raising: this runs on a loop that must not
    stop because the network did.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "ping", "-c", "1", "-W", str(int(max(1, timeout))), "-n", target,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout + 2)
    except (OSError, asyncio.TimeoutError) as exc:
        logger.debug("WAN probe failed: %s", exc)
        return False, None
    if proc.returncode != 0:
        return False, None
    return True, parse_rtt(out or b"")


def _valid_ip(text: str) -> str | None:
    text = text.strip()
    try:
        return str(ipaddress.ip_address(text))
    except ValueError:
        return None


async def public_ip(timeout: float = 4.0) -> str | None:
    """The network's egress address as the internet sees it, or None.

    Every failure — no network, a blocked host, a garbled body — falls through
    to the next source and finally to None: this is a nice-to-have on a loop
    that must not stop because a third party was slow.
    """
    try:
        async with httpx.AsyncClient(
            timeout=timeout, follow_redirects=True, headers={"user-agent": "netscan-agent"}
        ) as client:
            for url, key in _PUBLIC_IP_SOURCES:
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    body = resp.text
                except httpx.HTTPError as exc:
                    logger.debug("public IP source %s failed: %s", url, exc)
                    continue
                if key == "ip":
                    match = _TRACE_IP.search(body)
                    candidate = match.group(1) if match else ""
                else:
                    candidate = body
                ip = _valid_ip(candidate)
                if ip:
                    return ip
                logger.debug("public IP source %s gave no address", url)
    except Exception as exc:  # noqa: BLE001
        logger.debug("public IP lookup failed: %s", exc)
    return None
