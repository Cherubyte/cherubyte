from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..config import UPLOAD_DIR, settings
from ..database import get_session
from ..models import (
    ApprovalStatus,
    ConnectionHistory,
    Device,
    DeviceImage,
    Event,
    EventLevel,
    IpAddress,
    MacAddress,
    OpenPort,
    iso_utc,
)
from ..services import duplicates, uptime, wol
from ._uploads import save_image_upload
from ..schemas import (
    AbsorbMacRequest,
    ConnectionOut,
    DeviceOut,
    DeviceUpdate,
    MergeRequest,
)

router = APIRouter(prefix="/devices", tags=["devices"])

_LOADED = (
    selectinload(Device.macs),
    selectinload(Device.ips),
    selectinload(Device.open_ports),
    selectinload(Device.images),
    selectinload(Device.user),
)


def _coerce_dt(value: object) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


async def _last_joins(
    session: AsyncSession, device_ids: list[int]
) -> dict[int, datetime]:
    """The timestamp of the most recent 'join' per device (indexed lookup)."""
    if not device_ids:
        return {}
    rows = await session.execute(
        select(ConnectionHistory.device_id, func.max(ConnectionHistory.timestamp))
        .where(
            ConnectionHistory.device_id.in_(device_ids),
            ConnectionHistory.event == "join",
        )
        .group_by(ConnectionHistory.device_id)
    )
    out: dict[int, datetime] = {}
    for did, ts in rows:
        dt = _coerce_dt(ts)
        if dt is not None:
            out[did] = dt
    return out


def _set_online_since(device: Device, joined: datetime | None) -> None:
    # a transient attribute DeviceOut (from_attributes) picks up
    device.online_since = (
        (joined or device.first_seen) if device.is_online else None
    )


async def _get(session: AsyncSession, device_id: int) -> Device:
    # start from a clean slate so post-mutation reads never see stale identity-map state
    session.expire_all()
    res = await session.execute(
        select(Device).where(Device.id == device_id).options(*_LOADED)
    )
    device = res.scalars().first()
    if device is None:
        raise HTTPException(404, "Device not found")
    joins = await _last_joins(session, [device.id] if device.is_online else [])
    _set_online_since(device, joins.get(device.id))
    return device


@router.get("/merge-suggestions")
async def merge_suggestions(session: AsyncSession = Depends(get_session)):
    """Devices that look like one handset behind a rotating MAC."""
    found = await duplicates.suggestions(session)
    return [
        {
            "reason": s.reason,
            "confidence": s.confidence,
            "target": {"id": s.target.id, "name": s.target.display_name},
            "duplicates": [
                {"id": d.id, "name": d.display_name, "first_seen": d.first_seen}
                for d in s.duplicates
            ],
        }
        for s in found
    ]


@router.get("/tags")
async def list_tags(session: AsyncSession = Depends(get_session)):
    """Every distinct tag in use, most common first — for the filter and the
    add-a-tag autocomplete. Declared before `/{device_id}`."""
    rows = (
        await session.execute(select(Device.tags).where(Device.tags.is_not(None)))
    ).scalars().all()
    counts: dict[str, int] = {}
    display: dict[str, str] = {}
    for raw in rows:
        for t in (raw or "").split(","):
            if not t:
                continue
            k = t.lower()
            counts[k] = counts.get(k, 0) + 1
            display.setdefault(k, t)
    ordered = sorted(counts, key=lambda k: (-counts[k], k))
    return [display[k] for k in ordered]


@router.get("/export.csv")
async def export_devices_csv(session: AsyncSession = Depends(get_session)):
    """The whole device inventory as CSV. Declared before `/{device_id}` so the
    literal path wins the route match."""
    res = await session.execute(select(Device).options(*_LOADED).order_by(Device.id))
    devices = list(res.scalars().unique())

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        ["id", "name", "type", "vendor", "model", "os", "approval", "online",
         "primary_ip", "ips", "macs", "owner", "tags", "first_seen", "last_seen"]
    )
    for d in devices:
        primary = next((i.address for i in d.ips if i.is_primary), None)
        if primary is None and d.ips:
            primary = d.ips[0].address
        w.writerow([
            d.id,
            d.display_name,
            d.device_type.value,
            d.vendor or "",
            d.model or "",
            d.os_family or "",
            d.approval_status.value,
            "yes" if d.is_online else "no",
            primary or "",
            " ".join(i.address for i in d.ips),
            " ".join(m.address for m in d.macs),
            d.user.name if d.user else "",
            " ".join(d.tag_list),
            iso_utc(d.first_seen) or "",
            iso_utc(d.last_seen) or "",
        ])
    return Response(
        buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="netscan-devices.csv"'},
    )


@router.get("", response_model=list[DeviceOut])
async def list_devices(
    session: AsyncSession = Depends(get_session),
    status: ApprovalStatus | None = None,
    online: bool | None = None,
    q: str | None = Query(None, description="search name / hostname / ip / mac"),
):
    stmt = select(Device).options(*_LOADED).order_by(Device.is_online.desc(), Device.last_seen.desc())
    if status is not None:
        stmt = stmt.where(Device.approval_status == status)
    if online is not None:
        stmt = stmt.where(Device.is_online.is_(online))
    res = await session.execute(stmt)
    devices = list(res.scalars().unique())

    joins = await _last_joins(session, [d.id for d in devices if d.is_online])
    for d in devices:
        _set_online_since(d, joins.get(d.id))

    if q:
        needle = q.lower().strip()
        def match(d: Device) -> bool:
            return (
                needle in (d.name or "").lower()
                or needle in (d.hostname or "").lower()
                or any(needle in i.address.lower() for i in d.ips)
                or any(needle in m.address.lower() for m in d.macs)
                or needle in (d.vendor or "").lower()
                or needle in (d.tags or "").lower()
            )
        devices = [d for d in devices if match(d)]
    return devices


@router.get("/{device_id}", response_model=DeviceOut)
async def get_device(device_id: int, session: AsyncSession = Depends(get_session)):
    return await _get(session, device_id)


# auto-populated fields the scan reconciler owns — once a user edits one of
# these by hand it gets pinned in Device.overrides and the scan leaves it alone.
_AUTO_FIELDS = {"device_type", "vendor", "model", "os_guess"}


@router.patch("/{device_id}", response_model=DeviceOut)
async def update_device(
    device_id: int, payload: DeviceUpdate, session: AsyncSession = Depends(get_session)
):
    device = await _get(session, device_id)
    data = payload.model_dump(exclude_unset=True)
    locked = device.locked_fields
    for key, value in data.items():
        if key == "tags":
            device.set_tags(value or [])
            continue
        if isinstance(value, str):
            value = value.strip() or None
        setattr(device, key, value)
        if key in _AUTO_FIELDS:
            locked.add(key)
    device.overrides = ",".join(sorted(locked)) or None
    await session.commit()
    return await _get(session, device_id)


@router.post("/{device_id}/approve", response_model=DeviceOut)
async def approve_device(device_id: int, session: AsyncSession = Depends(get_session)):
    device = await _get(session, device_id)
    device.approval_status = ApprovalStatus.approved
    session.add(
        Event(
            message=f"{device.display_name} aprovado",
            level=EventLevel.success,
            category="approval",
            device_id=device.id,
        )
    )
    await session.commit()
    return await _get(session, device_id)


@router.post("/{device_id}/ignore", response_model=DeviceOut)
async def ignore_device(device_id: int, session: AsyncSession = Depends(get_session)):
    device = await _get(session, device_id)
    device.approval_status = ApprovalStatus.ignored
    session.add(
        Event(
            message=f"{device.display_name} marcado como ignorado",
            level=EventLevel.info,
            category="approval",
            device_id=device.id,
        )
    )
    await session.commit()
    return await _get(session, device_id)


@router.delete("/{device_id}", status_code=204)
async def delete_device(device_id: int, session: AsyncSession = Depends(get_session)):
    device = await _get(session, device_id)
    await session.delete(device)
    await session.commit()


@router.get("/{device_id}/history", response_model=list[ConnectionOut])
async def device_history(
    device_id: int,
    session: AsyncSession = Depends(get_session),
    limit: int = Query(100, le=1000),
):
    res = await session.execute(
        select(ConnectionHistory)
        .where(ConnectionHistory.device_id == device_id)
        .order_by(ConnectionHistory.timestamp.desc())
        .limit(limit)
    )
    return list(res.scalars())


@router.get("/{device_id}/uptime")
async def device_uptime_route(
    device_id: int,
    session: AsyncSession = Depends(get_session),
    days: int = Query(30, ge=1, le=365),
):
    """Fraction of the last `days` this device was online (from its join/leave
    history). `ratio` is null when there isn't enough history yet."""
    return await uptime.device_uptime(session, device_id, days)


async def _fold_into(session: AsyncSession, target_id: int, src_id: int) -> None:
    """Move every child row of src onto target and delete src. Pure Core."""
    rows = (
        await session.execute(
            select(
                Device.id, Device.first_seen, Device.last_seen, Device.is_online
            ).where(Device.id.in_([target_id, src_id]))
        )
    ).all()
    by_id = {r.id: r for r in rows}
    if target_id not in by_id or src_id not in by_id:
        return
    t, s = by_id[target_id], by_id[src_id]

    # Drop src rows that would collide with a per-device unique key on target.
    dup_ports = (
        await session.execute(
            select(OpenPort.port).where(OpenPort.device_id == target_id)
        )
    ).scalars().all()
    if dup_ports:
        await session.execute(
            OpenPort.__table__.delete().where(
                OpenPort.device_id == src_id, OpenPort.port.in_(dup_ports)
            )
        )

    for table in (MacAddress, IpAddress, OpenPort, ConnectionHistory, DeviceImage, Event):
        await session.execute(
            table.__table__.update()
            .where(table.device_id == src_id)
            .values(device_id=target_id)
        )
    await session.execute(
        Device.__table__.update()
        .where(Device.id == target_id)
        .values(
            first_seen=min(t.first_seen, s.first_seen),
            last_seen=max(t.last_seen, s.last_seen),
            is_online=t.is_online or s.is_online,
        )
    )
    await session.execute(Device.__table__.delete().where(Device.id == src_id))


@router.post("/{device_id}/merge", response_model=DeviceOut)
async def merge_devices(
    device_id: int, payload: MergeRequest, session: AsyncSession = Depends(get_session)
):
    """Fold source devices into this one (MACs, IPs, ports, history, images)."""
    await _get(session, device_id)
    n = 0
    for src_id in payload.source_ids:
        if src_id != device_id:
            await _fold_into(session, device_id, src_id)
            n += 1
    await session.commit()
    merged = await _get(session, device_id)
    session.add(
        Event(
            message=f"{n} dispositivo(s) fundido(s) em {merged.display_name}",
            level=EventLevel.info,
            category="merge",
            device_id=device_id,
        )
    )
    await session.commit()
    return await _get(session, device_id)


@router.post("/{device_id}/wake")
async def wake_device(device_id: int, session: AsyncSession = Depends(get_session)):
    """Queue a Wake-on-LAN for this device. The agents send the magic packet on
    their next check-in; the panel can't reach the network itself."""
    device = await _get(session, device_id)
    primary = device.macs[0] if device.macs else None
    if primary is None:
        raise HTTPException(422, "Device has no MAC address to wake")
    if primary.is_random:
        raise HTTPException(422, "A randomised MAC can't be used for Wake-on-LAN")
    norm = await wol.queue(session, primary.address, device.id)
    if norm is None:
        raise HTTPException(422, f"Not a usable MAC address: {mac}")
    session.add(
        Event(
            message=f"Wake-on-LAN enviado a {device.display_name}",
            level=EventLevel.info,
            category="presence",
            device_id=device.id,
        )
    )
    await session.commit()
    return {"ok": True, "mac": norm}


@router.post("/{device_id}/absorb-mac", response_model=DeviceOut)
async def absorb_mac(
    device_id: int,
    payload: AbsorbMacRequest,
    session: AsyncSession = Depends(get_session),
):
    """Attach another MAC to this device so it can have several.

    If the MAC currently belongs to another device, it (and its IPs / ports /
    history) are moved here; a source device left with no MACs is deleted.
    """
    await _get(session, device_id)
    addr = payload.address.strip().lower()

    mac = (
        await session.execute(select(MacAddress).where(MacAddress.address == addr))
    ).scalars().first()

    if mac is None:
        session.add(MacAddress(device_id=device_id, address=addr))
        await session.commit()
        return await _get(session, device_id)

    if mac.device_id == device_id:
        raise HTTPException(400, "MAC já pertence a este dispositivo")

    await _fold_into(session, device_id, mac.device_id)
    await session.commit()

    merged = await _get(session, device_id)
    session.add(
        Event(
            message=f"MAC {addr} fundido em {merged.display_name}",
            level=EventLevel.info,
            category="merge",
            device_id=device_id,
        )
    )
    await session.commit()
    return await _get(session, device_id)


@router.delete("/{device_id}/macs/{address}", response_model=DeviceOut)
async def detach_mac(
    device_id: int, address: str, session: AsyncSession = Depends(get_session)
):
    device = await _get(session, device_id)
    if len(device.macs) <= 1:
        raise HTTPException(400, "O dispositivo tem de ter pelo menos um MAC")
    mac = next((m for m in device.macs if m.address == address.lower()), None)
    if mac is None:
        raise HTTPException(404, "MAC not found")
    await session.delete(mac)
    await session.commit()
    return await _get(session, device_id)


@router.post("/{device_id}/images", response_model=DeviceOut)
async def upload_image(
    device_id: int,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    device = await _get(session, device_id)
    ext = Path(file.filename or "").suffix.lower() or ".jpg"
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        raise HTTPException(400, "Unsupported image type")
    fname = f"dev{device_id}-{uuid.uuid4().hex[:12]}{ext}"
    dest = UPLOAD_DIR / fname
    await save_image_upload(file, dest, max_bytes=settings.max_upload_bytes)
    device.images.append(DeviceImage(filename=fname, is_primary=not device.images))
    await session.commit()
    return await _get(session, device_id)


@router.delete("/{device_id}/images/{image_id}", response_model=DeviceOut)
async def delete_image(
    device_id: int, image_id: int, session: AsyncSession = Depends(get_session)
):
    device = await _get(session, device_id)
    img = next((i for i in device.images if i.id == image_id), None)
    if img is None:
        raise HTTPException(404, "Image not found")
    (UPLOAD_DIR / img.filename).unlink(missing_ok=True)
    await session.delete(img)
    await session.commit()
    return await _get(session, device_id)
