"""Phase 5 bets: the bets table (integration migration, FK-less — see note below).

Revision ID: 0005_phase5_bets
Revises: 0004_phase3_wallet_ledger
Create Date: 2026-05-27

Creates the ``bets`` table Phase 5 owns. ``market_id`` / ``outcome_id`` are plain UUIDs with
NO database FK — matching ``app/bets/models.py`` exactly. A bet's market is validated at the APP
layer (``BetService.place_bet`` via ``MarketReadPort`` -> 404 on an unknown market), not by a DB
FK; this keeps the model<->migration contract consistent and the decoupled bet/settlement test
suite (which stubs market ids) green. A DB-level FK to ``markets`` / ``outcomes`` is an OPTIONAL
hardening item (Phase 11) — adding it would also require every bet/settlement test to seed real
markets first. Columns match ``app/bets/models.py`` verbatim:
  - money ``stake`` NUMERIC(18,4) + ``CHECK (stake > 0)``,
  - odds-at-placement NUMERIC(8,6) (a probability in (0,1], the locked price),
  - status Text walking PENDING -> SETTLED_WON/_LOST (CHECK enforced),
  - tenant_id ghost (PLT-01).

The new Phase 5 ledger vocabulary (transfer/account kinds) is migration-FREE — the
``accounts.kind`` / ``transfers.kind`` columns are Text, so settlement adds string values, not
schema. Only the bets table itself needs DDL.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005_phase5_bets"
down_revision: str | None = "0004_phase3_wallet_ledger"
branch_labels: str | None = None
depends_on: str | None = None

TENANT_DEFAULT = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.create_table(
        "bets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        # market_id / outcome_id are plain UUIDs (NO FK) — matching app/bets/models.py exactly.
        # A bet's market is validated at the APP layer (BetService.place_bet via MarketReadPort
        # rejects an unknown market with 404), not by a DB FK. This keeps the model<->migration
        # contract consistent and the decoupled bet/settlement suite (which stubs market ids)
        # green. A DB-level FK to markets/outcomes is an OPTIONAL hardening (Phase 11) — it would
        # also require every bet/settlement test to seed real markets first.
        sa.Column("market_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("outcome_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stake", sa.Numeric(18, 4), nullable=False),
        sa.Column("odds_at_placement", sa.Numeric(8, 6), nullable=False),
        sa.Column(
            "status",
            sa.Text,
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            server_default=sa.text(f"'{TENANT_DEFAULT}'::uuid"),
        ),
        sa.CheckConstraint("stake > 0", name="bets_stake_positive"),
        sa.CheckConstraint(
            "status IN ('PENDING','SETTLED_WON','SETTLED_LOST')",
            name="bets_status_check",
        ),
    )
    op.create_index("bets_user_idx", "bets", ["user_id"])
    op.create_index("bets_market_idx", "bets", ["market_id"])


def downgrade() -> None:
    op.drop_index("bets_market_idx", table_name="bets")
    op.drop_index("bets_user_idx", table_name="bets")
    op.drop_table("bets")
