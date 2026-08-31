"""Suggest merges for devices that are really one phone behind a rotating MAC.

Modern phones randomise their MAC per network and re-roll it periodically, so a
single handset turns into a stream of "new device" entries. The scanner already
records `is_random`; this reads it back and proposes the merges.

The test is deliberately conservative — a wrong merge is worse than a missed
one — so a pair is only suggested when the identities agree and the two were
never online at the same time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models import Device

# how far apart two sightings may be and still look like the same handset
MAX_GAP = timedelta(days=30)


@dataclass
class Suggestion:
    target: Device          # the older device, which should absorb the others
    duplicates: list[Device]
    reason: str

    @property
    def confidence(self) -> str:
        return "high" if "model" in self.reason else "medium"


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _all_macs_random(device: Device) -> bool:
    return bool(device.macs) and all(m.is_random for m in device.macs)


def _identity(device: Device) -> tuple[str, str] | None:
    """What makes two entries look like the same handset, strongest first."""
    model = (device.model or "").strip().lower()
    if model:
        return ("model", model)
    host = (device.hostname or "").strip().lower()
    if host:
        return ("name", host)
    return None


def _overlaps(a: Device, b: Device) -> bool:
    """True if both were on the network at once — then they are not the same one."""
    return (
        _aware(a.first_seen) <= _aware(b.last_seen)
        and _aware(b.first_seen) <= _aware(a.last_seen)
    )


def _too_far_apart(a: Device, b: Device) -> bool:
    later, earlier = sorted((a, b), key=lambda d: _aware(d.first_seen), reverse=True)
    return _aware(later.first_seen) - _aware(earlier.last_seen) > MAX_GAP


def find(devices: list[Device]) -> list[Suggestion]:
    candidates = [d for d in devices if _all_macs_random(d) and _identity(d)]
    groups: dict[tuple[str, str], list[Device]] = {}
    for device in candidates:
        groups.setdefault(_identity(device), []).append(device)

    suggestions: list[Suggestion] = []
    for (basis, value), members in groups.items():
        if len(members) < 2:
            continue
        members.sort(key=lambda d: _aware(d.first_seen))
        target = members[0]
        duplicates = [
            d
            for d in members[1:]
            if not _overlaps(target, d) and not _too_far_apart(target, d)
        ]
        if not duplicates:
            continue
        suggestions.append(
            Suggestion(
                target=target,
                duplicates=duplicates,
                reason=f"Random MAC and the same {basis} ({value})",
            )
        )
    suggestions.sort(key=lambda s: len(s.duplicates), reverse=True)
    return suggestions


async def suggestions(session: AsyncSession) -> list[Suggestion]:
    res = await session.execute(select(Device).options(selectinload(Device.macs)))
    return find(list(res.scalars().unique()))
