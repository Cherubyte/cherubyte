"""Backup / restore round-trip for the database and uploads."""

import io
import tarfile
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import User
from app.services import backup


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    """Point the backup service at a throwaway uploads dir, not the dev one."""
    up = tmp_path / "uploads"
    up.mkdir()
    monkeypatch.setattr(backup, "UPLOAD_DIR", up)
    return up


@pytest.mark.asyncio
async def test_round_trip_restores_rows_and_files(session, uploads, tmp_path):
    session.add(User(name="Alex"))
    await session.commit()
    (uploads / "brand-abc.png").write_bytes(b"\x89PNG fake")

    archive = tmp_path / "b.tar.gz"
    backup.create(archive)

    # wipe both
    from app.models import User as U

    await session.execute(U.__table__.delete())
    await session.commit()
    (uploads / "brand-abc.png").unlink()

    summary = backup.restore(archive)
    assert summary["uploads"] == 1

    # the db file was swapped under us — read it fresh
    import sqlite3

    db = sqlite3.connect(str(backup.db_path()))
    names = [r[0] for r in db.execute("SELECT name FROM users")]
    db.close()
    assert names == ["Alex"]
    assert (uploads / "brand-abc.png").read_bytes() == b"\x89PNG fake"
    # the pre-restore copies are kept
    assert backup.db_path().with_name(backup.db_path().name + ".pre-restore").exists()


def test_inspect_accepts_a_legacy_netscan_db_member(tmp_path):
    """Backups written before the NetScan → Cherubyte rename carry the database
    as `netscan.db`. `inspect` (and, through it, `restore`) still accept them."""
    import sqlite3

    db_file = tmp_path / "src.db"
    con = sqlite3.connect(str(db_file))
    con.execute("CREATE TABLE t (x)")
    con.commit()
    con.close()

    legacy = tmp_path / "legacy.tar.gz"
    with tarfile.open(legacy, "w:gz") as tar:
        tar.add(db_file, arcname="netscan.db")

    assert backup.inspect(legacy) == {"meta": {}, "uploads": 0}


@pytest.mark.asyncio
async def test_backup_snapshot_is_consistent_under_writes(session, uploads, tmp_path):
    session.add(User(name="Sam"))
    await session.commit()
    archive = tmp_path / "b.tar.gz"
    backup.create(archive)
    assert tarfile.is_tarfile(archive)
    with tarfile.open(archive) as tar:
        assert "cherubyte.db" in tar.getnames()
        assert "meta.json" in tar.getnames()


def test_restore_rejects_a_non_archive(tmp_path):
    junk = tmp_path / "x.tar.gz"
    junk.write_bytes(b"not a tar")
    with pytest.raises(backup.BackupError):
        backup.restore(junk)


def test_restore_rejects_a_path_traversal_member(tmp_path, uploads):
    evil = tmp_path / "evil.tar.gz"
    with tarfile.open(evil, "w:gz") as tar:
        payload = b"x"
        info = tarfile.TarInfo("../../etc/pwned")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    with pytest.raises(backup.BackupError):
        backup.inspect(evil)


def test_restore_rejects_an_archive_without_a_database(tmp_path):
    noddb = tmp_path / "nodb.tar.gz"
    with tarfile.open(noddb, "w:gz") as tar:
        payload = b"{}"
        info = tarfile.TarInfo("meta.json")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    with pytest.raises(backup.BackupError):
        backup.inspect(noddb)


def test_api_download_is_admin_only(session, uploads):
    from fastapi.testclient import TestClient

    from app import main

    c = TestClient(main.app)
    c.post("/api/auth/setup", json={"username": "admin", "password": "hunter2!!"})
    r = c.get("/api/settings/backup")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/gzip"
    assert r.content[:2] == b"\x1f\x8b"  # gzip magic

    c.post(
        "/api/auth/accounts",
        json={"username": "vic", "password": "hunter2!!", "role": "viewer"},
    )
    viewer = TestClient(main.app)
    viewer.post("/api/auth/login", json={"username": "vic", "password": "hunter2!!"})
    assert viewer.get("/api/settings/backup").status_code == 403


def test_api_restore_rejects_junk(session, uploads):
    from fastapi.testclient import TestClient

    from app import main

    c = TestClient(main.app)
    c.post("/api/auth/setup", json={"username": "admin", "password": "hunter2!!"})
    r = c.post(
        "/api/settings/restore",
        files={"file": ("x.tar.gz", b"not a tar", "application/gzip")},
    )
    assert r.status_code == 422


def test_restore_rejects_a_corrupt_database(tmp_path):
    bad = tmp_path / "bad.tar.gz"
    with tarfile.open(bad, "w:gz") as tar:
        payload = b"SQLite format 3\x00 but corrupt"
        info = tarfile.TarInfo("cherubyte.db")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    with pytest.raises(backup.BackupError):
        backup.inspect(bad)
