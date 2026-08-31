"""Bearer tokens for scripts and scrapers.

A token is `nsk_` + 32 URL-safe bytes, shown once. Only its SHA-256 is stored —
same reasoning as the agent keys (`services/agents.py`): high-entropy random, so
a password KDF protects nothing. Tokens authenticate the ordinary API routes but
are pinned to `viewer`, so they can read and nothing else.
"""

from __future__ import annotations

import secrets
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AccountRole, ApiToken, utcnow

PREFIX = "nsk_"


def looks_like_token(value: str) -> bool:
    return value.startswith(PREFIX)


def _hash(token: str) -> str:
    return sha256(token.encode()).hexdigest()


def new_token() -> str:
    return PREFIX + secrets.token_urlsafe(32)


async def create(
    session: AsyncSession, *, name: str, created_by: int | None
) -> tuple[ApiToken, str]:
    token = new_token()
    row = ApiToken(
        name=name.strip()[:120] or "token",
        token_hash=_hash(token),
        role=AccountRole.viewer,
        created_by=created_by,
    )
    session.add(row)
    await session.flush()
    return row, token


async def authenticate(session: AsyncSession, presented: str) -> ApiToken | None:
    """The token row behind this string, or None. Bumps `last_used_at`.

    The lookup is by hash of a 256-bit random value, so there is no guessable
    space a timing side-channel could narrow — a plain indexed match is fine.
    """
    if not looks_like_token(presented):
        return None
    row = (
        await session.execute(
            select(ApiToken).where(ApiToken.token_hash == _hash(presented))
        )
    ).scalars().first()
    if row is not None:
        row.last_used_at = utcnow()
    return row


async def list_all(session: AsyncSession) -> list[ApiToken]:
    return list(
        (
            await session.execute(select(ApiToken).order_by(ApiToken.created_at.desc()))
        ).scalars()
    )


async def revoke(session: AsyncSession, token_id: int) -> bool:
    row = await session.get(ApiToken, token_id)
    if row is None:
        return False
    await session.delete(row)
    return True
