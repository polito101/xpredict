"""Phase 10 (Plan 10-01): single-row tenant_config branding table.

Revision ID: 0009_phase10_tenant_config
Revises: 0008_phase8_user_created_at
Create Date: 2026-05-31

Creates the ``tenant_config`` table (D-07) that holds the operator's white-label
branding — brand name, primary/secondary palette hex, and an optional in-row logo
(D-08). A ``UNIQUE(tenant_id)`` constraint enforces the single row in v1 and is the
multi-tenant v2 seam. Chains off the single current head ``0008`` (do NOT branch —
Pitfall 6, single-head invariant).

Seeds one default row (XPredict / #4f46e5 indigo / #0ea5e9 sky, no logo) at the
``TENANT_DEFAULT`` constant via an idempotent ``INSERT ... ON CONFLICT (tenant_id)
DO NOTHING`` (the same singleton-seed pattern as 0004's house accounts), so the
public ``/branding/current`` read works against a fresh DB with no admin write.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0009_phase10_tenant_config"
down_revision: str | None = "0008_phase8_user_created_at"
branch_labels: str | None = None
depends_on: str | None = None


# Pitfall 10: same literal as 0001/0002/0004 — single source of truth for the v1
# default tenant UUID across every table.
TENANT_DEFAULT = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.create_table(
        "tenant_config",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("brand_name", sa.Text, nullable=False),
        sa.Column("primary_hex", sa.String(7), nullable=False),
        sa.Column("secondary_hex", sa.String(7), nullable=False),
        sa.Column("logo_bytes", sa.LargeBinary, nullable=True),
        sa.Column("logo_content_type", sa.String(64), nullable=True),
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
        sa.UniqueConstraint("tenant_id", name="tenant_config_tenant_id_key"),
    )

    # Idempotent singleton seed — re-running against an existing DB does not error
    # (ON CONFLICT on the unique tenant_id). Defaults: XPredict indigo/sky, no logo.
    op.execute(
        f"""
        INSERT INTO tenant_config (id, brand_name, primary_hex, secondary_hex, tenant_id)
        VALUES (gen_random_uuid(), 'XPredict', '#4f46e5', '#0ea5e9', '{TENANT_DEFAULT}'::uuid)
        ON CONFLICT (tenant_id) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.drop_table("tenant_config")
