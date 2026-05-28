"""merge phase5 bets + phase6 polymarket heads

Revision ID: 0006_merge_phase5_phase6
Revises: 0005_phase5_bets, 0004_phase6_polymarket_sync
Create Date: 2026-05-28

Phases 5 (bets/settlement) and 6 (polymarket sync) branched independently off
0003_phase4_markets and were integrated via separate PRs, leaving two alembic
heads. They touch disjoint tables (bets vs markets columns), so this is a pure
graph-merge revision with no schema operations.
"""

from __future__ import annotations

from typing import Sequence, Union

revision: str = "0006_merge_phase5_phase6"
down_revision: Union[str, tuple[str, ...], None] = (
    "0005_phase5_bets",
    "0004_phase6_polymarket_sync",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
