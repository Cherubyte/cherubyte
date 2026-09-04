"""Schema setup: create_all + the frozen additive patches bring any database to
the "baseline" shape, then Alembic takes over — stamping a database it has
never touched (rather than re-running DDL it already has), then upgrading.
"""

from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import text

from app.config import BASE_DIR
from app.database import Base, engine, init_db


def _db_path() -> str:
    return engine.url.database


def _head() -> list[str]:
    """The revision Alembic considers current, read rather than hardcoded.

    These tests are about *stamping and upgrading*, not about which migration
    happens to be last, so naming one here would break them every time a
    migration is added — which is exactly what happened. `get_heads()` is
    plural on purpose: two migrations that both descend from the same parent
    leave Alembic with two heads and no error until runtime, so a merge that
    forgets to re-chain one fails here instead.
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    return list(ScriptDirectory.from_config(Config(str(BASE_DIR / "alembic.ini"))).get_heads())


async def _reset_empty() -> None:
    """Drop everything, including alembic_version, leaving a blank file."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.execute(text("DROP TABLE IF EXISTS alembic_version"))


@pytest.fixture(autouse=True)
async def _clean():
    await _reset_empty()
    yield
    await _reset_empty()


def _alembic_version() -> list[str]:
    con = sqlite3.connect(_db_path())
    try:
        rows = con.execute("SELECT version_num FROM alembic_version").fetchall()
    finally:
        con.close()
    return [r[0] for r in rows]


def _columns(table: str) -> set[str]:
    con = sqlite3.connect(_db_path())
    try:
        return {row[1] for row in con.execute(f"PRAGMA table_info({table})")}
    finally:
        con.close()


async def test_a_brand_new_database_is_stamped_then_brought_to_head():
    await init_db()
    assert _alembic_version() == _head()
    assert "counts_for_presence" in _columns("devices")


async def test_running_init_db_twice_is_a_harmless_no_op():
    await init_db()
    await init_db()
    assert _alembic_version() == _head()

async def test_a_pre_alembic_database_is_patched_then_stamped_without_data_loss():
    """A database create_all built (or an old release built by hand) with no
    alembic_version table at all — the exact shape every real install that
    predates this migration system is in."""
    con = sqlite3.connect(_db_path())
    con.executescript(
        """
        CREATE TABLE devices (
            id INTEGER PRIMARY KEY,
            hostname VARCHAR(255),
            device_type VARCHAR(32) NOT NULL DEFAULT 'unknown',
            approval_status VARCHAR(16) NOT NULL DEFAULT 'pending',
            is_online BOOLEAN NOT NULL DEFAULT 0,
            first_seen DATETIME NOT NULL,
            last_seen DATETIME NOT NULL,
            name VARCHAR(255)
        );
        INSERT INTO devices (id, hostname, first_seen, last_seen, name)
        VALUES (1, 'old-phone', '2020-01-01', '2020-01-01', 'Old Phone');
        """
    )
    con.commit()
    con.close()

    await init_db()

    assert _alembic_version() == _head()
    cols = _columns("devices")
    for missing in ("counts_for_presence", "model", "os_guess", "notify_policy", "tags"):
        assert missing in cols, f"{missing} was not patched in"
    # a real Alembic migration beyond baseline also applied
    assert "offline_alerted" in _columns("agents")

    con = sqlite3.connect(_db_path())
    try:
        row = con.execute("SELECT name FROM devices WHERE id = 1").fetchone()
    finally:
        con.close()
    assert row == ("Old Phone",), "pre-existing rows must survive the upgrade"


async def test_the_composite_history_index_is_present_either_way():
    await init_db()
    con = sqlite3.connect(_db_path())
    try:
        names = {
            r[0]
            for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='connection_history'"
            )
        }
    finally:
        con.close()
    assert "ix_conn_history_device_ts" in names
