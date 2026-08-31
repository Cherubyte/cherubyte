"""Deciding what a device is called, from what an agent saw.

This is interpretation, not observation, so it lives with the panel: improving
how a name is chosen ships as a panel release and applies to every agent
already in the field, including old ones.
"""

from __future__ import annotations

import re

from cherubyte_protocol import HostObservation

from .apple_models import prettify_model


def looks_generic(name: str) -> bool:
    n = name.lower().strip()
    return (
        n in {"", "localhost", "unknown", "espressif", "amazon", "-"}
        or n.startswith("android-")
        or n.replace("-", "").replace(":", "").isdigit()
    )


def clean_name(name: str) -> str:
    import re

    n = name.strip().rstrip(".")
    n = re.sub(r"^[0-9A-Fa-f]{6,16}@", "", n)        # raop "AABBCC@Name"
    n = re.sub(r"\s*\[[0-9a-fA-F:]{6,}\]\s*$", "", n)  # "Name [aa:bb:cc:..]"
    for suf in (".local", ".lan", ".home", ".fritz.box", ".hub"):
        if n.lower().endswith(suf):
            n = n[: -len(suf)]
    n = n.replace("_", " ").strip()
    # "Sams-MacBook-Pro-2" -> "Sams MacBook Pro 2" reads better untouched;
    # only de-dash when it's clearly a single hyphenated hostname token
    return n



def best_name(obs: HostObservation) -> str | None:
    """The friendliest name any probe produced for this host."""
    ordered = [
        obs.mdns_name,
        obs.ssdp_name,
        obs.hostname,
        obs.netbios_name,
        obs.http_title,
    ]
    good = [clean_name(c) for c in ordered if c and not looks_generic(c)]
    if good:
        # when reverse-DNS and NetBIOS agree on a prefix, keep the longer form
        return max(good[:2], key=len) if len(good) >= 2 and (
            good[0].lower().startswith(good[1].lower()[:8])
            or good[1].lower().startswith(good[0].lower()[:8])
        ) else good[0]
    for cand in ordered:
        if cand:
            return clean_name(cand)
    return None


def best_model(obs: HostObservation) -> str | None:
    raw = obs.mdns_model or obs.ssdp_model
    return prettify_model(raw) if raw else None
