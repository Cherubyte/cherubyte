"""Web Push subscription management.

Behind the login wall like the rest of `/api`. The browser fetches the VAPID
public key, subscribes with its push service, and hands the resulting
subscription here to be stored. Alerts are then delivered by
`services/webpush.py`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models import PushSubscription, utcnow
from ..services import webpush

router = APIRouter(prefix="/push", tags=["push"])


class SubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class SubscriptionIn(BaseModel):
    endpoint: str
    keys: SubscriptionKeys


class UnsubscribeIn(BaseModel):
    endpoint: str


@router.get("/key")
async def get_key(session: AsyncSession = Depends(get_session)):
    await webpush.ensure_keys(session)
    return {"key": webpush.public_key(), "enabled": webpush.is_enabled()}


@router.post("/subscribe")
async def subscribe(
    payload: SubscriptionIn, session: AsyncSession = Depends(get_session)
):
    await webpush.ensure_keys(session)
    if not payload.endpoint.startswith("https://"):
        raise HTTPException(422, "endpoint must be an https URL")

    row = (
        await session.execute(
            select(PushSubscription).where(
                PushSubscription.endpoint == payload.endpoint
            )
        )
    ).scalars().first()
    if row is None:
        row = PushSubscription(endpoint=payload.endpoint)
        session.add(row)
    row.p256dh = payload.keys.p256dh
    row.auth = payload.keys.auth
    row.last_ok_at = utcnow()
    await session.commit()
    return {"ok": True}


@router.post("/unsubscribe")
async def unsubscribe(
    payload: UnsubscribeIn, session: AsyncSession = Depends(get_session)
):
    row = (
        await session.execute(
            select(PushSubscription).where(
                PushSubscription.endpoint == payload.endpoint
            )
        )
    ).scalars().first()
    if row is not None:
        await session.delete(row)
        await session.commit()
    return {"ok": True}


@router.post("/test")
async def test_push():
    result = await webpush.send_test()
    return {"ok": bool(result.get("sent")), **result}
