"""Signed, expiring tokens for the action buttons on a notification.

A notification button has to carry its own authority: the phone tapping it is
not logged in, and the app has no sessions. So each button gets an HMAC over
(action, device id, expiry) — enough to approve *that* device from *that*
notice, useless for anything else, and worthless once it expires.

The secret lives in the settings table and is generated on first use.
"""

from __future__ import annotations

import hmac
import secrets
import time
from hashlib import sha256

_secret: str = ""

TTL_SECONDS = 7 * 24 * 3600
ACTIONS = ("approve", "ignore")


def configure(secret: str | None) -> None:
    global _secret
    if secret:
        _secret = secret


def ensure_secret() -> str:
    """The signing secret, creating one the first time it is needed."""
    global _secret
    if not _secret:
        _secret = secrets.token_urlsafe(32)
    return _secret


def _sign(action: str, device_id: int, expires: int) -> str:
    msg = f"{action}:{device_id}:{expires}".encode()
    return hmac.new(ensure_secret().encode(), msg, sha256).hexdigest()[:32]


def make(action: str, device_id: int, *, ttl: int = TTL_SECONDS) -> str:
    expires = int(time.time()) + ttl
    return f"{expires}.{_sign(action, device_id, expires)}"


def verify(action: str, device_id: int, token: str) -> bool:
    if action not in ACTIONS or not token:
        return False
    raw_expires, _, digest = token.partition(".")
    if not digest:
        return False
    try:
        expires = int(raw_expires)
    except ValueError:
        return False
    if expires < time.time():
        return False
    return hmac.compare_digest(digest, _sign(action, device_id, expires))
