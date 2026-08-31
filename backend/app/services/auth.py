"""Password hashing and opaque login sessions.

No third-party dependency: the hash is PBKDF2-HMAC-SHA256 from the stdlib and a
session is a random token looked up in `auth_sessions`. The cookie carries only
the token, so logout is a row delete and expiry is a timestamp check.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Account, AuthSession, utcnow

COOKIE_NAME = "cherubyte_session"
SESSION_TTL = timedelta(days=30)

_PBKDF2_ROUNDS = 600_000
_ALGO = "pbkdf2_sha256"


# --- passwords -------------------------------------------------------------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ROUNDS)
    return f"{_ALGO}${_PBKDF2_ROUNDS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, rounds, salt_hex, dk_hex = stored.split("$")
        if algo != _ALGO:
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(dk.hex(), dk_hex)


# --- brute-force throttle (per username, in memory) ------------------------

_MAX_FAILURES = 5
_LOCKOUT_SECONDS = 60
_failures: dict[str, list[float]] = {}


def is_locked_out(username: str) -> bool:
    hits = [t for t in _failures.get(username, []) if time.time() - t < _LOCKOUT_SECONDS]
    _failures[username] = hits
    return len(hits) >= _MAX_FAILURES


def note_failure(username: str) -> None:
    _failures.setdefault(username, []).append(time.time())


def clear_failures(username: str) -> None:
    _failures.pop(username, None)


# --- sessions -------------------------------------------------------------

async def count_accounts(session: AsyncSession) -> int:
    return int((await session.execute(select(func.count(Account.id)))).scalar_one())


async def create_session(
    session: AsyncSession, account: Account, user_agent: str | None
) -> AuthSession:
    row = AuthSession(
        token=secrets.token_hex(32),
        account_id=account.id,
        expires_at=utcnow() + SESSION_TTL,
        user_agent=(user_agent or "")[:255] or None,
    )
    session.add(row)
    account.last_login = utcnow()
    return row


async def account_for_token(session: AsyncSession, token: str) -> Account | None:
    if not token:
        return None
    row = await session.get(AuthSession, token)
    if row is None:
        return None
    now = utcnow()
    expires = row.expires_at
    if expires.tzinfo is None:
        from datetime import timezone

        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= now:
        await session.delete(row)
        return None
    # slide the window when it is more than half-spent
    if expires - now < SESSION_TTL / 2:
        row.expires_at = now + SESSION_TTL
    return await session.get(Account, row.account_id)


async def destroy_session(session: AsyncSession, token: str) -> None:
    if not token:
        return
    row = await session.get(AuthSession, token)
    if row is not None:
        await session.delete(row)
