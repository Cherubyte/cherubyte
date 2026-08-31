"""Alembic environment.

Two ways this runs:

  * from the command line (`alembic revision --autogenerate`, `alembic
    upgrade head`) — builds its own sync engine from the app's own
    `database_url` (see `get_url`), so it always points at whatever DB the
    app is actually configured to use, `CHERUBYTE_DATABASE_URL` overrides
    included, rather than a URL hardcoded in alembic.ini that could drift.

  * from `app.database.init_db()` at startup, which is already inside an
    open async-bridged connection (`conn.run_sync(...)`) — passes that
    connection in via `config.attributes["connection"]` so migrations run
    on it directly instead of opening a second one.
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

config = context.config

# Skip when embedded in the app (a connection was handed in): the app has
# already called logging.basicConfig(), and alembic.ini's [logger_*] sections
# would add a second handler on top of it, duplicating every line. Standalone
# CLI use has no other logging set up yet, so there this is what makes
# `alembic upgrade head` print anything at all.
if config.config_file_name is not None and "connection" not in config.attributes:
    fileConfig(config.config_file_name)

from app.database import Base  # noqa: E402
from app import models  # noqa: E402,F401  (registers mappers on Base.metadata)

target_metadata = Base.metadata


def get_url() -> str:
    from app.config import settings

    # Alembic runs synchronously; aiosqlite is an async-only driver, so a
    # standalone CLI invocation needs the plain sync one. The app's own
    # async engine (database.py) is untouched — it never imports this file.
    return settings.database_url.replace("+aiosqlite", "")


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Reuse a connection handed in by init_db() if there is one; otherwise
    # (plain CLI use) open our own, short-lived.
    connection = config.attributes.get("connection")
    if connection is not None:
        _do_run_migrations(connection)
        return

    connectable = engine_from_config(
        {"sqlalchemy.url": get_url()},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        _do_run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
