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


class TenantMiddleware:
    """Set the current tenant from the edge's header, for the span of one request.

    Pure ASGI rather than BaseHTTPMiddleware: that one runs the downstream app
    in a separate task, where a ContextVar set here is not visible. It is also
    cheaper, and this runs on every request.

    Installed only in multi-tenant mode. In single-tenant mode the header is
    never read at all, so a stray one on a self-hosted panel means nothing.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._header = settings.tenant_header.lower().encode("latin-1")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        tenant: str | None = None
        for name, value in scope.get("headers", ()):
            if name == self._header:
                try:
                    tenant = validate_tenant_id(value.decode("latin-1"))
                except ValueError:
                    # Ends in the same 401 as no header, but a malformed id is
                    # a different event — either the edge is broken or someone
                    # is poking at the origin directly — and should be seen.
                    logger.warning("Refusing malformed tenant header")
                break

        token = current_tenant.set(tenant)
        try:
            await self.app(scope, receive, send)
        finally:
            current_tenant.reset(token)
