"""Admitting agents, and checking the ones that come back.

An agent is a machine client: it cannot do an interactive login, so it is never
put behind Cloudflare Access. It carries a key instead, issued once in exchange
for a single-use enrolment token.

Fail closed at every step. An unknown key, a disabled agent, a spent token and
an expired token all refuse. There is no path where a missing credential reads
as "allow" — the reason this matters here is that the thing on the other side
of it is a complete inventory of somebody's home network.
"""

from __future__ import annotations

import hmac
import json
import logging
import secrets
from datetime import timedelta
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cherubyte_protocol import AgentConfig

from ..config import settings
from ..models import Agent, EnrolmentToken, utcnow

logger = logging.getLogger("cherubyte.agents")

TOKEN_TTL = timedelta(hours=24)


def hash_secret(value: str) -> str:
    """Hash a key or token for storage.

    A plain SHA-256 rather than a password KDF on purpose: these are 32 bytes
    of `secrets.token_urlsafe`, not something a person chose, so there is no
    guessable space for a slow hash to protect. Never store the original.
    """
    return sha256(value.encode()).hexdigest()


def new_secret() -> str:
    return secrets.token_urlsafe(32)


async def issue_token(session: AsyncSession, label: str | None = None) -> str:
    """Mint an enrolment token. Returned once; only its hash is kept."""
    token = new_secret()
    session.add(
        EnrolmentToken(
            token_hash=hash_secret(token),
            label=label,
            expires_at=utcnow() + TOKEN_TTL,
        )
    )
    return token


async def enrol(
    session: AsyncSession, *, token: str, name: str, version: str = ""
) -> tuple[Agent, str] | None:
    """Spend a token for an agent and its key, or None if the token is no good."""
    row = (
        await session.execute(
            select(EnrolmentToken).where(EnrolmentToken.token_hash == hash_secret(token))
        )
    ).scalars().first()
    if row is None:
        logger.warning("Enrolment refused: unknown token")
        return None
    if row.used_at is not None:
        logger.warning("Enrolment refused: token already spent")
        return None
    if row.expires_at.replace(tzinfo=row.expires_at.tzinfo or utcnow().tzinfo) < utcnow():
        logger.warning("Enrolment refused: token expired")
        return None

    key = new_secret()
    agent = Agent(name=name or "agent", key_hash=hash_secret(key), version=version or None)
    session.add(agent)
    await session.flush()
    row.used_at = utcnow()
    row.used_by_agent_id = agent.id
    logger.info("Agent %s (%s) enrolled", agent.id, agent.name)
    return agent, key


async def authenticate(session: AsyncSession, agent_id: int, key: str) -> Agent | None:
    """The agent behind this id and key, or None. Compared in constant time."""
    if not key:
        return None
    agent = await session.get(Agent, agent_id)
    if agent is None or not agent.enabled:
        return None
    if not hmac.compare_digest(agent.key_hash, hash_secret(key)):
        return None
    return agent


def set_subnets(agent: Agent, subnets: list[str]) -> None:
    agent.subnets = json.dumps(sorted(set(subnets)))


def get_subnets(agent: Agent) -> list[str]:
    if not agent.subnets:
        return []
    try:
        loaded = json.loads(agent.subnets)
    except (ValueError, TypeError):
        return []
    return [c for c in loaded if isinstance(c, str)]


async def known_subnets(session: AsyncSession) -> list[str]:
    """Every CIDR any enabled agent reports sweeping.

    The panel no longer looks at interfaces itself — it does not have any worth
    looking at — so this is where the UI's idea of "the network" comes from.
    """
    rows = (await session.execute(select(Agent).where(Agent.enabled.is_(True)))).scalars()
    out: list[str] = []
    for agent in rows:
        out.extend(get_subnets(agent))
    return sorted(set(out))


def desired_config() -> AgentConfig:
    """The configuration the panel wants its agents to run.

    Read from the panel's own settings, which is where an operator edits them.
    An agent that has never been configured still gets sensible values, because
    these are the same defaults the panel ships with.
    """
    return AgentConfig(
        scan_interval_seconds=settings.scan_interval_seconds,
        identify_interval_seconds=settings.identify_interval_seconds,
        identify_batch=settings.identify_batch,
        full_sweep_interval_seconds=settings.full_sweep_interval_seconds,
        port_probe_concurrency=settings.port_probe_concurrency,
        arp_timeout=settings.arp_timeout,
        enable_reverse_dns=settings.enable_reverse_dns,
        enable_port_probe=settings.enable_port_probe,
        enable_dhcp_sniffer=settings.enable_dhcp_sniffer,
        enable_snmp=settings.enable_snmp,
        snmp_community=settings.snmp_community or "public",
        wan_enabled=settings.wan_enabled,
        wan_target=settings.wan_target or "1.1.1.1",
        subnets=[
            c for c in (
                [s.get("cidr", "") for s in (settings.subnets or [])]
                or ([settings.subnet] if settings.subnet else [])
            ) if c
        ],
    )
