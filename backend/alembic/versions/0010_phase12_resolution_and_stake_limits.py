"""Phase 12: persist the resolution winner (STL-06) + per-market stake limits (BET-06).

Additive, reversible migration adding FIVE nullable columns to ``markets``:

  - ``winning_outcome_id`` (UUID, nullable) — the outcome the market resolved on. Written
    inside the settlement ACID transaction by ``HouseMarketResolveAdapter.mark_resolved``
    (previously the winner lived ONLY in the admin-gated audit log, so the player saw
    "Market not found" / no winner — the STL-06 root cause).
  - ``resolution_source`` (String(40), nullable) — a stable token ("HOUSE" /
    "POLYMARKET_UMA") projecting how the market was resolved (derived from the resolving
    actor). A denormalized, publicly-readable copy; the audit row stays the system of record.
  - ``resolution_justification`` (Text, nullable) — the public trust signal shown on the
    resolved-market panel.
  - ``min_stake`` / ``max_stake`` (Numeric(18, 4), nullable) — per-market BET-06 limits.
    NULL = fall back to the global ``BET_MIN_STAKE`` / ``BET_MAX_STAKE`` config defaults
    (the global constants are NOT removed). Per-MARKET storage (not TenantConfig, which is
    a single-row global table structurally unfit for per-market values) per RESEARCH A1.

Purely additive: every column is nullable, no backfill (pre-Phase-12 resolved markets keep
their audit-log-only winner — a follow-up backfill can read ``audit_log.payload`` if needed).

Revision ID: 0010_phase12_resolution_and_stake_limits
Revises: 0009_phase10_tenant_config
Create Date: 2026-06-03
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_phase12_resolution_and_stake_limits"
down_revision: Union[str, Sequence[str], None] = "0009_phase10_tenant_config"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "markets",
        sa.Column("winning_outcome_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "markets",
        sa.Column("resolution_source", sa.String(40), nullable=True),
    )
    op.add_column(
        "markets",
        sa.Column("resolution_justification", sa.Text(), nullable=True),
    )
    op.add_column(
        "markets",
        sa.Column("min_stake", sa.Numeric(18, 4), nullable=True),
    )
    op.add_column(
        "markets",
        sa.Column("max_stake", sa.Numeric(18, 4), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("markets", "max_stake")
    op.drop_column("markets", "min_stake")
    op.drop_column("markets", "resolution_justification")
    op.drop_column("markets", "resolution_source")
    op.drop_column("markets", "winning_outcome_id")
