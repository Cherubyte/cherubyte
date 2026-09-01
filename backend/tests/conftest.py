"""Test fixtures.

The app builds its engine from settings at import time, so the database URL has
to be redirected *before* anything from `app` is imported.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="cherubyte-tests-"))
os.environ["CHERUBYTE_DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP / 'test.db'}"
# The suite's baseline is a single-tenant panel, and it must be that whatever
# is in the working directory: a `.env` left by a hosted dev instance would
# otherwise put every test into multi-tenant mode, where the shared fixture
# below has no tenant and refuses. The tests that want the hosted mode set it
# themselves, per test.
os.environ["CHERUBYTE_MULTI_TENANT"] = "false"
os.environ["CHERUBYTE_TENANTS_DIR"] = str(_TMP / "tenants")
# pin these so tests never depend on the machine's real network
os.environ["CHERUBYTE_SUBNET"] = "192.168.1.0/24"
os.environ["CHERUBYTE_TELEGRAM_BOT_TOKEN"] = ""
os.environ["CHERUBYTE_TELEGRAM_CHAT_ID"] = ""
os.environ["CHERUBYTE_NTFY_TOPIC"] = ""

import pytest_asyncio  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.database import Base, SessionLocal, engine, init_db  # noqa: E402


@pytest_asyncio.fixture
async def session():
    """A clean database per test.

    `alembic_version` lives outside `Base.metadata`, so drop_all() leaves it
    standing — without dropping it too, init_db() would see a database it
    thinks is already at "baseline" even though drop_all just wiped every
    table, and skip re-stamping it.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
    await init_db()
    async with SessionLocal() as s:
        yield s
