"""Live-bets bridge (v1.3, LB-A): livebets_escrow singleton + livebets_bets mirror.

Revision ID: 0011_livebets_bridge
Revises: 0011_phase13_market_groups
Create Date: 2026-06-05

Additive, reversible migration for the live-bets ledger mirror. It changes NO
existing table and adds NO Postgres enum — the new ledger vocabulary (account
kind ``livebets_escrow``, the ``livebets_*`` transfer kinds) is migration-free
because ``accounts.kind`` / ``transfers.kind`` are ``Text``. Running
``alembic upgrade head`` creates the escrow singleton + the mirror table with zero
behavior change to existing tables; ``alembic downgrade -1`` removes both cleanly.

Two additions:
  - ``livebets_bets`` mirror table — matches ``app/integrations/livebets/models.py``
    verbatim: ``bet_id`` UUID PK (NO ``gen_random_uuid()`` default — it is the
    live-bets id, supplied by live-bets), ``user_id`` UUID not null (FK-less, like
    ``bets.user_id``), ``table_id`` / ``market_id`` UUID nullable, ``stake``
    NUMERIC(18,4), ``status`` Text default ``'PENDING'`` + CHECK against live-bets'
    REAL ``BetStatus`` enum (``PENDING|WON|LOST|REFUNDED|VOIDED`` — NO ``VOID``),
    ``created_at`` TIMESTAMP(tz) NOW(), ``settled_at`` nullable, ``tenant_id`` ghost.
  - ``livebets_escrow`` system singleton account — seeded with the SAME idempotent
    ``ON CONFLICT DO NOTHING`` pattern as the ``house_*`` seed in
    ``0004_phase3_wallet_ledger.py``, using the fixed UUID + literals from
    ``app/integrations/livebets/constants.py`` and ``app/wallet/constants.py`` so
    the service references it without a runtime lookup.

LOCKED DECISION — loss sink: losses sweep to ``HOUSE_REVENUE_ACCOUNT_ID`` (kind
``house_revenue``), NOT ``house_promo``. The design-contract §8 table shows losses
-> ``house_promo``, but the CONTEXT open item says "If a distinct house P&L account
exists, route losses there", and ``app/settlement/service.py``'s loser sweep is
``market_liability -> house_revenue``. The livebets loss path mirrors it exactly:
``livebets_escrow -> house_revenue`` (consumed by the service in Task 2).

The ``revision`` id is ``0011_livebets_bridge`` (20 chars) — well under the
``alembic_version.version_num`` ``varchar(32)`` limit that ``0010`` documents.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.integrations.livebets.constants import (
    KIND_LIVEBETS_ESCROW,
    LIVEBETS_ESCROW_ACCOUNT_ID,
)
from app.wallet.constants import OWNER_SYSTEM, PLAY_USD

# revision identifiers, used by Alembic.
revision: str = "0011_livebets_bridge"
down_revision: str | None = "0011_phase13_market_groups"
branch_labels: str | None = None
depends_on: str | None = None

# Pitfall 10: same literal as 0001/0002/0004/0005 — the v1 default tenant UUID.
TENANT_DEFAULT = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    # ----------------------------------------------------------------------
    # livebets_bets mirror table — matches app/integrations/livebets/models.py
    # verbatim. bet_id is the live-bets UUID (NO server default — supplied by
    # live-bets). FK-less user_id (matches bets.user_id, app-layer verified).
    # ----------------------------------------------------------------------
    op.create_table(
        "livebets_bets",
        sa.Column("bet_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("table_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("market_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("stake", sa.Numeric(18, 4), nullable=False),
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
        sa.Column("settled_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            server_default=sa.text(f"'{TENANT_DEFAULT}'::uuid"),
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','WON','LOST','REFUNDED','VOIDED')",
            name="livebets_bets_status_check",
        ),
    )
    op.create_index("livebets_bets_user_idx", "livebets_bets", ["user_id"])

    # ----------------------------------------------------------------------
    # Seed the livebets_escrow singleton (idempotent — ON CONFLICT DO NOTHING
    # on the unique owner/kind/currency tuple), exactly like the house_* seed in
    # 0004. owner_type=system, owner_id NULL, balance 0. Fixed UUID + literals
    # come from app/integrations/livebets/constants.py + app/wallet/constants.py.
    # ----------------------------------------------------------------------
    op.execute(
        f"""
        INSERT INTO accounts (id, owner_type, owner_id, kind, currency, balance) VALUES
          ('{LIVEBETS_ESCROW_ACCOUNT_ID}', '{OWNER_SYSTEM}', NULL,
           '{KIND_LIVEBETS_ESCROW}', '{PLAY_USD}', 0)
        ON CONFLICT (owner_type, owner_id, kind, currency) DO NOTHING;
        """
    )


def downgrade() -> None:
    """Remove the seeded escrow account by id, then the index + mirror table.

    A clean downgrade implies no live data was mirrored, so the escrow account is
    balance-0 and no entries reference it — the DELETE-by-id is safe.
    """
    op.execute(f"DELETE FROM accounts WHERE id = '{LIVEBETS_ESCROW_ACCOUNT_ID}';")
    op.drop_index("livebets_bets_user_idx", table_name="livebets_bets")
    op.drop_table("livebets_bets")
