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
# pin these so tests never depend on the machine's real network
os.environ["CHERUBYTE_SUBNET"] = "192.168.1.0/24"
os.environ["CHERUBYTE_TELEGRAM_BOT_TOKEN"] = ""
os.environ["CHERUBYTE_TELEGRAM_CHAT_ID"] = ""
os.environ["CHERUBYTE_NTFY_TOPIC"] = ""

import pytest_asyncio  # noqa: E402

from app.database import Base, SessionLocal, engine, init_db  # noqa: E402


@pytest_asyncio.fixture
async def session():
    """A clean database per test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await init_db()
    async with SessionLocal() as s:
        yield s
