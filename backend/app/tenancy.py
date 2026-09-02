"""Which tenant a request belongs to.

Multi-tenant mode puts every customer in one process with a database file
each, so the question every query has to answer first is *whose*. The answer
lives in a context variable, set once per request by the middleware below and
read by database.get_session(). Nothing else should need to know.

Fail closed. A request with no tenant is refused, never served from a default
database — there is no default: in multi-tenant mode a shared database is the
one thing that must not exist.
"""

from __future__ import annotations

import logging
import re
from contextvars import ContextVar

from fastapi import HTTPException
from starlette.types import ASGIApp, Receive, Scope, Send

from .config import settings

logger = logging.getLogger("cherubyte.tenancy")

# A tenant id becomes a file name under tenants_dir, so this is a path-safety
# rule before it is a naming rule: lower-case, no dots, no separators, nothing
# that a filesystem could read as anything but a single segment.
TENANT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,63}$")

current_tenant: ContextVar[str | None] = ContextVar("current_tenant", default=None)

# Agent keys and enrolment tokens minted for a tenant carry the tenant in
# front: `t.<tenant>.<random>`. The edge routes an agent's request on that
# prefix alone — no lookup per report, and no shared table of every tenant's
# secrets for the edge to hold. The prefix is not secret and adds nothing to
# the hash; it is an address, and the random part after it is the key.
#
# The separator is a dot because it is the one character neither side can
# contain: a tenant id is [a-z0-9_-] and token_urlsafe emits [A-Za-z0-9_-],
# both of which include `_` and `-`. With either of those as the separator,
# tenant `abc_d` + random `R…` and tenant `abc` + random `d_R…` are the same
# string, and a regex leaning either way hands the edge the wrong tenant.
SECRET_PREFIX_RE = re.compile(r"^t\.([a-z0-9][a-z0-9_-]{2,63})\.([A-Za-z0-9_-]{16,})$")


def tenant_from_secret(secret: object) -> str | None:
    """The tenant an agent secret was minted for, or None for a plain one.

    A malformed prefix reads as None rather than as a partial tenant: the
    edge then has no tenant to forward, and the origin refuses. The rule is
    mirrored in the Worker; change one and change both.
    """
    if not isinstance(secret, str):
        return None
    m = SECRET_PREFIX_RE.fullmatch(secret)
    return m.group(1) if m else None


def validate_tenant_id(value: object) -> str:
    """The id if it is safe to use as a path segment, else ValueError."""
    if not isinstance(value, str) or not TENANT_ID_RE.fullmatch(value):
        raise ValueError("invalid tenant id")
    return value


def require_tenant() -> str:
    """The current tenant, or a 401. Only meaningful in multi-tenant mode."""
    tenant = current_tenant.get()
    if tenant is None:
        raise HTTPException(401, "No tenant")
    return tenant


SESSION_COOKIE = "cherubyte_session"


def _cookie(header: str, name: str) -> str | None:
    for part in header.split(";"):
        k, _, v = part.strip().partition("=")
        if k == name:
            return v
    return None


def _bearer(header: str) -> str:
    scheme, _, rest = header.strip().partition(" ")
    return rest.strip() if scheme.lower() == "bearer" else ""


class TenantMiddleware:
    """Work out whose request this is, for the span of one request.

    The credential decides, not the header. A session cookie and an agent key
    both carry the tenant they were minted for, so the answer comes from the
    thing the caller had to hold — and somebody who sets the header to another
    tenant is routed to their own database rather than that one. The header is
    a fallback for internal callers that have no credential yet: the login
    service asking a specific tenant a question, and provisioning.

    That ordering matters now that the panel answers the internet directly.
    Trusting the header first would let a valid session for one tenant be
    pointed at another; it would still fail there, since the token is not in
    that database, but "fails closed" is a worse property than "cannot be
    aimed" when the fix costs nothing.

    Pure ASGI rather than BaseHTTPMiddleware: that one runs the downstream app
    in a separate task, where a ContextVar set here is not visible.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._header = settings.tenant_header.lower().encode("latin-1")

    def _resolve(self, scope: Scope) -> str | None:
        header_value: str | None = None
        cookie_header = ""
        auth_header = ""
        for name, value in scope.get("headers", ()):
            if name == self._header:
                header_value = value.decode("latin-1")
            elif name == b"cookie":
                cookie_header = value.decode("latin-1")
            elif name == b"authorization":
                auth_header = value.decode("latin-1")

        # 1. the browser's own session
        session = _cookie(cookie_header, SESSION_COOKIE)
        if session:
            found = tenant_from_secret(session)
            if found:
                return found

        # 2. an agent's key
        key = _bearer(auth_header)
        if key:
            found = tenant_from_secret(key)
            if found:
                return found

        # 3. an internal caller that has no credential yet
        if header_value is not None:
            try:
                return validate_tenant_id(header_value)
            except ValueError:
                # Ends in the same 401 as no tenant, but a malformed id is a
                # different event — something is broken or somebody is poking
                # at the panel — and should be seen.
                logger.warning("Refusing malformed tenant header")
        return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        token = current_tenant.set(self._resolve(scope))
        try:
            await self.app(scope, receive, send)
        finally:
            current_tenant.reset(token)
