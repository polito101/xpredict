"""Phase 3 wallet/ledger: accounts + transfers + entries (double-entry).

Revision ID: 0003_phase3_wallet_ledger
Revises: 0002_phase2_auth
Create Date: 2026-05-27

Creates the three tables Phase 3 owns, locked to STACK §3.2's UUID model
(ARCHITECTURE.md BIGINT is SUPERSEDED) and matching the ORM declarations in
``app/wallet/models.py`` verbatim. Drift between this file and the models breaks
the contract checked by ``tests/wallet/test_models.py`` +
``tests/wallet/test_migration_0003.py``.

DB-level invariants established here:
  - ``CHECK (balance >= 0)`` on accounts (WAL-08) — defense-in-depth.
  - ``transfers`` / ``entries`` are append-only (WAL-06): a BEFORE UPDATE OR
    DELETE deny-trigger + ``REVOKE UPDATE, DELETE`` — ported verbatim from the
    Phase 1 ``audit_log`` pattern (0001), generalized to a shared
    ``raise_ledger_immutable()`` function for both tables. ``accounts`` is NOT
    immutable — its balance is a mutable denormalized cache.
  - ``transfers.idempotency_key`` UNIQUE (WAL — idempotent recharge, 03-04).

Seeds the two system-account singletons (``house_promo`` funded, ``house_revenue``
balance 0) with the fixed UUIDs from ``app/wallet/constants.py`` so the recharge
service (03-04) and settlement (Phase 5) reference them without a lookup. The
seed is idempotent (ON CONFLICT DO NOTHING on the unique owner/kind/currency
tuple) so re-running against an existing DB does not error.

The ``TENANT_DEFAULT`` constant is the SAME literal as 0001/0002 — Pitfall 10:
single source of truth for the v1 default tenant UUID across every table.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.wallet.constants import (
    HOUSE_PROMO_ACCOUNT_ID,
    HOUSE_REVENUE_ACCOUNT_ID,
    KIND_HOUSE_PROMO,
    KIND_HOUSE_REVENUE,
    OWNER_SYSTEM,
    PLAY_USD,
)

# revision identifiers, used by Alembic.
revision: str = "0003_phase3_wallet_ledger"
down_revision: str | None = "0002_phase2_auth"
branch_labels: str | None = None
depends_on: str | None = None


# Pitfall 10: same literal as 0001_phase1_foundations.py / 0002_phase2_auth.py.
TENANT_DEFAULT = "00000000-0000-0000-0000-000000000001"

# Locked verbatim — tests/wallet/test_migration_0003.py asserts against this.
LEDGER_IMMUTABLE_MSG = (
    "transfers/entries are append-only -- UPDATE and DELETE are forbidden"
)

# house_promo opening balance — large enough that admin recharges (which debit
# this account) never hit the ``balance >= 0`` floor in v1.
HOUSE_PROMO_OPENING_BALANCE = "1000000000.0000"


def upgrade() -> None:
    # ----------------------------------------------------------------------
    # accounts (WAL-06 / WAL-08) — UUID PK, NUMERIC(18,4) balance cache,
    # version column, tenant_id ghost, CHECK (balance >= 0).
    # ----------------------------------------------------------------------
    op.create_table(
        "accounts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("owner_type", sa.Text, nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column(
            "currency",
            sa.Text,
            nullable=False,
            server_default=sa.text(f"'{PLAY_USD}'"),
        ),
        sa.Column(
            "balance",
            sa.Numeric(18, 4),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "version",
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
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            server_default=sa.text(f"'{TENANT_DEFAULT}'::uuid"),
        ),
        sa.UniqueConstraint(
            "owner_type",
            "owner_id",
            "kind",
            "currency",
            name="accounts_owner_kind_currency_key",
        ),
        sa.CheckConstraint("balance >= 0", name="balance_non_negative"),
    )

    # ----------------------------------------------------------------------
    # transfers (WAL-06) — immutable business event; idempotency_key UNIQUE.
    # NO updated_at / deleted_at.
    # ----------------------------------------------------------------------
    op.create_table(
        "transfers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("idempotency_key", sa.Text, nullable=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("idempotency_key", name="transfers_idempotency_key_key"),
    )

    # ----------------------------------------------------------------------
    # entries (WAL-06) — append-only double-entry legs; FK transfer/account,
    # direction + amount CHECKs, index on account_id.
    # ----------------------------------------------------------------------
    op.create_table(
        "entries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "transfer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("transfers.id"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id"),
            nullable=False,
        ),
        sa.Column("direction", sa.Text, nullable=False),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "direction IN ('debit','credit')", name="entries_direction_check"
        ),
        sa.CheckConstraint("amount > 0", name="entries_amount_positive"),
    )
    op.create_index("entries_account_idx", "entries", ["account_id"])

    # ----------------------------------------------------------------------
    # Immutability (WAL-06) — PORT of the Phase 1 audit_log pattern (0001),
    # generalized to one shared function for both ledger tables. accounts is
    # intentionally EXCLUDED (its balance is a mutable cache).
    # ----------------------------------------------------------------------
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION raise_ledger_immutable() RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION '{LEDGER_IMMUTABLE_MSG}';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    for tbl in ("transfers", "entries"):
        op.execute(
            f"""
            CREATE TRIGGER {tbl}_immutability_trigger
                BEFORE UPDATE OR DELETE ON {tbl}
                FOR EACH ROW EXECUTE FUNCTION raise_ledger_immutable();
            """
        )
        # Defense-in-depth: REVOKE so the GRANT layer rejects too.
        op.execute(f"REVOKE UPDATE, DELETE ON {tbl} FROM PUBLIC;")

    # ----------------------------------------------------------------------
    # Seed system-account singletons (idempotent — ON CONFLICT DO NOTHING on
    # the unique owner/kind/currency tuple). house_promo is the recharge SOURCE
    # (funded); house_revenue is the Phase 5 SINK (balance 0). Fixed UUIDs come
    # from app/wallet/constants.py so the service can reference them directly.
    # ----------------------------------------------------------------------
    op.execute(
        f"""
        INSERT INTO accounts (id, owner_type, owner_id, kind, currency, balance) VALUES
          ('{HOUSE_PROMO_ACCOUNT_ID}', '{OWNER_SYSTEM}', NULL, '{KIND_HOUSE_PROMO}',
           '{PLAY_USD}', {HOUSE_PROMO_OPENING_BALANCE}),
          ('{HOUSE_REVENUE_ACCOUNT_ID}', '{OWNER_SYSTEM}', NULL, '{KIND_HOUSE_REVENUE}',
           '{PLAY_USD}', 0)
        ON CONFLICT (owner_type, owner_id, kind, currency) DO NOTHING;
        """
    )


def downgrade() -> None:
    """Drop triggers + function, then tables in FK-safe order.

    ``entries`` references both ``transfers`` and ``accounts`` (FKs), so it is
    dropped FIRST, then ``transfers``, then ``accounts`` — mirroring the 0001
    downgrade structure (drop FK-bearing tables before their parents).
    """
    for tbl in ("transfers", "entries"):
        op.execute(
            f"DROP TRIGGER IF EXISTS {tbl}_immutability_trigger ON {tbl};"
        )
    op.execute("DROP FUNCTION IF EXISTS raise_ledger_immutable();")

    op.drop_index("entries_account_idx", table_name="entries")
    op.drop_table("entries")
    op.drop_table("transfers")
    op.drop_table("accounts")
