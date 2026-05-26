"""Phase 1 foundations: audit_log + feature_flags with tenant_id ghost column.

Revision ID: 0001_phase1_foundations
Revises:
Create Date: 2026-05-26

Creates the two tables Phase 1 owns (D-15). Defense-in-depth immutability
for ``audit_log`` via Postgres trigger + ``REVOKE UPDATE, DELETE`` (D-20).
``tenant_id UUID`` ghost column on both tables, defaulted to
``00000000-0000-0000-0000-000000000001`` per Settings.TENANT_ID_DEFAULT (D-22,
PLT-01). Seeds 3 feature flags per D-39.

The ``TENANT_DEFAULT`` constant is defined once and reused on both tables —
Pitfall 10 mitigation (avoids divergent defaults across tables).
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_phase1_foundations"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


# Pitfall 10: define once, reuse on every table that needs the ghost column.
TENANT_DEFAULT = "00000000-0000-0000-0000-000000000001"


# D-44 trigger error message (locked verbatim — tests assert against this).
AUDIT_IMMUTABLE_MSG = "audit_log is append-only -- UPDATE and DELETE are forbidden"


def upgrade() -> None:
    # ----------------------------------------------------------------------
    # audit_log (D-19)
    # ----------------------------------------------------------------------
    op.create_table(
        "audit_log",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "occurred_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("actor", sa.Text, nullable=False),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("ip", postgresql.INET, nullable=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            server_default=sa.text(f"'{TENANT_DEFAULT}'::uuid"),
        ),
    )
    op.create_index(
        "ix_audit_log_occurred_at",
        "audit_log",
        [sa.text("occurred_at DESC")],
    )
    op.create_index("ix_audit_log_event_type", "audit_log", ["event_type"])
    op.create_index("ix_audit_log_actor", "audit_log", ["actor"])

    # ----------------------------------------------------------------------
    # audit_log immutability — Postgres trigger (D-20)
    # ----------------------------------------------------------------------
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION raise_audit_immutable() RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION '{AUDIT_IMMUTABLE_MSG}';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_log_immutability_trigger
            BEFORE UPDATE OR DELETE ON audit_log
            FOR EACH ROW EXECUTE FUNCTION raise_audit_immutable();
        """
    )

    # ----------------------------------------------------------------------
    # Defense-in-depth: REVOKE so the GRANT layer rejects too (D-20)
    # ----------------------------------------------------------------------
    op.execute("REVOKE UPDATE, DELETE ON audit_log FROM PUBLIC;")

    # ----------------------------------------------------------------------
    # feature_flags (D-37)
    # ----------------------------------------------------------------------
    op.create_table(
        "feature_flags",
        sa.Column("key", sa.Text, nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column("value", postgresql.JSONB, nullable=True),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,  # part of composite PK → cannot be NULL
            server_default=sa.text(f"'{TENANT_DEFAULT}'::uuid"),
        ),
        sa.PrimaryKeyConstraint("key", "tenant_id"),
    )

    # ----------------------------------------------------------------------
    # Seed default feature flags (D-39) — idempotent ON CONFLICT DO NOTHING
    # so re-running the migration against an existing DB doesn't error.
    # ----------------------------------------------------------------------
    op.execute(
        f"""
        INSERT INTO feature_flags (key, enabled, tenant_id) VALUES
          ('stripe_recharge_enabled', FALSE, '{TENANT_DEFAULT}'),
          ('polymarket_sync_enabled', FALSE, '{TENANT_DEFAULT}'),
          ('admin_2fa_required',     FALSE, '{TENANT_DEFAULT}')
        ON CONFLICT (key, tenant_id) DO NOTHING;
        """
    )


def downgrade() -> None:
    """Drop both tables, the trigger, and the function.

    ``audit_log`` is dropped with CASCADE so that any Phase 2+ foreign keys
    referencing it are removed cleanly without manual intervention (WR-06).
    ``feature_flags`` is listed first because Phase 2+ may reference it; if a
    downstream FK exists and ``feature_flags`` is dropped first, Postgres will
    error — at that point the migration author must update the downgrade order.
    """
    op.execute(
        "DROP TRIGGER IF EXISTS audit_log_immutability_trigger ON audit_log;"
    )
    op.execute("DROP FUNCTION IF EXISTS raise_audit_immutable();")
    op.drop_table("feature_flags")
    op.drop_index("ix_audit_log_actor", table_name="audit_log")
    op.drop_index("ix_audit_log_event_type", table_name="audit_log")
    op.drop_index("ix_audit_log_occurred_at", table_name="audit_log")
    op.execute("DROP TABLE IF EXISTS audit_log CASCADE;")
