from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import api_router
from .api.settings import _load_from_db
from .config import UPLOAD_DIR, settings
from .database import SessionLocal, init_db
from .scheduler import scheduler, start as start_scheduler
from .services import mqtt, oui
from .services.retention import run_purge

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
logger = logging.getLogger("netscan")


@asynccontextmanager
async def lifespan(app: FastAPI):
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
    logger.info("NetScan up on :%s", settings.port)
    yield
    mqtt.stop()
    scheduler.shutdown(wait=False)


app = FastAPI(title="NetScan", version="0.1.0", lifespan=lifespan)

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
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

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
    "message": "NetScan API is running. Build the frontend "
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
