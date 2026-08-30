from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_session
from ..models import Device, User
from ..schemas import UserDetailOut, UserIn, UserOut, UserPatch
from ..services.presence import presence_intervals

router = APIRouter(prefix="/users", tags=["users"])

_DEVICE_LOAD = (
    selectinload(User.devices).selectinload(Device.macs),
    selectinload(User.devices).selectinload(Device.ips),
)


def _present(user: User) -> bool:
    return any(d.is_online and d.counts_for_presence for d in user.devices)


def _to_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        name=user.name,
        avatar=user.avatar,
        notes=user.notes,
        is_guest=user.is_guest,
        device_count=len(user.devices),
        is_present=_present(user),
    )


async def _load(session: AsyncSession, user_id: int) -> User:
    user = (
        await session.execute(
            select(User).where(User.id == user_id).options(*_DEVICE_LOAD)
        )
    ).scalars().first()
    if user is None:
        raise HTTPException(404, "User not found")
    return user


@router.get("", response_model=list[UserOut])
async def list_users(session: AsyncSession = Depends(get_session)):
    res = await session.execute(select(User).options(*_DEVICE_LOAD))
    return [_to_out(u) for u in res.scalars()]


@router.post("", response_model=UserOut, status_code=201)
async def create_user(payload: UserIn, session: AsyncSession = Depends(get_session)):
    user = User(**payload.model_dump())
    session.add(user)
    await session.commit()
    return _to_out(await _load(session, user.id))


@router.get("/{user_id}", response_model=UserDetailOut)
async def get_user(user_id: int, session: AsyncSession = Depends(get_session)):
    from ..schemas import DeviceMini

    user = await _load(session, user_id)
    devices = sorted(
        user.devices, key=lambda d: (not d.is_online, d.display_name.lower())
    )
    return UserDetailOut(
        **_to_out(user).model_dump(),
        devices=[DeviceMini.model_validate(d) for d in devices],
    )


@router.get("/{user_id}/presence")
async def user_presence(
    user_id: int,
    session: AsyncSession = Depends(get_session),
    days: int = Query(10, ge=1, le=30),
):
    await _load(session, user_id)
    return await presence_intervals(session, user_id, days)


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int, payload: UserPatch, session: AsyncSession = Depends(get_session)
):
    user = await _load(session, user_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, key, value)
    await session.commit()
    return _to_out(await _load(session, user_id))


@router.delete("/{user_id}", status_code=204)
async def delete_user(user_id: int, session: AsyncSession = Depends(get_session)):
    user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalars().first()
    if user is None:
        raise HTTPException(404, "User not found")
    await session.execute(
        Device.__table__.update().where(Device.user_id == user_id).values(user_id=None)
    )
    await session.delete(user)
    await session.commit()
