"""Endpoints reachable from a notification button.

These carry their own authority in a signed token rather than a session, so
they live apart from the regular device routes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models import ApprovalStatus, Device
from ..services import action_tokens

router = APIRouter(prefix="/actions", tags=["actions"])

_STATUS = {
    "approve": ApprovalStatus.approved,
    "ignore": ApprovalStatus.ignored,
}


@router.post("/{action}/{device_id}")
async def run_action(
    action: str,
    device_id: int,
    t: str = Query("", description="signed token from the notification"),
    session: AsyncSession = Depends(get_session),
):
    if action not in _STATUS:
        raise HTTPException(404, "Ação desconhecida")
    if not action_tokens.verify(action, device_id, t):
        raise HTTPException(403, "Token inválido ou expirado")
    device = await session.get(Device, device_id)
    if device is None:
        raise HTTPException(404, "Dispositivo não encontrado")
    device.approval_status = _STATUS[action]
    await session.commit()
    return {"ok": True, "device": device.display_name, "status": device.approval_status.value}
