"""Web Push notifications — alerts delivered to a browser with no third party.

The other channels lean on someone else's infrastructure (Telegram, ntfy, an
SMTP server). Web Push needs only the browser's own push service, which the
panel talks to directly using a VAPID key it generates once and keeps in the
`settings` table. Nothing about the alert passes through Cherubyte's authors.

`pywebpush` does the payload encryption (RFC 8291) and the VAPID JWT; it is
synchronous (built on `requests`), so every send goes through a worker thread.
A subscription the push service reports as gone (404/410) is deleted.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import SessionLocal
from ..models import PushSubscription, utcnow

logger = logging.getLogger("cherubyte.webpush")

_KEY_PRIVATE = "vapid_private_pem"
_KEY_PUBLIC = "vapid_public_key"

_runtime: dict[str, object] = {}


def configure(
    *,
    private_pem: str | None = None,
    public_key: str | None = None,
    subject: str | None = None,
    enabled: bool | None = None,
) -> None:
    for key, value in (
        ("private_pem", private_pem),
        ("public_key", public_key),
        ("subject", subject),
        ("enabled", enabled),
    ):
        if value is not None:
            _runtime[key] = value


def _get(key: str, fallback: object = None) -> object:
    value = _runtime.get(key)
    return fallback if value is None else value


def public_key() -> str:
    """The base64url application server key the browser subscribes with."""
    return str(_get("public_key", "") or "")


def is_enabled() -> bool:
    return bool(_get("enabled", settings.webpush_enabled))


def has_keys() -> bool:
    return bool(_get("private_pem") and public_key())


def _subject() -> str:
    explicit = str(_get("subject", settings.vapid_subject) or "").strip()
    if explicit:
        return explicit if ":" in explicit else f"mailto:{explicit}"
    base = (settings.public_base_url or "").strip()
    return base or "mailto:admin@example.com"


def generate_keys() -> tuple[str, str]:
    """A fresh VAPID keypair as (private PEM, base64url public key)."""
    from cryptography.hazmat.primitives import serialization
    from py_vapid import Vapid01

    v = Vapid01()
    v.generate_keys()
    private_pem = v.private_pem().decode()
    raw = v.public_key.public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    public = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    return private_pem, public


async def ensure_keys(session: AsyncSession) -> None:
    """Generate and persist a VAPID keypair the first time it is needed."""
    from ..models import Setting

    rows = {
        r.key: r.value
        for r in (
            await session.execute(
                select(Setting).where(Setting.key.in_([_KEY_PRIVATE, _KEY_PUBLIC]))
            )
        ).scalars()
    }
    if rows.get(_KEY_PRIVATE) and rows.get(_KEY_PUBLIC):
        configure(private_pem=rows[_KEY_PRIVATE], public_key=rows[_KEY_PUBLIC])
        return

    private_pem, public = generate_keys()
    for key, value in ((_KEY_PRIVATE, private_pem), (_KEY_PUBLIC, public)):
        row = await session.get(Setting, key)
        if row is None:
            session.add(Setting(key=key, value=value))
        else:
            row.value = value
    await session.commit()
    configure(private_pem=private_pem, public_key=public)
    logger.info("Generated a VAPID keypair for Web Push")


def _send_blocking(subscription: dict, payload: str) -> None:
    from pywebpush import webpush

    webpush(
        subscription_info=subscription,
        data=payload,
        vapid_private_key=str(_get("private_pem")),
        vapid_claims={"sub": _subject()},
        ttl=600,
    )


async def _send_one(sub: PushSubscription, payload: str) -> str:
    """'ok', 'gone' (delete it) or 'error'."""
    from pywebpush import WebPushException

    info = {
        "endpoint": sub.endpoint,
        "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
    }
    try:
        await asyncio.get_running_loop().run_in_executor(
            None, _send_blocking, info, payload
        )
        return "ok"
    except WebPushException as exc:
        code = getattr(exc.response, "status_code", None)
        if code in (404, 410):
            return "gone"
        logger.warning("web push failed (%s): %s", code, exc)
        return "error"
    except Exception as exc:  # noqa: BLE001
        logger.warning("web push error: %s", exc)
        return "error"


async def send_test() -> dict:
    async with SessionLocal() as session:
        return await _broadcast(
            session,
            "Cherubyte",
            "Test notification — push is working on this browser.",
            url=settings.public_base_url or "/",
        )


async def broadcast(title: str, body: str, *, url: str | None = None) -> dict:
    """Push one notice to every subscribed browser. Prunes dead subscriptions."""
    if not is_enabled() or not has_keys():
        return {}
    async with SessionLocal() as session:
        return await _broadcast(session, title, body, url=url or "/")


async def _broadcast(
    session: AsyncSession, title: str, body: str, *, url: str
) -> dict:
    subs = list((await session.execute(select(PushSubscription))).scalars())
    if not subs:
        return {"sent": 0, "removed": 0}

    payload = json.dumps({"title": title, "body": body, "url": url})
    sent = 0
    dead: list[PushSubscription] = []
    for sub in subs:
        result = await _send_one(sub, payload)
        if result == "ok":
            sent += 1
            sub.last_ok_at = utcnow()
        elif result == "gone":
            dead.append(sub)
    for sub in dead:
        await session.delete(sub)
    if sent or dead:
        await session.commit()
    return {"sent": sent, "removed": len(dead)}
