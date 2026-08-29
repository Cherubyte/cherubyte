"""MAC vendor lookup with an offline cache (mac-vendor-lookup).

Used from async code, so we drive the async client directly rather than the
sync wrapper (which spins its own event loop and breaks under a running loop).
"""

from __future__ import annotations

import logging

logger = logging.getLogger("netscan.oui")

try:
    from mac_vendor_lookup import AsyncMacLookup

    _lookup: "AsyncMacLookup | None" = AsyncMacLookup()
except Exception:  # noqa: BLE001
    _lookup = None

_cache: dict[str, str | None] = {}


def is_locally_administered(mac: str) -> bool:
    """Randomised / privacy MACs have bit 1 of the first octet set."""
    try:
        first = int(mac.split(":")[0], 16)
        return bool(first & 0b10)
    except (ValueError, IndexError):
        return False


async def vendor_for(mac: str) -> str | None:
    if _lookup is None:
        return None
    prefix = mac.lower()[:8]
    if prefix in _cache:
        return _cache[prefix]
    try:
        vendor = await _lookup.lookup(mac)
    except Exception:  # noqa: BLE001  (KeyError for unknown OUI, IO errors, ...)
        vendor = None
    _cache[prefix] = vendor
    return vendor


async def refresh_db() -> None:
    if _lookup is None:
        return
    try:
        await _lookup.update_vendors()
        _cache.clear()
        logger.info("OUI database refreshed")
    except Exception as exc:  # noqa: BLE001
        logger.warning("OUI refresh failed: %s", exc)
