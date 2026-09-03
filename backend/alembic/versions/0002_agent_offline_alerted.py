"""agents.offline_alerted

Revision ID: 0002_agent_offline_alerted
Revises: baseline
Create Date: 2026-09-03

Tracks whether the panel has already sent an "agent went silent" alert for a
given agent, so an outage produces one notice rather than one per health check.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_agent_offline_alerted"
down_revision: Union[str, Sequence[str], None] = "baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(bind, table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, "agents", "offline_alerted"):
        op.add_column(
            "agents",
            sa.Column(
                "offline_alerted",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )


def downgrade() -> None:
    op.drop_column("agents", "offline_alerted")
