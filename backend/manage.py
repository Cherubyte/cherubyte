#!/usr/bin/env python3
"""Small admin CLI for the NetScan panel.

Run from the `backend/` directory with its venv:

    .venv/bin/python manage.py create-admin [username]
    .venv/bin/python manage.py init-db
    .venv/bin/python manage.py backup [path.tar.gz]
    .venv/bin/python manage.py restore <path.tar.gz>

`create-admin` reads the password from $NETSCAN_ADMIN_PASSWORD when set (so the
setup script can run unattended), otherwise it prompts. It also promotes an
existing account to admin and resets its password, so it doubles as a recovery
tool if you lock yourself out.
"""

from __future__ import annotations

import asyncio
import getpass
import os
import sys

from sqlalchemy import select

from app.database import SessionLocal, init_db
from app.models import Account, AccountRole
from app.services import auth

_MIN_PASSWORD = 8


async def _create_admin(username: str, password: str) -> str:
    await init_db()
    async with SessionLocal() as session:
        existing = (
            await session.execute(select(Account).where(Account.username == username))
        ).scalar_one_or_none()
        if existing is not None:
            existing.password_hash = auth.hash_password(password)
            existing.role = AccountRole.admin
            verb = "updated"
        else:
            session.add(
                Account(
                    username=username,
                    password_hash=auth.hash_password(password),
                    role=AccountRole.admin,
                )
            )
            verb = "created"
        await session.commit()
    return verb


def _prompt_password() -> str:
    env = os.environ.get("NETSCAN_ADMIN_PASSWORD")
    if env:
        if len(env) < _MIN_PASSWORD:
            sys.exit(f"NETSCAN_ADMIN_PASSWORD is shorter than {_MIN_PASSWORD} characters")
        return env
    while True:
        pw = getpass.getpass("Password: ")
        if len(pw) < _MIN_PASSWORD:
            print(f"  too short — need {_MIN_PASSWORD}+ characters")
            continue
        if pw != getpass.getpass("Password (again): "):
            print("  did not match")
            continue
        return pw


def _clean_username(raw: str) -> str:
    name = (raw or "").strip().lower()
    if not (2 <= len(name) <= 64) or not all(c.isalnum() or c in "._-" for c in name):
        sys.exit("Invalid username (2–64 chars, letters/digits/._- only)")
    return name


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return

    cmd = args[0]
    if cmd == "init-db":
        asyncio.run(init_db())
        print("Schema is up to date.")
        return

    if cmd == "backup":
        from pathlib import Path

        from app.services import backup

        dest = Path(args[1]) if len(args) > 1 else Path(backup.default_name())
        backup.create(dest)
        print(f"Backup written to {dest} ({dest.stat().st_size / 1024:.0f} KiB).")
        return

    if cmd == "restore":
        from pathlib import Path

        from app.services import backup

        if len(args) < 2:
            sys.exit("Usage: manage.py restore <path.tar.gz>")
        src = Path(args[1])
        if not src.is_file():
            sys.exit(f"No such file: {src}")
        try:
            summary = backup.restore(src)
        except backup.BackupError as exc:
            sys.exit(f"Refused: {exc}")
        print(
            f"Restored from {src.name} ({summary['uploads']} upload(s)). "
            "The previous data is kept alongside as *.pre-restore. "
            "Restart the panel."
        )
        return

    if cmd == "create-admin":
        username = _clean_username(
            args[1] if len(args) > 1 else os.environ.get("NETSCAN_ADMIN_USERNAME") or "admin"
        )
        password = _prompt_password()
        verb = asyncio.run(_create_admin(username, password))
        print(f"Admin account {username!r} {verb}.")
        return

    sys.exit(f"Unknown command {cmd!r}. Try --help.")


if __name__ == "__main__":
    main()
