"""Telegram notifications. Config comes from settings, overridable via DB."""

from __future__ import annotations

import logging

import httpx

from ..config import settings

logger = logging.getLogger("netscan.telegram")

_runtime: dict[str, object] = {}


def configure(
    bot_token: str | None = None,
    chat_id: str | None = None,
    *,
    enabled: bool | None = None,
) -> None:
    if bot_token is not None:
        _runtime["bot_token"] = bot_token
    if chat_id is not None:
        _runtime["chat_id"] = chat_id
    if enabled is not None:
        _runtime["enabled"] = enabled


def _creds() -> tuple[str, str] | None:
    token = _runtime.get("bot_token") or settings.telegram_bot_token
    chat = _runtime.get("chat_id") or settings.telegram_chat_id
    if token and chat:
        return str(token), str(chat)
    return None


def is_enabled() -> bool:
    value = _runtime.get("enabled")
    return settings.telegram_enabled if value is None else bool(value)


def has_credentials() -> bool:
    return _creds() is not None


def is_configured() -> bool:
    """Enabled AND has a bot token + chat id — i.e. would actually send."""
    return is_enabled() and has_credentials()


async def send(text: str) -> bool:
    if not is_configured():
        logger.debug("Telegram not configured; skipping: %s", text)
        return False
    token, chat = _creds()  # type: ignore[misc]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                url,
                json={"chat_id": chat, "text": text, "parse_mode": "HTML"},
            )
        if resp.status_code != 200:
            logger.warning("Telegram send failed %s: %s", resp.status_code, resp.text)
            return False
        return True
    except httpx.HTTPError as exc:
        logger.warning("Telegram send error: %s", exc)
        return False
