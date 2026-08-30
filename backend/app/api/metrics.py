"""`/api/metrics` — Prometheus exposition.

Outside the login wall, like the agent routes: a scraper is a machine client and
cannot hold a browser session. When `metrics_token` is set it must be presented
as a bearer header or a `?token=` query param; unset, the endpoint is open on the
LAN like the rest of the API (don't expose the panel to the internet — see the
Security section of the README).
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_session
from ..services.metrics import build_exposition

router = APIRouter(tags=["metrics"])

_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


def _presented_token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.query_params.get("token", "")


def _authorised(request: Request) -> bool:
    want = settings.metrics_token or ""
    if not want:
        return True
    got = _presented_token(request)
    return bool(got) and hmac.compare_digest(got, want)


@router.get("/metrics")
async def metrics(request: Request, session: AsyncSession = Depends(get_session)):
    if not settings.metrics_enabled:
        raise HTTPException(404, "metrics endpoint disabled")
    if not _authorised(request):
        raise HTTPException(
            401,
            "metrics token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    body = await build_exposition(session, version=request.app.version)
    return Response(body, media_type=_CONTENT_TYPE)
