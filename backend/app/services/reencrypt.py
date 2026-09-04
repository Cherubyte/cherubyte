"""Rewriting a tenant's database under a key.

Two jobs, one mechanism:

* **Turning encryption on** for a database that already holds plain text —
  a beta tenant from before this existed, or an import of somebody's
  self-hosted panel.
* **Key rotation.** Read under the old key, write under the new one.

Without this the two states cannot be mixed, and the reason is the blind
indexes rather than the ciphertext. A plaintext row's index is a lowercased
copy of the address; an encrypted row's is an HMAC. Once a key is loaded every
lookup computes the HMAC, so the old rows stop matching — which does not look
like an error. It looks like a device that is rediscovered as new on every
scan, and a person whose name can suddenly be taken twice.

**Read with one key, write with another, in one pass per column.** Raw SQL
throughout, deliberately: the ORM's encrypted types read the key from a
context variable at bind time, and this is the one operation that needs two
different keys in scope at once. Going around them is clearer than trying to
make them do it.

Idempotent. A value already encrypted under the target key is decrypted and
re-encrypted, which changes the nonce and nothing else, so an interrupted run
is safe to start again. Not concurrent-safe: the tenant must not be serving
traffic, which for a rotation means suspending them first.
"""

from __future__ import annotations

import logging

from sqlalchemy import text

from .. import crypto, database
from ..crypto import _Encrypted
from ..database import Base
from ..keyring import using

logger = logging.getLogger("cherubyte.reencrypt")

# (table, value column, blind index column). Kept next to the models so a new
# indexed column is added in one place; the Alembic revision keeps its own
# frozen copy, because a migration has to describe the schema as it was.
BLIND_INDEXES: tuple[tuple[str, str, str], ...] = (
    ("mac_addresses", "address", "address_bi"),
    ("ip_addresses", "address", "address_bi"),
    ("users", "name", "name_bi"),
)


def encrypted_columns() -> list[tuple[str, str, str]]:
    """Every (table, column, aad) the models declare as encrypted.

    Read off the metadata rather than listed by hand: a column added to a
    model and forgotten here would be quietly left in plain text, and nothing
    would ever say so.
    """
    found = []
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, _Encrypted):
                found.append((table.name, column.name, column.type.aad))
    return sorted(found)


def _index_column(table: str, column: str) -> str | None:
    for t, source, target in BLIND_INDEXES:
        if t == table and source == column:
            return target
    return None


async def reencrypt(
    tenant_id: str, *, old_key: bytes | None, new_key: bytes | None
) -> dict[str, int]:
    """Rewrite every encrypted column of one tenant. Returns rows touched.

    `old_key` is the key the data is currently under — None for plain text.
    `new_key` is what it should be under — None to decrypt everything, which
    is what exporting a tenant to self-hosting needs.
    """
    counts: dict[str, int] = {}
    engine, _ = await database._tenants.get(tenant_id)

    async with engine.begin() as conn:
        for table, column, aad in encrypted_columns():
            index_column = _index_column(table, column)
            rows = (await conn.execute(text(f"SELECT id, {column} FROM {table}"))).fetchall()

            touched = 0
            for row_id, stored in rows:
                if stored is None:
                    continue
                with using(old_key):
                    plain = crypto.decrypt(stored, aad)
                with using(new_key):
                    rewritten = crypto.encrypt(plain, aad)
                    index = crypto.blind_index(plain) if index_column else None

                sets = f"{column} = :value"
                params: dict[str, object] = {"value": rewritten, "id": row_id}
                if index_column:
                    sets += f", {index_column} = :index"
                    params["index"] = index
                await conn.execute(text(f"UPDATE {table} SET {sets} WHERE id = :id"), params)
                touched += 1

            if touched:
                counts[f"{table}.{column}"] = touched
                logger.info("Rewrote %d rows of %s.%s", touched, table, column)

    return counts


def reencrypt_uploads(tenant_id: str, *, old_key: bytes | None, new_key: bytes | None) -> int:
    """The same for the photographs on disk. Returns files rewritten.

    Written to a temporary name and moved into place, so a run interrupted
    part-way leaves whole files rather than half-encrypted ones.
    """
    from ..api._uploads import UPLOAD_AAD
    from ..config import upload_dir
    from ..tenancy import current_tenant

    token = current_tenant.set(tenant_id)
    try:
        directory = upload_dir()
        if not directory.is_dir():
            return 0
        done = 0
        for path in sorted(directory.rglob("*")):
            if not path.is_file():
                continue
            blob = path.read_bytes()
            with using(old_key):
                plain = crypto.decrypt_bytes(blob, UPLOAD_AAD)
            with using(new_key):
                rewritten = crypto.encrypt_bytes(plain, UPLOAD_AAD)
            staging = path.with_name(path.name + ".rewriting")
            staging.write_bytes(rewritten)
            staging.replace(path)
            done += 1
        logger.info("Rewrote %d uploaded file(s)", done)
        return done
    finally:
        current_tenant.reset(token)
