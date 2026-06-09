"""Early close — bets gain a CLOSED status + closed_at / exit_odds.

Additive + reversible. Widens the ``bets_status_check`` CHECK to allow a terminal ``CLOSED``
status (set when a player cashes out a position before resolution) and adds two nullable
columns: ``closed_at`` (when the close happened) and ``exit_odds`` (the outcome's price
captured at close, in (0,1]; the realized-on-close P&L derives from stake, odds_at_placement,
exit_odds). No backfill — existing bets keep both columns NULL.

Revision ID: 0012_early_close
Revises: 0011_livebets_bridge
Create Date: 2026-06-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012_early_close"
down_revision: str | Sequence[str] | None = "0011_livebets_bridge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUS_CHECK = "bets_status_check"
_OLD_STATUS = "status IN ('PENDING','SETTLED_WON','SETTLED_LOST')"
_NEW_STATUS = "status IN ('PENDING','SETTLED_WON','SETTLED_LOST','CLOSED')"


def upgrade() -> None:
    op.add_column("bets", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("bets", sa.Column("exit_odds", sa.Numeric(8, 6), nullable=True))
    op.drop_constraint(_STATUS_CHECK, "bets", type_="check")
    op.create_check_constraint(_STATUS_CHECK, "bets", _NEW_STATUS)


def downgrade() -> None:
    op.drop_constraint(_STATUS_CHECK, "bets", type_="check")
    op.create_check_constraint(_STATUS_CHECK, "bets", _OLD_STATUS)
    op.drop_column("bets", "exit_odds")
    op.drop_column("bets", "closed_at")
