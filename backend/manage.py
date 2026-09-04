#!/usr/bin/env python3
"""Small admin CLI for the Cherubyte panel.

Run from the `backend/` directory with its venv:

    .venv/bin/python manage.py create-admin [username]
    .venv/bin/python manage.py init-db
    .venv/bin/python manage.py backup [path.tar.gz]
    .venv/bin/python manage.py restore <path.tar.gz>
    .venv/bin/python manage.py reencrypt <tenant-id> [--from-plaintext|--to-plaintext]
    .venv/bin/python manage.py create-agent-token [label]

`create-admin` reads the password from $CHERUBYTE_ADMIN_PASSWORD when set (so the
setup script can run unattended), otherwise it prompts. It also promotes an
existing account to admin and resets its password, so it doubles as a recovery
tool if you lock yourself out.

`reencrypt` is hosted-only and rewrites one tenant's data under a different key.
`--from-plaintext` turns encryption on for a database that predates it;
`--to-plaintext` decrypts one, for handing somebody their data back on the way
out; neither rotates the key in place. The tenant must not be serving traffic
while it runs.

`create-agent-token` mints a fresh agent enrolment token — the same one-time-
use, 24h-lived token `Settings ▸ Agents ▸ New token` issues over HTTP — without
needing a browser session first. Same trust level as the rest of this CLI
(direct database access), so a whole install can be scripted end to end:
create the admin, mint a token, feed it to the agent's own installer, all from
a terminal.
"""

from __future__ import annotations

import asyncio
import getpass
import os
import sys

from sqlalchemy import select

from app.database import SessionLocal, init_db
from app.models import Account, AccountRole
from app.services import agents as agent_service
from app.services import auth

_MIN_PASSWORD = 8


async def _create_agent_token(label: str | None) -> str:
    await init_db()
    async with SessionLocal() as session:
        token = await agent_service.issue_token(session, label)
        await session.commit()
    return token


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
    env = os.environ.get("CHERUBYTE_ADMIN_PASSWORD")
    if env:
        if len(env) < _MIN_PASSWORD:
            sys.exit(f"CHERUBYTE_ADMIN_PASSWORD is shorter than {_MIN_PASSWORD} characters")
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

    if cmd == "reencrypt":
        # Turning encryption on for a tenant that predates it, and rotating a
        # key later. Both are the same pass: read under one key, write under
        # the next. The tenant must not be serving traffic while it runs.
        from app.keyring import key_for
        from app.services.reencrypt import reencrypt, reencrypt_uploads

        if len(args) < 2:
            sys.exit("Usage: manage.py reencrypt <tenant-id> [--from-plaintext|--to-plaintext]")
        tenant = args[1]
        flags = set(args[2:])

        async def _run() -> tuple[dict[str, int], int]:
            # --from-plaintext: the rows are readable now and should not be.
            # --to-plaintext: the reverse, for handing a tenant their data
            # back on the way out. Neither given means a rotation, which needs
            # the old key and is not something the service can guess.
            fetched = await key_for(tenant)
            old = None if "--from-plaintext" in flags else fetched
            new = None if "--to-plaintext" in flags else fetched
            if old is new and "--from-plaintext" not in flags:
                sys.exit(
                    "Nothing to do: pass --from-plaintext to encrypt a database that is "
                    "currently readable, or --to-plaintext to decrypt one."
                )
            rows = await reencrypt(tenant, old_key=old, new_key=new)
            files = reencrypt_uploads(tenant, old_key=old, new_key=new)
            return rows, files

        rewritten, files = asyncio.run(_run())
        total = sum(rewritten.values())
        for where, count in sorted(rewritten.items()):
            print(f"  {where}: {count}")
        print(f"Rewrote {total} value(s) and {files} file(s) for {tenant}.")
        return

    if cmd == "create-agent-token":
        label = args[1] if len(args) > 1 else None
        token = asyncio.run(_create_agent_token(label))
        print(token)
        return

    if cmd == "create-admin":
        username = _clean_username(
            args[1] if len(args) > 1 else os.environ.get("CHERUBYTE_ADMIN_USERNAME") or "admin"
        )
        password = _prompt_password()
        verb = asyncio.run(_create_admin(username, password))
        print(f"Admin account {username!r} {verb}.")
        return

    sys.exit(f"Unknown command {cmd!r}. Try --help.")


if __name__ == "__main__":
    main()
