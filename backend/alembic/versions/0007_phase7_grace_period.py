"""Phase 7: add markets.uma_resolved_at for Polymarket auto-resolution grace period.

Records the first time the Beat task observed umaResolutionStatus='resolved' for
a mirrored market. The Beat task uses this timestamp to enforce the configurable
grace window (POLYMARKET_GRACE_PERIOD_MINUTES) before triggering settlement via
SettlementService (STL-01).

Revision ID: 0007_phase7_grace_period
Revises: 0006_merge_phase5_phase6
Create Date: 2026-05-28
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_phase7_grace_period"
down_revision: Union[str, Sequence[str], None] = "0006_merge_phase5_phase6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "markets",
        sa.Column("uma_resolved_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("markets", "uma_resolved_at")
