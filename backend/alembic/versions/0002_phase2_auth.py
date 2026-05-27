"""Phase 2 auth: users + refresh_tokens.

Revision ID: 0002_phase2_auth
Revises: 0001_phase1_foundations
Create Date: 2026-05-27

Creates the two tables Phase 2 owns (D-08):
  - users (fastapi-users base schema + display_name, banned_at, token_version,
    tenant_id ghost)
  - refresh_tokens (token-rotation + reuse detection store; AUTH-09)

The ``TENANT_DEFAULT`` constant is the SAME literal as Plan 01-03's
``0001_phase1_foundations.py`` — Pitfall 10 mitigation: single source of truth
for the v1 default tenant UUID across every table that needs the ghost.

Column shapes are locked against ``app/auth/models.py`` declarations
(Plan 02-01 Task 2). Any drift here breaks the model<->migration contract;
``tests/auth/test_migration_0002.py`` is the integration check.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_phase2_auth"
down_revision: str | None = "0001_phase1_foundations"
branch_labels: str | None = None
depends_on: str | None = None


# Pitfall 10: same literal as 0001_phase1_foundations.py.
TENANT_DEFAULT = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    # ----------------------------------------------------------------------
    # users (D-08, D-10, AUTH-01, AUTH-06)
    # ----------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # fastapi-users base columns — sizes verified against
        # SQLAlchemyBaseUserTableUUID source (T-02-05 mitigation:
        # hashed_password must be >= Argon2id hash length ~95 chars).
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("hashed_password", sa.String(1024), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("TRUE"),
        ),
        sa.Column(
            "is_superuser",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column(
            "is_verified",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        # XPredict additions (D-08, D-10).
        sa.Column("display_name", sa.Text, nullable=True),
        sa.Column("banned_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "token_version",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            server_default=sa.text(f"'{TENANT_DEFAULT}'::uuid"),
        ),
    )
    # UNIQUE on email (login lookup + dedupe). fastapi-users expects this.
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # ----------------------------------------------------------------------
    # refresh_tokens (D-08, AUTH-09)
    # ----------------------------------------------------------------------
    op.create_table(
        "refresh_tokens",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # SHA256 hex digest = 64 chars; Text is fine (unbounded but indexed).
        sa.Column("token_hash", sa.Text, nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "reuse_count",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        # Snapshot of user.token_version at issue (AUTH-06 belt+suspenders).
        sa.Column(
            "token_version",
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
    )
    # UNIQUE on token_hash — token rotation invariant.
    op.create_index(
        "ix_refresh_tokens_token_hash",
        "refresh_tokens",
        ["token_hash"],
        unique=True,
    )
    # FK lookup index for ``WHERE user_id = ? AND revoked_at IS NULL`` queries
    # (logout, reuse-detection bulk update, password-reset cascade).
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])


def downgrade() -> None:
    """Drop both tables + indexes in reverse FK order.

    refresh_tokens references users.id (ON DELETE CASCADE) — drop the
    FK-bearing table FIRST, then users. Indexes go before tables so we
    don't leave orphan index definitions on already-dropped tables.
    """
    # refresh_tokens (drop FK-bearing first)
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_token_hash", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")

    # users
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
