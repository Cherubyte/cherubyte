"""Optional Fingerbank (https://fingerbank.org) device identification.

Needs a free API key in NETSCAN_FINGERBANK_API_KEY. Given a DHCP parameter
request list (+ optional hints) it returns a device name, its hierarchy
(e.g. "Operating System/…/Android OS") and often the OS.
"""

from __future__ import annotations

import logging

import httpx

from ..config import settings

logger = logging.getLogger("netscan.fingerbank")

_URL = "https://api.fingerbank.org/api/v2/combinations/interrogate"
_cache: dict[str, dict | None] = {}


def is_enabled() -> bool:
    return bool(settings.fingerbank_api_key)


def reset_cache() -> None:
    """Drop memoised answers — call when the API key changes."""
    _cache.clear()


# A stable, well-known DHCP fingerprint (a generic Android handset) used only to
# check that the configured key is accepted and the service is reachable.
_PROBE_FINGERPRINT = "1,3,6,15,26,28,51,58,59,43"


async def check() -> dict:
    """Diagnose the Fingerbank integration for the settings page.

    Returns {"status": ...} where status is one of: no_key, ok, invalid_key,
    rate_limited, error. On ok, also returns name/os/score.
    """
    if not settings.fingerbank_api_key:
        return {"status": "no_key"}
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.post(
                _URL,
                params={"key": settings.fingerbank_api_key},
                json={"dhcp_fingerprint": _PROBE_FINGERPRINT},
            )
    except httpx.HTTPError as exc:
        return {"status": "error", "detail": str(exc)}
    if resp.status_code in (401, 403):
        return {"status": "invalid_key"}
    if resp.status_code == 429:
        return {"status": "rate_limited"}
    if resp.status_code >= 400:
        return {"status": "error", "detail": f"HTTP {resp.status_code}"}
    data = resp.json()
    dev = data.get("device", {}) or {}
    parents = [p.get("name") for p in dev.get("parents", []) if p.get("name")]
    return {
        "status": "ok",
        "name": dev.get("name"),
        "os": _os_from(dev.get("name"), parents),
        "score": data.get("score"),
    }


async def lookup(
    dhcp_param_list: str,
    *,
    mac: str | None = None,
    hostname: str | None = None,
    vendor_class: str | None = None,
    user_agent: str | None = None,
) -> dict | None:
    """Return {name, os, parents:[...]} or None."""
    if not settings.fingerbank_api_key or not dhcp_param_list:
        return None
    if dhcp_param_list in _cache:
        return _cache[dhcp_param_list]

    payload: dict = {"dhcp_fingerprint": dhcp_param_list}
    if mac:
        payload["mac"] = mac
    if hostname:
        payload["hostname"] = hostname
    if vendor_class:
        payload["dhcp_vendor"] = vendor_class
    if user_agent:
        payload["user_agents"] = [user_agent]

    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.post(
                _URL,
                params={"key": settings.fingerbank_api_key},
                json=payload,
            )
        if resp.status_code == 404:
            _cache[dhcp_param_list] = None
            return None
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("Fingerbank lookup failed: %s", exc)
        return None

    dev = data.get("device", {}) or {}
    parents = [p.get("name") for p in dev.get("parents", []) if p.get("name")]
    result = {
        "name": dev.get("name"),
        "score": data.get("score"),
        "parents": parents,
        "os": _os_from(dev.get("name"), parents),
        "version": data.get("version"),
    }
    _cache[dhcp_param_list] = result
    return result


def _os_from(name: str | None, parents: list[str]) -> str | None:
    chain = [p.lower() for p in parents] + [(name or "").lower()]
    text = " ".join(chain)
    for key, label in (
        ("android", "Android"),
        ("ios", "iOS"),
        ("ipados", "iPadOS"),
        ("mac os", "macOS"),
        ("macos", "macOS"),
        ("windows", "Windows"),
        ("chrome os", "ChromeOS"),
        ("linux", "Linux"),
        ("tvos", "tvOS"),
        ("playstation", "PlayStation OS"),
    ):
        if key in text:
            return label
    return None
