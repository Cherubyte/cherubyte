"""Join the two lineages that both branched off `baseline`.

`0002_agent_offline_alerted` shipped in v0.21.0; `0002_blind_indexes` and
`0003_device_codes` came from the hosted-tenancy branch. Both named `baseline`
as their parent, so Alembic had two heads and refused to pick one.

A merge revision rather than a renumber, because renumbering the released one
strands every panel that already installed v0.21.0: its `alembic_version` row
still says `0002_agent_offline_alerted`, and an id that no longer exists is
`Can't locate revision identified by ...` on the next start, not a silent
no-op. Both ids stay exactly as they were applied; this revision only records
that the two lines rejoin here. It has no DDL of its own.
"""

from typing import Sequence, Union

revision: str = "0004_merge_tenancy_and_agent_health"
down_revision: Union[str, Sequence[str], None] = (
    "0003_device_codes",
    "0002_agent_offline_alerted",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
