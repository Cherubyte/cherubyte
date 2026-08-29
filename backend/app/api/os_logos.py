from __future__ import annotations

from ..models import OsLogo
from ._logostore import build_router

router = build_router(
    prefix="/os",
    tag="os",
    model=OsLogo,
    counter=lambda d: d.os_family,
    file_prefix="os",
    skip_unkeyed=True,
)
