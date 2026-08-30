from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings

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


# Additive columns added after the first release. SQLite's create_all won't
# touch existing tables, so we patch them in on startup. (table, column, ddl)
_MIGRATIONS: tuple[tuple[str, str, str], ...] = (
    ("devices", "counts_for_presence", "BOOLEAN NOT NULL DEFAULT 1"),
    ("devices", "model", "VARCHAR(255)"),
    ("devices", "os_guess", "VARCHAR(255)"),
    ("devices", "overrides", "VARCHAR(255)"),
    ("devices", "notify_policy", "VARCHAR(16) NOT NULL DEFAULT 'default'"),
    ("users", "is_guest", "BOOLEAN NOT NULL DEFAULT 0"),
    ("agents", "public_ip", "VARCHAR(45)"),
    ("agents", "public_ip_at", "DATETIME"),
    ("agents", "last_ip", "VARCHAR(45)"),
    ("agents", "health_port", "INTEGER NOT NULL DEFAULT 1002"),
    ("agents", "scan_requested", "BOOLEAN NOT NULL DEFAULT 0"),
)

# Indexes added after the first release, applied the same way. (name, table, columns)
_INDEXES: tuple[tuple[str, str, str], ...] = (
    # the presence grid reads one device's history inside a time window
    ("ix_conn_history_device_ts", "connection_history", "device_id, timestamp"),
)


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


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
