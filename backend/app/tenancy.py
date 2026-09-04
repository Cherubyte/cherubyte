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
from collections.abc import Callable
from contextvars import ContextVar
from typing import Generic, TypeVar

from fastapi import HTTPException
from starlette.types import ASGIApp, Receive, Scope, Send

from .config import settings

logger = logging.getLogger("cherubyte.tenancy")

V = TypeVar("V")

# A tenant id becomes a file name under tenants_dir, so this is a path-safety
# rule before it is a naming rule: lower-case, no dots, no separators, nothing
# that a filesystem could read as anything but a single segment.
TENANT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,63}$")

current_tenant: ContextVar[str | None] = ContextVar("current_tenant", default=None)


class PerTenant(Generic[V]):
    """One value per tenant, for state a module would otherwise hold once.

    A plain module-level cache is not safe here. Two requests share one event
    loop, so whichever entered last has already overwritten the dict by the
    time the first resumes — and the panel rewrites exactly this kind of cache
    on entering a tenant's scope, so the overwrite is not hypothetical.
    `settings` sidesteps it with a ContextVar overlay; everything else that
    caches per-tenant state needs the same guarantee, which is what this is.

    Keyed by `None` for the single-tenant panel, where there is exactly one
    value and `current_tenant` is never set.
    """

    __slots__ = ("_factory", "_values")

    def __init__(self, factory: Callable[[], V]) -> None:
        self._factory = factory
        self._values: dict[str | None, V] = {}

    def get(self) -> V:
        key = current_tenant.get() if settings.multi_tenant else None
        if key not in self._values:
            self._values[key] = self._factory()
        return self._values[key]

    def forget(self, tenant_id: str) -> None:
        """Drop one tenant's value — offboarding, and tests."""
        self._values.pop(tenant_id, None)

    def clear(self) -> None:
        """Drop every tenant's value — tests."""
        self._values.clear()

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

    def _misrouted(self, scope: Scope) -> str | None:
        """The upstream name the router meant, when it is not this process.

        Only checked when this process has been given a name, which is only
        the case during a blue/green rollout. The router is what stops two
        panel versions writing one tenant's SQLite file; this catches the
        router being wrong, because without it the symptom is a corrupted
        database instead of an error.
        """
        if not settings.upstream_name:
            return None
        wanted = settings.upstream_header.lower().encode("latin-1")
        for name, value in scope.get("headers", ()):
            if name == wanted:
                meant = value.decode("latin-1").strip()
                return meant if meant != settings.upstream_name else None
        return None

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

        meant = self._misrouted(scope)
        if meant is not None:
            # 421 Misdirected Request, which is exactly what this is: the
            # request arrived at a server that is not authoritative for it.
            logger.error(
                "Refusing a request routed to %r; this process is %r. The router "
                "and this process disagree about who owns the tenant, and serving "
                "it would put two schema versions on one database.",
                meant,
                settings.upstream_name,
            )
            await _refuse(send, 421, b"Misdirected request")
            return

        tenant = self._resolve(scope)
        if tenant is None and _is_page_request(scope):
            # A browser asking for a page, with no session: send it to the
            # login window rather than answer JSON it cannot do anything with.
            # Without this the panel's own SPA is stranded after a sign-out or
            # an expired session — it holds a screen full of stale data and
            # never navigates, because every call it makes comes back 401.
            # API calls still get the 401; only a document navigation moves.
            await _redirect(send, settings.login_path)
            return

        token = current_tenant.set(tenant)
        try:
            await self.app(scope, receive, send)
        finally:
            current_tenant.reset(token)


def _is_page_request(scope: Scope) -> bool:
    """A browser navigating, rather than the SPA calling its API."""
    if scope.get("method") not in ("GET", "HEAD"):
        return False
    path = scope.get("path", "")
    if path.startswith("/api/") or path.startswith("/uploads/") or path.startswith("/assets/"):
        return False
    for name, value in scope.get("headers", ()):
        if name == b"accept":
            return b"text/html" in value
    return False


async def _refuse(send: Send, status: int, body: bytes) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"text/plain; charset=utf-8"),
                (b"content-length", str(len(body)).encode("ascii")),
                (b"cache-control", b"no-store"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


async def _redirect(send: Send, location: str) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 302,
            "headers": [
                (b"location", location.encode("latin-1")),
                (b"content-length", b"0"),
                # An unauthenticated redirect must never be what a cache
                # serves to the next person who asks for this page.
                (b"cache-control", b"no-store"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": b""})
