"""Checks whether `main` has moved past the version that's running, and can
pull that in for a git checkout.

The project doesn't cut GitHub Releases yet (see docs/RELEASING.md), so "the
latest version" is read straight off `frontend/package.json` on `main` — the
one file the release process itself bumps first, and the same file this app
already reads its own version from (config.APP_VERSION). Once releases start
this still works: main's version only ever moves forward from the last one.

A Docker deployment can't safely re-launch its own container from inside
itself (that needs the host's Docker socket, which this app is never handed),
so `apply()` only runs for a git checkout — `deploy_mode()` tells the caller
which case it's in.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from pathlib import Path

import httpx

from ..config import APP_VERSION, BASE_DIR
from ..models import utcnow

logger = logging.getLogger("cherubyte.update")

REPO = "Cherubyte/cherubyte"
REPO_URL = f"https://github.com/{REPO}"
_PACKAGE_URL = f"https://raw.githubusercontent.com/{REPO}/main/frontend/package.json"

# In a git checkout this is the repo root; in the Docker image it's just /app
# (no .git there), which is how deploy_mode() tells the two apart.
ROOT = BASE_DIR.parent


def _parse(v: str) -> tuple[int, ...]:
    """"v0.14.1" -> (0, 14, 1). Unparsable segments become 0 rather than raising —
    a scheme change on `main` should never crash the check."""
    out = []
    for part in v.strip().lstrip("vV").split("."):
        digits = "".join(c for c in part if c.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple(out) or (0,)


def is_newer(latest: str, current: str) -> bool:
    return _parse(latest) > _parse(current)


def deploy_mode() -> str:
    """"git" when ROOT is a checkout `apply()` can update in place; "container"
    otherwise (the Docker image, or any install with the .git dir removed)."""
    return "git" if (ROOT / ".git").is_dir() else "container"


_status: dict = {
    "current": APP_VERSION,
    "latest": None,
    "checked_at": None,
    "error": None,
}


async def check() -> dict:
    """Refresh `_status` from `main`. Never raises — a failed check just leaves
    the last known state with an `error` note."""
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(_PACKAGE_URL)
            resp.raise_for_status()
            latest = resp.json()["version"]
        _status.update(latest=latest, checked_at=utcnow(), error=None)
    except httpx.HTTPStatusError as exc:
        logger.warning("update check failed: %s", exc)
        _status.update(checked_at=utcnow(), error=f"GitHub returned {exc.response.status_code}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("update check failed: %s", exc)
        _status.update(checked_at=utcnow(), error=f"{type(exc).__name__}: {exc}"[:200])
    return _status


def status() -> dict:
    return _status


_apply: dict = {"status": "idle", "log": [], "error": None, "started_at": None}


def apply_status() -> dict:
    return _apply


async def _run(cmd: list[str], cwd: Path) -> None:
    _apply["log"].append("$ " + " ".join(cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    assert proc.stdout is not None
    async for raw in proc.stdout:
        line = raw.decode(errors="replace").rstrip()
        if line:
            _apply["log"].append(line)
    code = await proc.wait()
    if code != 0:
        raise RuntimeError(f"`{' '.join(cmd)}` exited {code}")


async def _run_apply() -> None:
    try:
        dirty = await asyncio.create_subprocess_exec(
            "git", "status", "--porcelain", cwd=str(ROOT),
            stdout=asyncio.subprocess.PIPE,
        )
        out, _ = await dirty.communicate()
        if out.strip():
            raise RuntimeError(
                "the checkout has local changes — commit, stash, or discard "
                "them first"
            )

        await _run(["git", "pull", "--ff-only"], ROOT)

        pip = ROOT / "backend" / ".venv" / "bin" / "pip"
        if pip.exists():
            await _run([str(pip), "install", "-q", "-r", "backend/requirements.txt"], ROOT)
            await _run([str(pip), "install", "-q", "./protocol"], ROOT)

        if shutil.which("npm"):
            await _run(["npm", "ci", "--no-audit", "--no-fund"], ROOT / "frontend")
            await _run(["npm", "run", "build"], ROOT / "frontend")
        else:
            _apply["log"].append("npm not found — skipped rebuilding the UI")

        _apply["status"] = "restarting"
        _apply["log"].append(
            "Update applied. Restarting — a systemd install (Restart=always) "
            "comes back on its own; anything else needs a manual restart."
        )
        await check()
        await asyncio.sleep(1)
        os._exit(0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("self-update failed: %s", exc)
        _apply["status"] = "failed"
        _apply["error"] = str(exc)


async def apply() -> None:
    if deploy_mode() != "git":
        raise RuntimeError("not a git checkout — pull the new image instead")
    if _apply["status"] == "updating":
        return
    _apply.update(status="updating", log=[], error=None, started_at=utcnow())
    asyncio.create_task(_run_apply())
