"""Fan-out for outgoing notifications.

Callers name an alert kind and describe the notice once (title + body lines);
the policy in `alerts` decides whether it goes out at all and on which
channels, and each channel formats it in its own dialect — HTML for Telegram,
plain text for ntfy.
"""

from __future__ import annotations

import logging
from html import escape

from . import alerts, ntfy, telegram

logger = logging.getLogger("cherubyte.notify")


async def broadcast(
    kind: str,
    title: str,
    lines: list[str],
    *,
    emoji: str = "",
    tags: list[str] | None = None,
    prio: int | None = None,
    actions: list[dict] | None = None,
    force: bool = False,
) -> dict[str, bool]:
    """Send one notice to every channel the policy allows. Per-channel status.

    `force` carries a per-device "always notify" override past the policy's
    enabled flag (quiet hours still apply to non-urgent kinds).
    """
    channels = alerts.channels_for(kind, force=force)
    if not channels:
        logger.debug("alert %s suppressed by policy", kind)
        return {}

    body = "\n".join(lines)
    heading = f"{emoji} {title}".strip()
    result: dict[str, bool] = {}

    if "telegram" in channels:
        text = f"{emoji} <b>{escape(title)}</b>".strip()
        if body:
            text += "\n" + escape(body)
        result["telegram"] = await telegram.send(text)

    if "ntfy" in channels:
        result["ntfy"] = await ntfy.send(
            body or title, title=heading, tags=tags, prio=prio, actions=actions
        )

    return result
