"""Reach an agent's trigger port directly, when the panel can.

The panel never sits on a monitored network, but the common single-box install
puts the agent one hop away — so when the panel has an address for it, a queued
sweep or on-demand probe can start in seconds instead of waiting out the
agent's report interval. Every failure falls through silently: the caller also
sets `scan_requested`, so the agent still picks the work up on its next
check-in.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from ..models import Agent

logger = logging.getLogger("cherubyte.agent_nudge")


async def poke(agent: Agent) -> bool:
    """Ask one agent to run a cycle now, directly. True if it accepted."""
    if not agent.last_ip:
        return False
    url = f"http://{agent.last_ip}:{agent.health_port or 1002}/trigger"
    try:
        async with httpx.AsyncClient(timeout=2.5) as client:
            r = await client.post(url)
        return r.status_code < 400
    except Exception as exc:  # noqa: BLE001
        logger.info("Could not reach agent %s at %s: %s", agent.id, url, exc)
        return False


async def poke_all(agents: list[Agent]) -> list[bool]:
    """Poke every agent concurrently; one bool per agent, in order."""
    if not agents:
        return []
    return list(await asyncio.gather(*(poke(a) for a in agents)))
