"""ntfy notifications. Config comes from settings, overridable via DB.

Publishes through ntfy's JSON endpoint (POST to the server root) so the title
and body survive as UTF-8 — the header-based API would need RFC 2047 encoding.
"""

from __future__ import annotations

import base64
import logging

import httpx

from ..config import settings

logger = logging.getLogger("netscan.ntfy")

DEFAULT_SERVER = "https://ntfy.sh"

_runtime: dict[str, object] = {}


def configure(
    *,
    server: str | None = None,
    topic: str | None = None,
    token: str | None = None,
    username: str | None = None,
    password: str | None = None,
    priority: int | None = None,
    enabled: bool | None = None,
) -> None:
    for key, value in (
        ("server", server),
        ("topic", topic),
        ("token", token),
        ("username", username),
        ("password", password),
        ("priority", priority),
        ("enabled", enabled),
    ):
        if value is not None:
            _runtime[key] = value


def _get(key: str, fallback: object) -> object:
    value = _runtime.get(key)
    return fallback if value is None else value


def server_url() -> str:
    raw = str(_get("server", settings.ntfy_server) or DEFAULT_SERVER).strip()
    return raw.rstrip("/") or DEFAULT_SERVER


def topic() -> str:
    return str(_get("topic", settings.ntfy_topic) or "").strip()


def priority() -> int:
    try:
        value = int(_get("priority", settings.ntfy_priority))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 3
    return min(5, max(1, value))


def is_enabled() -> bool:
    return bool(_get("enabled", settings.ntfy_enabled))


def has_auth() -> bool:
    token = str(_get("token", settings.ntfy_token) or "")
    password = str(_get("password", settings.ntfy_password) or "")
    return bool(token or password)


def is_configured() -> bool:
    return is_enabled() and bool(topic())


def _auth_header() -> dict[str, str]:
    token = str(_get("token", settings.ntfy_token) or "").strip()
    if token:
        return {"Authorization": f"Bearer {token}"}
    username = str(_get("username", settings.ntfy_username) or "").strip()
    password = str(_get("password", settings.ntfy_password) or "")
    if username or password:
        raw = base64.b64encode(f"{username}:{password}".encode()).decode()
        return {"Authorization": f"Basic {raw}"}
    return {}


async def send(
    message: str,
    *,
    title: str | None = None,
    tags: list[str] | None = None,
    prio: int | None = None,
    actions: list[dict] | None = None,
) -> bool:
    if not is_configured():
        logger.debug("ntfy not configured; skipping: %s", title or message)
        return False
    payload: dict[str, object] = {
        "topic": topic(),
        "message": message,
        "priority": prio if prio is not None else priority(),
    }
    if title:
        payload["title"] = title
    if tags:
        payload["tags"] = tags
    if actions:
        # ntfy renders at most three buttons on a notification
        payload["actions"] = actions[:3]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(server_url(), json=payload, headers=_auth_header())
        if resp.status_code >= 300:
            logger.warning("ntfy send failed %s: %s", resp.status_code, resp.text)
            return False
        return True
    except httpx.HTTPError as exc:
        logger.warning("ntfy send error: %s", exc)
        return False
