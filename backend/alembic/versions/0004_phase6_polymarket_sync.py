"""Phase 6 polymarket sync: volume columns + partial unique index.

Revision ID: 0004_phase6_polymarket_sync
Revises: 0003_phase4_markets
Create Date: 2026-05-28

Adds two volume columns to the markets table for Polymarket data sync
and a partial unique index on (source, source_market_id) for upsert
idempotency.

MKT-05: volume + volume_24hr columns for catalog replication.
MKT-06: partial unique index for ON CONFLICT upsert.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0004_phase6_polymarket_sync"
down_revision: str | None = "0003_phase4_markets"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Add volume columns to markets
    # ------------------------------------------------------------------
    op.add_column(
        "markets",
        sa.Column(
            "volume",
            sa.Numeric(18, 4),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "markets",
        sa.Column(
            "volume_24hr",
            sa.Numeric(18, 4),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    # ------------------------------------------------------------------
    # Polymarket slug — stores the Gamma API slug for source_url construction.
    # Numeric source_market_id is not a valid Polymarket URL path segment.
    # ------------------------------------------------------------------
    op.add_column(
        "markets",
        sa.Column(
            "polymarket_slug",
            sa.String(300),
            nullable=True,
        ),
    )

    # ------------------------------------------------------------------
    # Partial unique index for upsert on (source, source_market_id)
    # Only applies when source_market_id IS NOT NULL (house markets
    # don't have one).
    # ------------------------------------------------------------------
    op.create_index(
        "ix_markets_source_source_market_id",
        "markets",
        ["source", "source_market_id"],
        unique=True,
        postgresql_where=sa.text("source_market_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_markets_source_source_market_id",
        table_name="markets",
    )
    op.drop_column("markets", "polymarket_slug")
    op.drop_column("markets", "volume_24hr")
    op.drop_column("markets", "volume")
