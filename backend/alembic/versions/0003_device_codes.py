"""Device codes: enrolling an agent by approving it rather than pasting a token.

Idempotent, like the revision before it, because `init_db()` reaches here with
`create_all` having already built the current model schema on a fresh database.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_device_codes"
down_revision: str | Sequence[str] | None = "0002_blind_indexes"
branch_labels = None
depends_on = None


def _has_table(conn, name: str) -> bool:
    return bool(
        conn.execute(
            sa.text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:n"), {"n": name}
        ).first()
    )


def upgrade() -> None:
    conn = op.get_bind()
    if not _has_table(conn, "device_codes"):
        op.create_table(
            "device_codes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("code", sa.String(16), nullable=False),
            sa.Column("poll_hash", sa.String(64), nullable=False),
            sa.Column("name", sa.String(120), nullable=False, server_default=""),
            sa.Column("version", sa.String(40), nullable=True),
            sa.Column("source_ip", sa.String(45), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "approved_by",
                sa.Integer(),
                sa.ForeignKey("accounts.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("collected_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "agent_id",
                sa.Integer(),
                sa.ForeignKey("agents.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
    conn.execute(
        sa.text("CREATE UNIQUE INDEX IF NOT EXISTS ix_device_codes_code ON device_codes (code)")
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_device_codes_code"))
    if _has_table(conn, "device_codes"):
        op.drop_table("device_codes")
