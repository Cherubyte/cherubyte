"""Map opaque model identifiers (mostly Apple + a few others) to readable names."""

from __future__ import annotations

import re

_EXACT: dict[str, str] = {
    # Apple TV
    "AppleTV5,3": "Apple TV HD",
    "AppleTV6,2": "Apple TV 4K",
    "AppleTV11,1": "Apple TV 4K (2nd gen)",
    "AppleTV14,1": "Apple TV 4K (3rd gen)",
    # HomePod
    "AudioAccessory1,1": "HomePod",
    "AudioAccessory5,1": "HomePod mini",
    "AudioAccessory6,1": "HomePod (2nd gen)",
    # Chromecast / Google
    "Chromecast": "Chromecast",
    "Chromecast Ultra": "Chromecast Ultra",
    "Google Home": "Google Home",
    "Google Home Mini": "Google Nest Mini",
    "Google Nest Hub": "Google Nest Hub",
}

_PREFIX: list[tuple[str, str]] = [
    ("iPhone", "iPhone"),
    ("iPad", "iPad"),
    ("Watch", "Apple Watch"),
    ("MacBookPro", "MacBook Pro"),
    ("MacBookAir", "MacBook Air"),
    ("MacBook", "MacBook"),
    ("Macmini", "Mac mini"),
    ("MacPro", "Mac Pro"),
    ("iMac", "iMac"),
    ("Mac", "Mac"),
    ("RP", "Raspberry Pi"),
]


def prettify_model(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = raw.strip()
    if raw in _EXACT:
        return _EXACT[raw]
    # "J413AP" style board ids -> leave, not helpful
    if re.fullmatch(r"[A-Z]\d+[A-Z]{2}", raw):
        return None
    for pre, label in _PREFIX:
        if raw.startswith(pre) and re.match(rf"{pre}\d", raw):
            return label
    # already human ("Chromecast", "Sonos One", "TS-451+")
    if " " in raw or "-" in raw or raw.istitle():
        return raw
    return raw
