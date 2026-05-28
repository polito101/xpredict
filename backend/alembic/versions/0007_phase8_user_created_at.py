"""Phase 8 (Plan 08-01): add users.created_at for the admin CRM.

Revision ID: 0007_phase8_user_created_at
Revises: 0006_merge_phase5_phase6
Create Date: 2026-05-28

The fastapi-users base ``users`` table (migration 0002) ships id / email /
hashed_password / is_active / is_superuser / is_verified plus the XPredict
additions (display_name, banned_at, token_version, tenant_id) — but NO signup
timestamp. The admin CRM (ADU-01 / D-05) must sort and filter users by signup
date, so this additive, backward-compatible migration adds a non-null
``created_at TIMESTAMPTZ`` with ``server_default=now()``: existing rows backfill
to the migration's execution time, and new rows stamp at insert.

Matches ``app/auth/models.py`` ``User.created_at`` verbatim. No data is rewritten
beyond the one-time backfill; no FK / constraint changes. The downgrade simply
drops the column.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0007_phase8_user_created_at"
down_revision: str | None = "0006_merge_phase5_phase6"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "created_at")
