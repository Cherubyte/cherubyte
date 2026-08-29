from __future__ import annotations

from ..models import Brand
from ._logostore import build_router

router = build_router(
    prefix="/brands",
    tag="brands",
    model=Brand,
    counter=lambda d: d.short_vendor,
    file_prefix="brand",
)
