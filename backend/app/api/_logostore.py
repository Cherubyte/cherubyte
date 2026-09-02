"""Shared CRUD for the tiny "name -> optional logo + device count" stores
(brands and OS families)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings, upload_dir
from ..database import get_session
from ..models import Device
from ._uploads import save_image_upload

_EXT_OK = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif"}


def build_router(
    *,
    prefix: str,
    tag: str,
    model,
    counter: Callable[[Device], str | None],
    file_prefix: str,
    skip_unkeyed: bool = False,
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=[tag])

    async def _counts(session: AsyncSession) -> dict[str, int]:
        devices = (await session.execute(select(Device))).scalars().all()
        out: dict[str, int] = {}
        for d in devices:
            key = counter(d)
            if not key:
                if skip_unkeyed:
                    continue  # e.g. devices with OS explicitly set to "Nenhum"
                key = "Desconhecido"
            out[key] = out.get(key, 0) + 1
        return out

    async def _get_or_create(session: AsyncSession, name: str):
        row = (
            await session.execute(
                select(model).where(func.lower(model.name) == name.lower())
            )
        ).scalars().first()
        if row is None:
            row = model(name=name)
            session.add(row)
            await session.flush()
        return row

    def _out(name: str, logo: str | None, count: int) -> dict:
        return {
            "name": name,
            "logo_url": f"/uploads/{logo}" if logo else None,
            "device_count": count,
        }

    @router.get("")
    async def list_all(session: AsyncSession = Depends(get_session)):
        counts = await _counts(session)
        stored = {
            r.name: r for r in (await session.execute(select(model))).scalars().all()
        }
        names = set(counts) | set(stored)
        rows = [
            _out(n, stored[n].logo if n in stored else None, counts.get(n, 0))
            for n in names
        ]
        return sorted(rows, key=lambda x: (-x["device_count"], x["name"].lower()))

    @router.post("/{name}/logo")
    async def upload_logo(
        name: str,
        file: UploadFile = File(...),
        session: AsyncSession = Depends(get_session),
    ):
        ext = Path(file.filename or "").suffix.lower() or ".png"
        if ext not in _EXT_OK:
            raise HTTPException(400, "Unsupported image type")
        row = await _get_or_create(session, name)
        fname = f"{file_prefix}-{uuid.uuid4().hex[:12]}{ext}"
        # write the replacement before dropping the old one: a rejected upload
        # must not leave the brand with no logo at all
        await save_image_upload(
            file, upload_dir(create=True) / fname, max_bytes=settings.max_upload_bytes
        )
        if row.logo:
            (upload_dir() / row.logo).unlink(missing_ok=True)
        row.logo = fname
        await session.commit()
        counts = await _counts(session)
        return _out(row.name, fname, counts.get(row.name, 0))

    @router.delete("/{name}/logo", status_code=204)
    async def delete_logo(name: str, session: AsyncSession = Depends(get_session)):
        row = (
            await session.execute(
                select(model).where(func.lower(model.name) == name.lower())
            )
        ).scalars().first()
        if row and row.logo:
            (upload_dir() / row.logo).unlink(missing_ok=True)
            row.logo = None
            await session.commit()

    return router
