from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import BASE_DIR, settings

engine = create_async_engine(settings.database_url, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@event.listens_for(engine.sync_engine, "connect")
def _sqlite_pragmas(dbapi_conn, _record):
    """WAL + a generous busy timeout so the live service and one-off scripts
    can touch the DB concurrently without 'database is locked'."""
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=8000")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.close()


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


async def init_db() -> None:
    from sqlalchemy import text

    from . import models  # noqa: F401  (register mappers)

    async with engine.begin() as conn:
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


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
