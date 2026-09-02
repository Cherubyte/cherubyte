"""Blind index columns for the encrypted addresses and user names.

Only the new columns are added. The encrypted columns themselves are not
altered: SQLite does not enforce VARCHAR lengths, so widening
`mac_addresses.address` from 17 to hold ciphertext changes the declared type
and nothing else, and a batch-mode table rebuild to achieve nothing is a
rebuild that can fail.

**Idempotent, because `init_db()` gets here with the work possibly done.**
That path runs `create_all` first, which builds the current model schema —
these columns and their indexes included — and only then stamps and upgrades.
So on a fresh database this migration finds everything already in place and
must be a no-op, while on a database created before this revision it does the
work. The same rule the additive patches in `database.py` follow, for the same
reason.

**The backfill assumes the database is not yet encrypted**, which is the only
case that reaches it. Hosted tenants are provisioned empty and encrypt from
their first write; a self-hosted database has no key and never will, and with
no key `blind_index()` is a lowercased copy, so equality lookups keep working
exactly as they did against the old plain column.

Importing an existing database *into* the hosted service is the case this does
not cover: those rows would carry plaintext indexes that no encrypted lookup
can match. That needs a re-encrypting pass, which is also what key rotation
needs, and is deliberately not this migration's job.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.crypto import blind_index

revision: str = "0002_blind_indexes"
down_revision: str | Sequence[str] | None = "baseline"
branch_labels = None
depends_on = None

# (table, source column, blind index column, unique)
_COLUMNS: tuple[tuple[str, str, str, bool], ...] = (
    ("mac_addresses", "address", "address_bi", False),
    ("ip_addresses", "address", "address_bi", False),
    # Unique, because this is where `users.name`'s uniqueness went: two rows
    # holding the same name encrypt differently and the old column constraint
    # would let both through.
    ("users", "name", "name_bi", True),
)


def _has_column(conn, table: str, column: str) -> bool:
    rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return column in {r[1] for r in rows}


def _backfill(conn, table: str, source: str, target: str) -> None:
    rows = conn.execute(
        sa.text(f"SELECT id, {source} FROM {table} WHERE {target} IS NULL")
    ).fetchall()
    for row_id, value in rows:
        if value is None:
            continue
        conn.execute(
            sa.text(f"UPDATE {table} SET {target} = :bi WHERE id = :id"),
            {"bi": blind_index(value), "id": row_id},
        )


def upgrade() -> None:
    conn = op.get_bind()
    for table, source, target, unique in _COLUMNS:
        if not _has_column(conn, table, target):
            op.add_column(table, sa.Column(target, sa.String(64), nullable=True))
        _backfill(conn, table, source, target)
        conn.execute(
            sa.text(
                f"CREATE {'UNIQUE ' if unique else ''}INDEX IF NOT EXISTS "
                f"ix_{table}_{target} ON {table} ({target})"
            )
        )


def downgrade() -> None:
    conn = op.get_bind()
    for table, _source, target, _unique in reversed(_COLUMNS):
        conn.execute(sa.text(f"DROP INDEX IF EXISTS ix_{table}_{target}"))
        if _has_column(conn, table, target):
            op.drop_column(table, target)
