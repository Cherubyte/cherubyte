"""The panel is where you get an agent.

`Settings ▸ Agents` offers a ready-to-run agent binary for each platform. The
agent is its own program now (github.com/Cherubyte/cherubyte-agent) and cuts its
own GitHub releases; this module reads the latest one and streams the asset from
the panel's own origin, so an operator never has to leave the panel — or reach
GitHub themselves, if only the panel can.

Same shape as `services/update.py`: a module-level cache, an `httpx` client with
a short timeout, and functions that never raise — a GitHub outage degrades the
page to the `git clone` / Docker instructions, it does not break it.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

import httpx

from ..config import DATA_DIR
from ..models import iso_utc, utcnow

logger = logging.getLogger("cherubyte.agent_release")

AGENT_REPO = "Cherubyte/cherubyte-agent"
REPO_URL = f"https://github.com/{AGENT_REPO}"
DOCKER_IMAGE = "ghcr.io/cherubyte/cherubyte-agent:latest"
_RELEASE_URL = f"https://api.github.com/repos/{AGENT_REPO}/releases/latest"

# asset name as attached by the agent repo's agent-binaries.yml
PLATFORMS: dict[str, str] = {
    "linux": "cherubyte-agent-linux-x86_64",
    "macos": "cherubyte-agent-macos-arm64",
    "windows": "cherubyte-agent-windows-x86_64.exe",
}
# what the browser should call the saved file
DOWNLOAD_NAME: dict[str, str] = {
    "linux": "cherubyte-agent",
    "macos": "cherubyte-agent",
    "windows": "cherubyte-agent.exe",
}
# the per-platform installer, so `curl <panel>/.../installer/linux | sudo bash`
# is all a native install takes — no repo checkout, panel is the only host hit.
_INSTALLER_PATH: dict[str, str] = {
    "linux": "agent/linux/install-service.sh",
    "macos": "agent/macos/install-daemon.sh",
    "windows": "agent/windows/install-service.ps1",
}
_RAW = f"https://raw.githubusercontent.com/{AGENT_REPO}/main"

CACHE_DIR = DATA_DIR / "agent-cache"
_TTL_SECONDS = 600

_cache: dict = {
    "tag": None,
    "published_at": None,
    "assets": {},          # platform -> {"name", "url", "size"}
    "checked_at": None,
    "error": None,
    "_fetched_monotonic": 0.0,
}
_lock = asyncio.Lock()


def _repo_info() -> dict:
    return {"repo_url": REPO_URL, "docker_image": DOCKER_IMAGE, "platforms": list(PLATFORMS)}


async def latest(*, force: bool = False) -> dict:
    """The latest agent release, cached for ~10 minutes. Never raises."""
    fresh = time.monotonic() - _cache["_fetched_monotonic"] < _TTL_SECONDS
    if _cache["tag"] and fresh and not force:
        return {**_cache, **_repo_info()}

    async with _lock:
        if _cache["tag"] and time.monotonic() - _cache["_fetched_monotonic"] < _TTL_SECONDS and not force:
            return {**_cache, **_repo_info()}
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
                resp = await client.get(
                    _RELEASE_URL, headers={"Accept": "application/vnd.github+json"}
                )
                resp.raise_for_status()
                body = resp.json()
            assets: dict[str, dict] = {}
            by_name = {a["name"]: a for a in body.get("assets", [])}
            for platform, asset_name in PLATFORMS.items():
                a = by_name.get(asset_name)
                if a:
                    assets[platform] = {
                        "name": asset_name,
                        "url": a["browser_download_url"],
                        "size": a.get("size"),
                    }
            _cache.update(
                tag=body.get("tag_name"),
                published_at=body.get("published_at"),
                assets=assets,
                checked_at=iso_utc(utcnow()),
                error=None,
                _fetched_monotonic=time.monotonic(),
            )
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            msg = "no release published yet" if code == 404 else f"GitHub returned {code}"
            logger.warning("agent release check: %s", msg)
            _cache.update(checked_at=iso_utc(utcnow()), error=msg, _fetched_monotonic=time.monotonic())
        except Exception as exc:  # noqa: BLE001
            logger.warning("agent release check failed: %s", exc)
            _cache.update(
                checked_at=iso_utc(utcnow()),
                error=f"{type(exc).__name__}: {exc}"[:200],
                _fetched_monotonic=time.monotonic(),
            )
    return {**_cache, **_repo_info()}


def _prune(keep_tag: str) -> None:
    prefix = f"{keep_tag}__"
    for f in CACHE_DIR.glob("*"):
        if not f.name.startswith(prefix):
            f.unlink(missing_ok=True)


async def asset_path(platform: str) -> Path | None:
    """The cached binary for `platform`, downloading it once. None when there is
    no release, no asset for that platform, or the download fails."""
    if platform not in PLATFORMS:
        return None
    info = await latest()
    tag = info.get("tag")
    asset = info.get("assets", {}).get(platform)
    if not tag or not asset:
        return None

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    dest = CACHE_DIR / f"{tag}__{asset['name']}"
    if dest.exists() and dest.stat().st_size > 0:
        return dest

    try:
        tmp = dest.with_suffix(dest.suffix + ".part")
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            async with client.stream("GET", asset["url"]) as resp:
                resp.raise_for_status()
                with tmp.open("wb") as fh:
                    async for chunk in resp.aiter_bytes(64 * 1024):
                        fh.write(chunk)
        tmp.replace(dest)
    except Exception as exc:  # noqa: BLE001
        logger.warning("agent asset download failed (%s): %s", platform, exc)
        return None

    _prune(tag)
    return dest


_installer_cache: dict[str, str] = {}


async def installer_script(platform: str) -> str | None:
    """The raw per-platform installer from the agent repo, cached in memory.
    None for an unknown platform or a failed fetch."""
    path = _INSTALLER_PATH.get(platform)
    if path is None:
        return None
    if platform in _installer_cache:
        return _installer_cache[platform]
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
            resp = await client.get(f"{_RAW}/{path}")
            resp.raise_for_status()
        _installer_cache[platform] = resp.text
        return resp.text
    except Exception as exc:  # noqa: BLE001
        logger.warning("agent installer fetch failed (%s): %s", platform, exc)
        return None
