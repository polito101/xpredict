"""Phase 4 markets: markets + outcomes + odds_snapshots.

Revision ID: 0003_phase4_markets
Revises: 0002_phase2_auth
Create Date: 2026-05-27

Creates three tables Phase 4 owns:
  - markets (source-agnostic market definition with CHECK constraints)
  - outcomes (binary YES/NO per market, enforced by trigger)
  - odds_snapshots (price history per outcome)

MKT-07: source + source_market_id + condition_id columns.
MKT-08: Binary-only enforcement via Postgres trigger (max 2 outcomes per market).
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003_phase4_markets"
down_revision: str | None = "0002_phase2_auth"
branch_labels: str | None = None
depends_on: str | None = None

TENANT_DEFAULT = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    # ------------------------------------------------------------------
    # markets
    # ------------------------------------------------------------------
    op.create_table(
        "markets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("resolution_criteria", sa.Text, nullable=False),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column(
            "source",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'HOUSE'"),
        ),
        sa.Column("source_market_id", sa.String(200), nullable=True),
        sa.Column("condition_id", sa.String(200), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'OPEN'"),
        ),
        sa.Column("deadline", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "bet_count",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("closed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            server_default=sa.text(f"'{TENANT_DEFAULT}'::uuid"),
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'OPEN', 'CLOSED', 'RESOLVED', 'CANCELLED')",
            name="ck_markets_status",
        ),
        sa.CheckConstraint(
            "source IN ('HOUSE', 'POLYMARKET')",
            name="ck_markets_source",
        ),
    )
    op.create_index("ix_markets_slug", "markets", ["slug"], unique=True)

    # ------------------------------------------------------------------
    # outcomes
    # ------------------------------------------------------------------
    op.create_table(
        "outcomes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "market_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("markets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(50), nullable=False),
        sa.Column("initial_odds", sa.Numeric(8, 6), nullable=False),
        sa.Column("current_odds", sa.Numeric(8, 6), nullable=False),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            server_default=sa.text(f"'{TENANT_DEFAULT}'::uuid"),
        ),
    )
    op.create_index("ix_outcomes_market_id", "outcomes", ["market_id"])

    # ------------------------------------------------------------------
    # odds_snapshots
    # ------------------------------------------------------------------
    op.create_table(
        "odds_snapshots",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "market_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("markets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "outcome_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("outcomes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("probability", sa.Numeric(8, 6), nullable=False),
        sa.Column(
            "snapshot_at",
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
    )
    op.create_index("ix_odds_snapshots_market_id", "odds_snapshots", ["market_id"])
    op.create_index("ix_odds_snapshots_outcome_id", "odds_snapshots", ["outcome_id"])

    # ------------------------------------------------------------------
    # MKT-08: binary-only trigger (max 2 outcomes per market)
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION check_binary_outcomes()
        RETURNS TRIGGER AS $$
        BEGIN
            IF (SELECT COUNT(*) FROM outcomes WHERE market_id = NEW.market_id) >= 2 THEN
                RAISE EXCEPTION 'Binary markets allow at most 2 outcomes (MKT-08)'
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_binary_outcomes_only
        BEFORE INSERT ON outcomes
        FOR EACH ROW
        EXECUTE FUNCTION check_binary_outcomes();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_binary_outcomes_only ON outcomes")
    op.execute("DROP FUNCTION IF EXISTS check_binary_outcomes()")
    op.drop_index("ix_odds_snapshots_outcome_id", table_name="odds_snapshots")
    op.drop_index("ix_odds_snapshots_market_id", table_name="odds_snapshots")
    op.drop_table("odds_snapshots")
    op.drop_index("ix_outcomes_market_id", table_name="outcomes")
    op.drop_table("outcomes")
    op.drop_index("ix_markets_slug", table_name="markets")
    op.drop_table("markets")
