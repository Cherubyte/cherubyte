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
from ..models import Agent, DeviceCode, EnrolmentToken, utcnow
from ..tenancy import current_tenant

logger = logging.getLogger("cherubyte.agents")

TOKEN_TTL = timedelta(hours=24)

# Short, because a code is live only for as long as somebody is standing at a
# terminal waiting to approve it. Ten minutes is enough to walk to a browser
# and not much use to anybody else.
DEVICE_CODE_TTL = timedelta(minutes=10)

# No O, 0, I, 1 or similar: this is read off a terminal and typed into a URL
# bar, and a code that needs explaining is a code that gets mistyped.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def hash_secret(value: str) -> str:
    """Hash a key or token for storage.

    A plain SHA-256 rather than a password KDF on purpose: these are 32 bytes
    of `secrets.token_urlsafe`, not something a person chose, so there is no
    guessable space for a slow hash to protect. Never store the original.
    """
    return sha256(value.encode()).hexdigest()


def new_secret() -> str:
    """A fresh key or enrolment token.

    Hosted, it carries the tenant in front — `t.<tenant>.<random>` — so the
    edge can route the agent that presents it without looking anything up.
    Self-hosted there is no tenant and the secret is what it always was. The
    prefix is not entropy and not secret; the 32 random bytes after it are.
    The dot is the one character neither part can contain (see tenancy.py).
    """
    random = secrets.token_urlsafe(32)
    tenant = current_tenant.get()
    return f"t.{tenant}.{random}" if tenant else random


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
        enable_passive_arp=settings.enable_passive_arp,
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


# ── device codes ───────────────────────────────────────────────────────────
#
# The other way in. An enrolment token is a secret the operator carries from
# the panel to the machine, and a secret that travels by copy and paste lands
# in a shell history and a config file that outlive it. Here nothing travels:
# the machine asks, a person approves, and the key is handed to the asker.


def new_code() -> str:
    """A short code for the URL. Grouped for reading aloud."""
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


async def request_device_code(
    session: AsyncSession, *, name: str, version: str = "", source_ip: str = ""
) -> tuple[DeviceCode, str]:
    """Start an enrolment. Returns the row and the poll secret, once.

    The poll secret is the thing that actually collects the key, and it is
    returned here and never again — only its hash is kept. So a person who
    reads the code off somebody's screen can look at an approval page and do
    nothing else.

    Nothing here is authenticated, because the machine has no credential yet.
    That is the point, and it is why the row records where the request came
    from: approving is a human looking at a page and recognising their own
    machine, so the page has to show enough to tell it from a stranger's.
    """
    poll_secret = new_secret()
    row = DeviceCode(
        code=new_code(),
        poll_hash=hash_secret(poll_secret),
        name=(name or "").strip()[:120],
        version=(version or "").strip()[:40] or None,
        source_ip=(source_ip or "").strip()[:45] or None,
        expires_at=utcnow() + DEVICE_CODE_TTL,
    )
    session.add(row)
    await session.flush()
    logger.info("Device code %s requested by %s (%s)", row.code, row.name, row.source_ip)
    return row, poll_secret


async def find_device_code(session: AsyncSession, code: str) -> DeviceCode | None:
    """A live request by its code. Expired and collected ones read as gone."""
    row = (
        await session.execute(select(DeviceCode).where(DeviceCode.code == (code or "").upper()))
    ).scalars().first()
    if row is None or row.collected_at is not None:
        return None
    if _expired(row):
        return None
    return row


def _expired(row: DeviceCode) -> bool:
    expires = row.expires_at
    return expires.replace(tzinfo=expires.tzinfo or utcnow().tzinfo) < utcnow()


async def approve_device_code(
    session: AsyncSession, code: str, *, account_id: int
) -> DeviceCode | None:
    """Say yes to a waiting machine. None when there is nothing to say yes to.

    Approving twice is harmless and keeps the first approval, so a double
    click does not look like a second machine.
    """
    row = await find_device_code(session, code)
    if row is None:
        return None
    if row.approved_at is None:
        row.approved_at = utcnow()
        row.approved_by = account_id
        logger.warning("Account %s approved device code %s (%s)", account_id, row.code, row.name)
    return row


async def collect_device_key(
    session: AsyncSession, *, code: str, poll_secret: str
) -> tuple[Agent, str] | None | str:
    """The agent and its key once approved.

    Returns the pair when it is ready, the string "pending" while it is not,
    and None when there is nothing valid to collect — expired, unknown, wrong
    secret, or already collected. The caller turns those into status codes;
    keeping them apart here is what lets the agent keep polling rather than
    giving up on a request that is simply not approved yet.
    """
    row = (
        await session.execute(select(DeviceCode).where(DeviceCode.code == (code or "").upper()))
    ).scalars().first()
    if row is None or _expired(row) or row.collected_at is not None:
        return None
    # Constant time, and checked before the approval state is revealed: a
    # caller with the code but not the secret learns nothing about whether
    # somebody approved it.
    if not hmac.compare_digest(row.poll_hash, hash_secret(poll_secret or "")):
        logger.warning("Device code %s polled with the wrong secret", row.code)
        return None
    if row.approved_at is None:
        return "pending"

    key = new_secret()
    agent = Agent(
        name=row.name or "agent", key_hash=hash_secret(key), version=row.version or None
    )
    session.add(agent)
    await session.flush()
    row.collected_at = utcnow()
    row.agent_id = agent.id
    logger.info("Agent %s (%s) enrolled by device code %s", agent.id, agent.name, row.code)
    return agent, key


async def pending_device_codes(session: AsyncSession) -> list[DeviceCode]:
    """Requests still waiting, newest first. For the panel to show."""
    rows = (
        await session.execute(
            select(DeviceCode)
            .where(DeviceCode.collected_at.is_(None))
            .order_by(DeviceCode.created_at.desc())
        )
    ).scalars().all()
    return [r for r in rows if not _expired(r)]


async def purge_device_codes(session: AsyncSession) -> int:
    """Delete codes that are spent or long past. Returns how many went.

    Kept for a day after they die rather than deleted on expiry, so somebody
    looking at why an enrolment failed can still see that it was asked for.
    """
    cutoff = utcnow() - timedelta(days=1)
    rows = (await session.execute(select(DeviceCode))).scalars().all()
    gone = 0
    for row in rows:
        created = row.created_at.replace(tzinfo=row.created_at.tzinfo or utcnow().tzinfo)
        if created < cutoff:
            await session.delete(row)
            gone += 1
    return gone
