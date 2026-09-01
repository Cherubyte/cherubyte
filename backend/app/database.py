"""Engines, sessions and the schema — for one database, or one per tenant.

A self-hosted panel is one SQLite file, and everything here that has a bare
name — `engine`, `SessionLocal`, `init_db()` — is that file, unchanged. The
hosted panel runs many tenants in one process with a file each; that mode is
off by default and, when on, leaves the bare names in place but makes the one
that would silently reach a shared database refuse instead.
"""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from collections.abc import AsyncGenerator
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from .config import BASE_DIR, settings
from .tenancy import current_tenant, validate_tenant_id

logger = logging.getLogger("cherubyte.db")


def _sqlite_pragmas(dbapi_conn, _record):
    """WAL + a generous busy timeout so the live service and one-off scripts
    can touch the DB concurrently without 'database is locked'."""
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=8000")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.close()


def _make_engine(url: str) -> AsyncEngine:
    """An engine with the pragmas every Cherubyte database gets."""
    eng = create_async_engine(url, echo=False, future=True)
    event.listens_for(eng.sync_engine, "connect")(_sqlite_pragmas)
    return eng


def _sessions(eng: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(eng, expire_on_commit=False, class_=AsyncSession)


# ── the single-tenant database ─────────────────────────────────────────────
# The whole story for a self-hosted panel, kept at module level so scripts,
# tests and the scheduler can reach it by name as they always have.

engine = _make_engine(settings.database_url)
_default_sessions = _sessions(engine)


class _SingleTenantSessions:
    """`SessionLocal()` — a session on the default database.

    In multi-tenant mode there is no default database, so a call here is a
    bug: some job or service is about to read or write somewhere that belongs
    to nobody, or to everybody. Raise, name the fix, and make it impossible to
    miss. In single-tenant mode this is the sessionmaker it always was.
    """

    def __call__(self, *args, **kwargs) -> AsyncSession:
        if settings.multi_tenant:
            raise RuntimeError(
                "SessionLocal() has no tenant in multi-tenant mode; "
                "use session_for(tenant_id), or get_session() inside a request"
            )
        return _default_sessions(*args, **kwargs)


SessionLocal = _SingleTenantSessions()


# ── one database per tenant ────────────────────────────────────────────────


def tenant_db_path(tenant_id: str) -> Path:
    return Path(settings.tenants_dir) / f"{validate_tenant_id(tenant_id)}.db"


class _TenantEngines:
    """Open engines, one per tenant, bounded.

    Each engine holds a connection and SQLite's page cache, and how many of
    those are open is what decides how many tenants fit in a small box — CPU
    has room for hundreds. Past the cap the least recently used is disposed;
    it comes back on that tenant's next request, a few milliseconds later.

    Opening never creates a file unless asked. A request for a tenant that was
    never provisioned must not leave an empty database behind that the next
    request then finds and treats as real.
    """

    def __init__(self) -> None:
        self._open: OrderedDict[str, tuple[AsyncEngine, async_sessionmaker[AsyncSession]]] = (
            OrderedDict()
        )
        self._lock = asyncio.Lock()

    async def get(
        self, tenant_id: str, *, create: bool = False
    ) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
        tenant_id = validate_tenant_id(tenant_id)
        evicted: list[AsyncEngine] = []
        async with self._lock:
            found = self._open.get(tenant_id)
            if found is not None:
                self._open.move_to_end(tenant_id)
                return found

            path = tenant_db_path(tenant_id)
            if not path.is_file():
                if not create:
                    raise LookupError(tenant_id)
                path.parent.mkdir(parents=True, exist_ok=True)

            eng = _make_engine(f"sqlite+aiosqlite:///{path}")
            entry = (eng, _sessions(eng))
            self._open[tenant_id] = entry
            while len(self._open) > max(1, settings.tenant_engine_cache):
                _, (old, _) = self._open.popitem(last=False)
                evicted.append(old)

        # Outside the lock: dispose can take a moment and nothing else needs
        # to wait on it.
        for old in evicted:
            await old.dispose()
        return entry

    async def dispose_all(self) -> None:
        async with self._lock:
            engines = [eng for eng, _ in self._open.values()]
            self._open.clear()
        for eng in engines:
            await eng.dispose()

    def __len__(self) -> int:
        return len(self._open)

    def __contains__(self, tenant_id: object) -> bool:
        return tenant_id in self._open


_tenants = _TenantEngines()


async def engine_for(tenant_id: str, *, create: bool = False) -> AsyncEngine:
    """One tenant's engine. LookupError if it was never provisioned."""
    eng, _ = await _tenants.get(tenant_id, create=create)
    return eng


async def session_for(tenant_id: str) -> AsyncSession:
    """A session on one tenant's database, for jobs and services that run
    outside a request. Requests get theirs from get_session()."""
    _, make = await _tenants.get(tenant_id)
    return make()


async def dispose_tenants() -> None:
    await _tenants.dispose_all()


# ── the request's session ──────────────────────────────────────────────────


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """The session every route depends on.

    Single-tenant: the one database. Multi-tenant: the database of the tenant
    the middleware resolved, and a refusal if it resolved none. There is no
    shared database to fall back to, and falling back is how one customer
    reads another's inventory.
    """
    if not settings.multi_tenant:
        async with _default_sessions() as session:
            yield session
        return

    tenant = current_tenant.get()
    if tenant is None:
        raise HTTPException(401, "No tenant")
    try:
        _, make = await _tenants.get(tenant)
    except LookupError:
        raise HTTPException(404, "Unknown tenant") from None
    async with make() as session:
        yield session


# ── schema ─────────────────────────────────────────────────────────────────


class Base(DeclarativeBase):
    pass


# Additive columns from before Alembic (see alembic/versions/baseline.py).
# Frozen — the schema these columns belong to is exactly what "baseline"
# recreates from nothing, so nothing new gets added here; a real Alembic
# migration handles anything from here on. Still run every start, because
# an old, never-upgraded install may be missing any subset of these.
# (table, column, ddl)
_MIGRATIONS: tuple[tuple[str, str, str], ...] = (
    ("devices", "counts_for_presence", "BOOLEAN NOT NULL DEFAULT 1"),
    ("devices", "model", "VARCHAR(255)"),
    ("devices", "os_guess", "VARCHAR(255)"),
    ("devices", "overrides", "VARCHAR(255)"),
    ("devices", "notify_policy", "VARCHAR(16) NOT NULL DEFAULT 'default'"),
    ("devices", "fingerprint", "TEXT"),
    ("devices", "tags", "VARCHAR(255)"),
    ("users", "is_guest", "BOOLEAN NOT NULL DEFAULT 0"),
    ("agents", "public_ip", "VARCHAR(45)"),
    ("agents", "public_ip_at", "DATETIME"),
    ("agents", "last_ip", "VARCHAR(45)"),
    ("agents", "health_port", "INTEGER NOT NULL DEFAULT 1002"),
    ("agents", "scan_requested", "BOOLEAN NOT NULL DEFAULT 0"),
)

# Same idea, for indexes. Also frozen; also still applied every start for the
# same reason. (name, table, columns)
_INDEXES: tuple[tuple[str, str, str], ...] = (
    # the presence grid reads one device's history inside a time window
    ("ix_conn_history_device_ts", "connection_history", "device_id, timestamp"),
)


def _migrate_with_alembic(connection) -> None:
    """Bring the schema the rest of the way with Alembic, reusing the
    connection already open in init_db()'s transaction rather than a second
    one — see alembic/env.py's `connection` attribute handoff.

    By the time this runs, create_all plus the additive patches above have
    already brought the database — brand new or years old — to exactly the
    schema alembic/versions/baseline.py builds from nothing. So: a database
    Alembic has never touched is stamped at "baseline" without re-running its
    DDL (the two are already identical), then whatever migrations exist
    beyond baseline apply normally. A database already on Alembic just
    upgrades — this is a no-op once it's current.
    """
    from alembic import command
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext

    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.attributes["connection"] = connection
    if not MigrationContext.configure(connection).get_current_heads():
        command.stamp(cfg, "baseline")
    command.upgrade(cfg, "head")


async def init_db(target: AsyncEngine | None = None) -> None:
    """Bring one database to the current schema.

    No argument is the single-tenant database, as it always was. Provisioning
    passes a tenant's engine, and every release runs this once per tenant —
    which is why it has to stay idempotent: a run that dies halfway through
    twenty-five databases has to be safe to start again from the top.
    """
    from sqlalchemy import text

    from . import models  # noqa: F401  (register mappers)

    eng = target if target is not None else engine
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for table, column, ddl in _MIGRATIONS:
            cols = await conn.execute(text(f"PRAGMA table_info({table})"))
            if column not in {row[1] for row in cols}:
                await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
        for name, table, columns in _INDEXES:
            await conn.execute(
                text(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({columns})")
            )
        await conn.run_sync(_migrate_with_alembic)


async def provision_tenant(tenant_id: str) -> Path:
    """Create a tenant's database, or bring an existing one up to date.

    Idempotent, because init_db() is. The file is the tenant: there is no
    registry here to keep in step with it, which is one less thing to drift.
    """
    eng = await engine_for(tenant_id, create=True)
    await init_db(eng)
    return tenant_db_path(tenant_id)
