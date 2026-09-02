from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .api import api_router
from .api.settings import _load_from_db
from . import crypto
from .api._uploads import UPLOAD_AAD
from .config import APP_VERSION, UPLOAD_DIR, settings, upload_dir
from .database import SessionLocal, dispose_tenants, init_db
from .scheduler import scheduler, start as start_scheduler
from .services import mqtt, oui, update
from .services.retention import run_purge
from .tenancy import TenantMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
logger = logging.getLogger("cherubyte")


async def _upgrade_every_tenant() -> None:
    """Bring every existing tenant's schema up to date at startup.

    Single-tenant does this on the one database and always has. Hosted did it
    only when a tenant was *created*, so a deploy that added a column reached
    new tenants and nobody else — the schema silently drifted per file, and
    the first symptom was a query failing on one customer and not another.

    Idempotent, and a few milliseconds each: create_all finds nothing to do
    and Alembic finds nothing to run once a database is current. A tenant
    whose upgrade fails is logged and skipped rather than taking the whole
    service down with it, since the others are fine and one broken file
    should not be an outage for everyone.
    """
    from .database import known_tenants, provision_tenant

    tenants = known_tenants()
    for tenant_id in tenants:
        try:
            await provision_tenant(tenant_id)
        except Exception:
            logger.exception("Could not upgrade the schema for %s", tenant_id)
    if tenants:
        logger.info("Schema checked for %d tenant(s)", len(tenants))


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.multi_tenant:
        # No default database to initialise and no one set of settings to
        # load: each tenant brings both, inside `scoped_to`. The scheduler
        # runs the per-tenant jobs. MQTT stays off — its queue, worker and
        # announced-set are process-global, so on a shared process it would
        # publish one tenant's devices under another's discovery topics; it
        # moves to the agent, which is on the LAN the broker is on anyway.
        await _upgrade_every_tenant()
        start_scheduler()
        logger.info("Cherubyte up on :%s — hosted", settings.port)
        yield
        scheduler.shutdown(wait=False)
        await dispose_tenants()
        return

    await init_db()
    async with SessionLocal() as session:
        await _load_from_db(session)
    start_scheduler()
    mqtt.start()

    import asyncio

    # the OUI vendor database is the panel's: one copy, shared by every agent
    asyncio.create_task(oui.refresh_db())
    # the purge job only fires 24h in; a box that reboots daily would never
    # reach it, so run one pass at startup too
    asyncio.create_task(run_purge())
    # same for the update check — don't make a fresh install wait 12h to learn
    # it's already current
    asyncio.create_task(update.check())
    logger.info("Cherubyte up on :%s", settings.port)
    yield
    mqtt.stop()
    scheduler.shutdown(wait=False)


app = FastAPI(title="Cherubyte", version=APP_VERSION, lifespan=lifespan)

# Outermost, so the tenant is known before anything else looks at the request.
# Only in multi-tenant mode: a self-hosted panel never reads the header, so a
# stray one cannot mean anything there.
if settings.multi_tenant:
    app.add_middleware(TenantMiddleware)

# The SPA is served from this same origin in production, and in development the
# Vite server proxies /api and /uploads server-side — neither makes a
# cross-origin request. So CORS stays off unless explicitly configured;
# `allow_origins=["*"]` on an unauthenticated LAN service let any website the
# user happened to visit read their whole device inventory and call the write
# endpoints.
_cors_origins = settings.cors_origin_list
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.info("CORS enabled for %s", ", ".join(_cors_origins))

app.include_router(api_router)


# Uploads are served by a route rather than a static mount, in both modes.
# Guessed from the extension, which `save_image_upload` has already checked
# against the file's actual leading bytes. Encrypted files are served from
# memory, so there is no path for FileResponse to sniff.
_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
}


# A mount is bound to one directory at import time, and hosted there is no
# one directory: these are photographs of somebody's home and each tenant has
# its own. One code path, resolved per request, so the mode cannot be wrong.
@app.get("/uploads/{name:path}", include_in_schema=False)
async def serve_upload(name: str):
    try:
        root = upload_dir().resolve()
    except (RuntimeError, ValueError):
        # Hosted with no tenant in scope. There is nothing to serve and no
        # shared directory to fall back to, which is the whole point.
        raise HTTPException(401, "No tenant") from None
    try:
        candidate = (root / name).resolve()
    except (OSError, ValueError, RuntimeError):
        raise HTTPException(404, "Not Found") from None
    # The name is attacker-controlled and arrives percent-decoded, so resolve
    # first and then require the result to still be inside — the same rule the
    # SPA fallback follows, and for the same reason.
    if not candidate.is_relative_to(root) or not candidate.is_file():
        raise HTTPException(404, "Not Found")

    blob = candidate.read_bytes()
    if not blob.startswith(crypto.FILE_MAGIC):
        # Never encrypted: self-hosted, or written before this existed.
        # Serving from the path keeps the range and caching headers.
        return FileResponse(candidate)
    try:
        body = crypto.decrypt_bytes(blob, UPLOAD_AAD)
    except crypto.CryptoError:
        # The file is here and unreadable. 404 rather than 500: to the person
        # looking at the page it is a missing picture either way, and a 500 on
        # an <img> tag says more about the server than it needs to.
        logger.exception("Could not decrypt %s", candidate.name)
        raise HTTPException(404, "Not Found") from None
    return Response(body, media_type=_MEDIA_TYPES.get(candidate.suffix.lower(), "image/jpeg"))

# Uploads are user-supplied and served from our own origin. An SVG logo is a
# document, not just a picture: opened directly it could run script here. Deny
# it everything and put it in its own origin.
_UPLOAD_CSP = "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; sandbox"


@app.middleware("http")
async def _harden_uploads(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/uploads/"):
        response.headers["Content-Security-Policy"] = _UPLOAD_CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": app.version}


# --- Serve the built frontend (SPA) -----------------------------------------
_dist = settings.frontend_dist

_NO_FRONTEND = {
    "message": "Cherubyte API is running. Build the frontend "
    "(cd frontend && npm install && npm run build) or use the Vite dev server.",
    "docs": "/docs",
}


def _dist_file(full_path: str) -> Path | None:
    """The file `full_path` names inside the built frontend, or None.

    The request path is attacker-controlled and arrives percent-decoded, so
    `_dist / full_path` alone escaped the directory: a GET for `%2e%2e/%2e%2e/…`
    resolved outside and FileResponse happily served it — arbitrary file read
    with the service's privileges, which include CAP_NET_RAW or root. Resolve
    first, then require the result to still be inside.
    """
    root = _dist.resolve()
    try:
        candidate = (root / full_path).resolve()
    except (OSError, ValueError, RuntimeError):
        return None
    if not candidate.is_relative_to(root):
        return None
    return candidate if candidate.is_file() else None


@app.get("/", include_in_schema=False)
async def index():
    idx = _dist_file("index.html")
    return FileResponse(idx) if idx else JSONResponse(_NO_FRONTEND)


if _dist.exists():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str):
    served = _dist_file(full_path)
    if served is not None:
        return FileResponse(served)
    idx = _dist_file("index.html")
    return FileResponse(idx) if idx else JSONResponse(_NO_FRONTEND, status_code=404)
