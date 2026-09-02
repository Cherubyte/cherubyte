"""Back up and restore the panel's state — the SQLite database and the uploads.

Everything the panel holds lives in `backend/data/`: `cherubyte.db` and the
`uploads/` tree. A backup is a gzipped tar of exactly those two, plus a small
`meta.json`. Losing the database loses your whole history, and on a Raspberry Pi
the thing it lives on is an SD card — so this wants to be one button.

The database is copied with SQLite's own backup API, not a file copy, so the
snapshot is consistent even while the service is writing to it. A restore swaps
the files in place and then the process exits: rewriting the database under a
live connection is not safe, and every supported deployment (systemd
`Restart=always`, Docker `restart: unless-stopped`) brings it straight back.
"""

from __future__ import annotations

import io
import json
import logging
import shutil
import sqlite3
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from ..config import DATA_DIR, settings, upload_dir

logger = logging.getLogger("cherubyte.backup")

_DB_MEMBER = "cherubyte.db"
# Backups written before the NetScan → Cherubyte rename carry the database as
# `netscan.db`. Restore still accepts them.
_LEGACY_DB_MEMBER = "netscan.db"
_META_MEMBER = "meta.json"
_UPLOADS_PREFIX = "uploads/"


def _archived_db_member(members: set[str]) -> str:
    """The name the database is stored under in this archive."""
    if _DB_MEMBER in members:
        return _DB_MEMBER
    if _LEGACY_DB_MEMBER in members:
        return _LEGACY_DB_MEMBER
    raise BackupError(f"archive has no {_DB_MEMBER}")


def db_path() -> Path | None:
    """The on-disk SQLite file for whoever is in scope, or None.

    Hosted, `settings.database_url` names a database that does not exist —
    there is no default one — so the tenant currently in scope decides, and a
    caller with no tenant gets None rather than somebody else's file.
    """
    if settings.multi_tenant:
        from ..database import tenant_db_path
        from ..tenancy import current_tenant

        tenant = current_tenant.get()
        return tenant_db_path(tenant) if tenant else None

    url = settings.database_url
    for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
        if url.startswith(prefix):
            return Path(url[len(prefix):])
    return None


def _snapshot_db(dest: Path) -> None:
    """A consistent copy of the live database, via SQLite's backup API."""
    src = db_path()
    if src is None or not src.exists():
        raise FileNotFoundError("no SQLite database to back up")
    source = sqlite3.connect(str(src))
    try:
        target = sqlite3.connect(str(dest))
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


def create(out_path: Path) -> Path:
    """Write a gzipped tar backup to `out_path`. Returns it."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        db_copy = Path(tmp) / _DB_MEMBER
        _snapshot_db(db_copy)

        meta = {
            "app": "cherubyte",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        meta_bytes = json.dumps(meta, indent=2).encode()

        with tarfile.open(out_path, "w:gz") as tar:
            tar.add(db_copy, arcname=_DB_MEMBER)
            info = tarfile.TarInfo(_META_MEMBER)
            info.size = len(meta_bytes)
            tar.addfile(info, io.BytesIO(meta_bytes))
            uploads = upload_dir()
            if uploads.is_dir():
                for path in sorted(uploads.rglob("*")):
                    if path.is_file():
                        tar.add(
                            path,
                            arcname=f"{_UPLOADS_PREFIX}{path.relative_to(uploads)}",
                        )
    return out_path


def default_name() -> str:
    return f"cherubyte-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.tar.gz"


class BackupError(ValueError):
    """The archive is not a Cherubyte backup, or is damaged."""


def _safe_members(tar: tarfile.TarFile) -> list[tarfile.TarInfo]:
    """Reject anything that would escape the extraction directory.

    Python 3.12 has `filter="data"` for this; 3.11 (the CI floor) does not, so
    the check is explicit: regular files only, relative paths only, no `..`.
    """
    out: list[tarfile.TarInfo] = []
    for m in tar.getmembers():
        name = m.name
        if m.isdir():
            continue
        if not (m.isfile() or m.islnk()):
            raise BackupError(f"unexpected entry in archive: {name}")
        if name.startswith("/") or ".." in Path(name).parts:
            raise BackupError(f"unsafe path in archive: {name}")
        out.append(m)
    return out


def inspect(archive: Path) -> dict:
    """Validate an archive without applying it. Raises BackupError if it's bad."""
    if not tarfile.is_tarfile(archive):
        raise BackupError("not a .tar.gz archive")
    with tarfile.open(archive, "r:gz") as tar:
        members = {m.name for m in _safe_members(tar)}
        db_member = _archived_db_member(members)
        with tempfile.TemporaryDirectory() as tmp:
            tar.extract(tar.getmember(db_member), tmp)  # noqa: S202 — path checked above
            db_copy = Path(tmp) / db_member
            probe = sqlite3.connect(str(db_copy))
            try:
                result = probe.execute("PRAGMA integrity_check").fetchone()
            except sqlite3.DatabaseError as exc:
                raise BackupError(f"the archived database is not readable: {exc}") from None
            finally:
                probe.close()
            if not result or result[0] != "ok":
                raise BackupError("the database in the archive fails its integrity check")
        meta: dict = {}
        if _META_MEMBER in members:
            f = tar.extractfile(_META_MEMBER)
            if f is not None:
                try:
                    meta = json.loads(f.read().decode())
                except (ValueError, UnicodeDecodeError):
                    meta = {}
        upload_files = sum(1 for m in members if m.startswith(_UPLOADS_PREFIX))
    return {"meta": meta, "uploads": upload_files}


def restore(archive: Path) -> dict:
    """Apply a backup: swap in its database and uploads. The caller must then
    exit the process — see the module docstring.

    The current database and uploads are moved aside (`*.pre-restore`) rather
    than deleted, so a bad restore is recoverable by hand.
    """
    summary = inspect(archive)

    target_db = db_path()
    if target_db is None:
        raise BackupError("restore needs a file-backed SQLite database")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with tarfile.open(archive, "r:gz") as tar:
            members = _safe_members(tar)
            db_member = _archived_db_member({m.name for m in members})
            for m in members:
                tar.extract(m, tmp_path)  # noqa: S202 — members checked

        # database
        _rotate(target_db)
        target_db.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(tmp_path / db_member, target_db)
        for sidecar in ("-wal", "-shm"):
            stale = target_db.with_name(target_db.name + sidecar)
            stale.unlink(missing_ok=True)

        # uploads
        staged_uploads = tmp_path / "uploads"
        uploads = upload_dir()
        if uploads.exists():
            _rotate(uploads)
        uploads.mkdir(parents=True, exist_ok=True)
        if staged_uploads.is_dir():
            for item in staged_uploads.rglob("*"):
                if item.is_file():
                    dest = uploads / item.relative_to(staged_uploads)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, dest)

    logger.warning("Restore applied from %s — the process will now exit to reload it", archive.name)
    return summary


def _rotate(path: Path) -> None:
    backup = path.with_name(path.name + ".pre-restore")
    if backup.exists():
        if backup.is_dir():
            shutil.rmtree(backup)
        else:
            backup.unlink()
    path.rename(backup)


__all__ = ["create", "restore", "inspect", "default_name", "BackupError", "db_path"]
