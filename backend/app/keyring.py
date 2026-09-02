"""Where the encryption keys come from, and why they are not on this box.

A key next to the data it protects is a lock with the key in it. The point of
fetching from a service is not that the panel never holds a key — it must, to
render a device name — but that the key does not live on the same disk as the
ciphertext, and that asking for one leaves a mark. A stolen disk yields
nothing. A key fetched for a tenant nobody logged into is a question somebody
has to answer.

The honest limits, so nothing here is oversold:

* The panel caches keys in memory while it runs. Root on a live box reads them.
* The service token that authorises the fetch is on that same box, so an
  attacker who takes the running machine can ask for keys too. What they
  cannot do is take them quietly: the audit log is written by the service.
* So the claim is "encrypted at rest, and key use is logged", never "we
  cannot read your data".

**Fail closed, and specifically in this direction.** If the key service is
configured but will not answer, the request fails. It must never fall back to
running without a key, because the panel would then read ciphertext rows as
opaque strings and write fresh rows in plain text — quietly turning half a
database into a mixture that no later migration can tell apart.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from contextlib import contextmanager
from typing import Iterator

import httpx

from .config import settings
from .crypto import KEY_LEN, current_key

logger = logging.getLogger("cherubyte.keyring")

TIMEOUT = httpx.Timeout(10.0, connect=4.0)

# tenant -> (key, fetched_at)
_cache: dict[str, tuple[bytes, float]] = {}
_locks: dict[str, asyncio.Lock] = {}


class KeyServiceError(RuntimeError):
    """The key for a tenant could not be obtained."""


def configured() -> bool:
    return bool(settings.key_service_url and settings.key_service_token)


def forget(tenant_id: str | None = None) -> None:
    """Drop cached keys. All of them when no tenant is named.

    Called when a tenant is offboarded, and available to a shutdown path that
    wants the keys out of memory before the process lingers.
    """
    if tenant_id is None:
        _cache.clear()
    else:
        _cache.pop(tenant_id, None)


async def key_for(tenant_id: str) -> bytes:
    """This tenant's key, from cache or from the service.

    The per-tenant lock is what stops a cold start from firing one request per
    concurrent caller. It matters more than it looks: every fetch is an audit
    line, and twenty identical lines a second would bury the one that means
    something.
    """
    if not configured():
        raise KeyServiceError("no key service is configured")

    hit = _cache.get(tenant_id)
    if hit and time.monotonic() - hit[1] < settings.key_cache_ttl:
        return hit[0]

    lock = _locks.setdefault(tenant_id, asyncio.Lock())
    async with lock:
        hit = _cache.get(tenant_id)  # somebody may have fetched it while we waited
        if hit and time.monotonic() - hit[1] < settings.key_cache_ttl:
            return hit[0]
        key = await _fetch(tenant_id)
        _cache[tenant_id] = (key, time.monotonic())
        return key


async def _fetch(tenant_id: str) -> bytes:
    url = settings.key_service_url.rstrip("/") + f"/keys/{tenant_id}"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(
                url, headers={"authorization": f"Bearer {settings.key_service_token}"}
            )
    except httpx.HTTPError as exc:
        raise KeyServiceError(f"the key service did not answer: {exc}") from exc

    if r.status_code == 404:
        raise KeyServiceError(f"no key exists for {tenant_id}")
    if r.status_code >= 300:
        raise KeyServiceError(f"the key service returned {r.status_code}")

    raw = base64.urlsafe_b64decode((r.json().get("key") or "").encode("ascii") + b"==")
    if len(raw) != KEY_LEN:
        # A short key would still encrypt and would still look like it worked.
        raise KeyServiceError("the key service returned a key of the wrong length")
    logger.info("Fetched the encryption key for %s", tenant_id)
    return raw


@contextmanager
def using(key: bytes | None) -> Iterator[None]:
    """Run a block with `key` loaded, and without it afterwards.

    `None` is a real value here and means plain text: self-hosted, and the
    provisioning path that creates a database before a key exists for it.
    """
    token = current_key.set(key)
    try:
        yield
    finally:
        current_key.reset(token)


async def load_for(tenant_id: str | None) -> bytes | None:
    """The key to run a request under, or None when encryption is off.

    Self-hosted has no key service and needs none, so an unconfigured service
    is not an error — it is the other supported way to run. A configured
    service that fails is an error, and loudly.
    """
    if tenant_id is None or not configured():
        return None
    return await key_for(tenant_id)
