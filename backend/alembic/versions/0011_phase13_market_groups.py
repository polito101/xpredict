"""Phase 13 (Plan 13-01): multi-outcome event-of-binaries schema seam.

Revision ID: 0011_phase13_market_groups
Revises: 0010_phase12_resolution_stakes
Create Date: 2026-06-05

Pure ADDITIVE schema gate for v1.2 multi-outcome events (EVT-01). A multi-outcome
event is modelled as N independent binary YES/NO markets grouped under one
``market_groups`` row — reusing the existing binary ``Market`` + ``Outcome`` +
``SettlementService`` unchanged. Existing standalone markets (``group_id IS NULL``)
stay byte-for-byte unchanged: the two new ``markets`` columns are nullable with no
backfill, and nothing in the binary read/bet/settle path is touched.

This migration, in one reversible unit:

* enables ``pg_trgm`` (FIRST — the GIN trigram indexes below depend on
  ``gin_trgm_ops`` existing);
* creates ``market_groups`` (UUID PK, title, source, source_event_id, category,
  slug, created_at/updated_at, ``tenant_id`` ghost column — CONVENTIONS §2). NO
  money column (would trip ``scripts/lint_money_columns.py``) and NO stored
  ``status``/``winning_outcome`` column (EVT-06 — event status is DERIVED in
  Phase 15, never stored);
* adds two nullable ``markets`` columns: ``group_id`` (FK → ``market_groups.id``
  ON DELETE **SET NULL**, never CASCADE — child markets carry bets/odds/ledger
  state, so deleting a group must ORPHAN them back to standalone, never delete
  financial rows) and ``group_item_title``;
* creates all six catalog/search indexes later phases (14 sync, 16 API, 17 UI)
  read: two GIN trigram (``market_groups.title``, ``markets.question``), the
  partial-unique ``(source, source_event_id) WHERE source_event_id IS NOT NULL``,
  the ``(category)`` indexes on both tables, ``markets (status, volume_24hr)``,
  and the composite ``odds_snapshots (outcome_id, snapshot_at)`` (ADDITIVE
  alongside the existing single-column ``ix_odds_snapshots_outcome_id`` from 0003,
  which is NOT dropped).

Chains off the single current head ``0010_phase12_resolution_stakes`` — that is
the in-table REVISION ID, NOT the filename stem
``0010_phase12_resolution_and_stake_limits`` (Alembic resolves by revision id; the
filename is decoupled). Do NOT branch (single-head invariant).

``downgrade()`` reverses EXACTLY what ``upgrade()`` created (indexes → FK → columns
→ slug index → table) but DELIBERATELY does NOT ``DROP EXTENSION pg_trgm``:
extensions are database-global and may be shared by future objects, and a bundled
idempotent extension is harmless to leave. Reversibility (SC#1) is satisfied by
restoring the pre-0011 schema OBJECTS; leaving ``pg_trgm`` is the safe choice
(RESEARCH A1 / Pitfall 3).

EVT-01: additive only — the binary model, CHECK constraints, the
``trg_binary_outcomes_only`` trigger, and all bet/odds/ledger paths are untouched.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision id is 26 chars — safely under the ``alembic_version.version_num``
# varchar(32) limit (Pitfall 1). down_revision is the REVISION ID of 0010, NOT its
# filename stem (Pitfall 2).
revision: str = "0011_phase13_market_groups"
down_revision: str | None = "0010_phase12_resolution_stakes"
branch_labels: str | None = None
depends_on: str | None = None


# Same literal as 0001/0003/0004/0009 — single source of truth for the v1 default
# tenant UUID across every table (CONVENTIONS §2).
TENANT_DEFAULT = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    # 1) pg_trgm FIRST — the GIN trigram indexes below require ``gin_trgm_ops`` to
    #    exist. Ordering is load-bearing.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # 2) market_groups table — UUID PK + timestamps + tenant_id ghost column.
    #    NO money column, NO status/winning_outcome column, NO seed row.
    op.create_table(
        "market_groups",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column(
            "source",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'HOUSE'"),
        ),
        sa.Column("source_event_id", sa.String(200), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("slug", sa.String(100), nullable=False),
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
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            server_default=sa.text(f"'{TENANT_DEFAULT}'::uuid"),
        ),
        sa.CheckConstraint(
            "source IN ('HOUSE', 'POLYMARKET')",
            name="ck_market_groups_source",
        ),
    )
    op.create_index(
        "ix_market_groups_slug", "market_groups", ["slug"], unique=True
    )

    # 3) nullable markets columns — additive, NO backfill.
    op.add_column(
        "markets",
        sa.Column("group_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "markets",
        sa.Column("group_item_title", sa.Text(), nullable=True),
    )
    # ON DELETE SET NULL — NEVER CASCADE. Child markets carry bets/odds/ledger
    # state; deleting a group must orphan them back to standalone (Pitfall 5).
    op.create_foreign_key(
        "fk_markets_group_id",
        "markets",
        "market_groups",
        ["group_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_markets_group_id", "markets", ["group_id"])

    # 4) GIN trigram indexes (pg_trgm — infix ILIKE substring/typo search).
    op.create_index(
        "ix_market_groups_title_trgm",
        "market_groups",
        ["title"],
        postgresql_using="gin",
        postgresql_ops={"title": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_markets_question_trgm",
        "markets",
        ["question"],
        postgresql_using="gin",
        postgresql_ops={"question": "gin_trgm_ops"},
    )

    # 5) partial-unique on (source, source_event_id) — mirrors 0004's markets
    #    upsert index; lets Phase 14 use ON CONFLICT for Gamma /events ingestion.
    op.create_index(
        "ix_market_groups_source_source_event_id",
        "market_groups",
        ["source", "source_event_id"],
        unique=True,
        postgresql_where=sa.text("source_event_id IS NOT NULL"),
    )

    # 6) B-tree catalog filter/sort indexes. The odds_snapshots composite is
    #    ADDITIVE alongside the existing single-column ix_odds_snapshots_outcome_id
    #    (0003) — do NOT drop the existing one.
    op.create_index("ix_market_groups_category", "market_groups", ["category"])
    op.create_index("ix_markets_category", "markets", ["category"])
    op.create_index(
        "ix_markets_status_volume_24hr", "markets", ["status", "volume_24hr"]
    )
    op.create_index(
        "ix_odds_snapshots_outcome_id_snapshot_at",
        "odds_snapshots",
        ["outcome_id", "snapshot_at"],
    )


def downgrade() -> None:
    # Exact reverse order: indexes → FK constraint → columns → slug index → table.
    # Deliberately do NOT drop pg_trgm (DB-global, may be shared; Pitfall 3 / A1).
    op.drop_index(
        "ix_odds_snapshots_outcome_id_snapshot_at", table_name="odds_snapshots"
    )
    op.drop_index("ix_markets_status_volume_24hr", table_name="markets")
    op.drop_index("ix_markets_category", table_name="markets")
    op.drop_index("ix_market_groups_category", table_name="market_groups")
    op.drop_index(
        "ix_market_groups_source_source_event_id", table_name="market_groups"
    )
    op.drop_index("ix_markets_question_trgm", table_name="markets")
    op.drop_index("ix_market_groups_title_trgm", table_name="market_groups")
    op.drop_index("ix_markets_group_id", table_name="markets")
    op.drop_constraint("fk_markets_group_id", "markets", type_="foreignkey")
    op.drop_column("markets", "group_item_title")
    op.drop_column("markets", "group_id")
    op.drop_index("ix_market_groups_slug", table_name="market_groups")
    op.drop_table("market_groups")
