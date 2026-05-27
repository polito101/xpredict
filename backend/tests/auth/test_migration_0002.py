"""Integration tests for Alembic migration ``0002_phase2_auth`` (D-08).

Runs against testcontainers Postgres 16 (lazy ``engine`` fixture in
``tests/conftest.py``) which executes ``alembic upgrade head`` once for
the session. These tests then introspect the resulting schema with
SQLAlchemy's ``inspect``.

Pattern source: ``tests/core/test_audit_immutability.py`` + ``PATTERNS.md``
§"Integration Test Pattern" lines 796-805.
"""

from __future__ import annotations

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import Inspector
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


# ---------------------------------------------------------------------------
# Migration chain: 0002 head, down_revision == 0001
# ---------------------------------------------------------------------------


async def test_alembic_head_is_0002(engine: AsyncEngine) -> None:
    """After ``alembic upgrade head``, ``alembic_version.version_num == 0002_phase2_auth``."""
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT version_num FROM alembic_version"))
        version = result.scalar_one()
    assert version == "0002_phase2_auth", (
        f"Expected alembic head 0002_phase2_auth; got {version}"
    )


async def test_down_revision_chains_from_0001(engine: AsyncEngine) -> None:
    """Migration 0002 declares ``down_revision = '0001_phase1_foundations'``."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config("alembic.ini")
    s = ScriptDirectory.from_config(cfg)
    rev = s.get_revision("0002_phase2_auth")
    assert rev is not None, "Revision 0002_phase2_auth missing from script directory"
    assert rev.down_revision == "0001_phase1_foundations"


# ---------------------------------------------------------------------------
# users table — exact columns + types + defaults
# ---------------------------------------------------------------------------


async def test_users_table_exists_with_expected_columns(engine: AsyncEngine) -> None:
    """``users`` has the 10 schema-locked columns (D-08)."""

    def _get_columns(sync_conn: object) -> set[str]:
        insp: Inspector = inspect(sync_conn)  # type: ignore[arg-type]
        return {c["name"] for c in insp.get_columns("users")}

    async with engine.connect() as conn:
        column_names = await conn.run_sync(_get_columns)

    required = {
        "id",
        "email",
        "hashed_password",
        "is_active",
        "is_superuser",
        "is_verified",
        "display_name",
        "banned_at",
        "token_version",
        "tenant_id",
    }
    missing = required - column_names
    assert not missing, f"users missing columns: {missing}"


async def test_users_email_unique_index(engine: AsyncEngine) -> None:
    """``ix_users_email`` exists, is unique, and indexes the ``email`` column."""

    def _get_indexes(sync_conn: object) -> list[dict]:
        insp: Inspector = inspect(sync_conn)  # type: ignore[arg-type]
        return list(insp.get_indexes("users"))

    async with engine.connect() as conn:
        indexes = await conn.run_sync(_get_indexes)

    email_idx = next(
        (
            i
            for i in indexes
            if i.get("name") == "ix_users_email"
            or (i.get("unique") and "email" in i.get("column_names", []))
        ),
        None,
    )
    assert email_idx is not None, f"ix_users_email missing; indexes={indexes}"
    assert email_idx.get("unique") is True
    assert "email" in email_idx.get("column_names", [])


async def test_users_tenant_id_default(engine: AsyncEngine) -> None:
    """``users.tenant_id`` defaults to TENANT_DEFAULT '00000000-...-0001' (PLT-01)."""
    async with engine.connect() as conn:
        # Use SQL to insert without tenant_id and read it back
        await conn.execute(
            text(
                """
                INSERT INTO users (email, hashed_password)
                VALUES ('tenantdefault-test@example.com', 'noop')
                """
            )
        )
        result = await conn.execute(
            text(
                "SELECT tenant_id FROM users WHERE email = 'tenantdefault-test@example.com'"
            )
        )
        tenant_id = result.scalar_one()
        # Cleanup so this test stays idempotent across reruns
        await conn.execute(
            text("DELETE FROM users WHERE email = 'tenantdefault-test@example.com'")
        )
        await conn.commit()

    assert str(tenant_id) == "00000000-0000-0000-0000-000000000001"


async def test_users_id_has_gen_random_uuid_default(engine: AsyncEngine) -> None:
    """``users.id`` server_default is ``gen_random_uuid()`` (raw SQL insert auto-PK)."""

    def _get_id_default(sync_conn: object) -> str | None:
        insp: Inspector = inspect(sync_conn)  # type: ignore[arg-type]
        for col in insp.get_columns("users"):
            if col["name"] == "id":
                d = col.get("default")
                return str(d) if d is not None else None
        return None

    async with engine.connect() as conn:
        default = await conn.run_sync(_get_id_default)

    assert default is not None, "users.id missing server_default"
    assert "gen_random_uuid" in default


# ---------------------------------------------------------------------------
# refresh_tokens table — columns + FK + indexes + server defaults
# ---------------------------------------------------------------------------


async def test_refresh_tokens_table_exists_with_expected_columns(
    engine: AsyncEngine,
) -> None:
    """``refresh_tokens`` has all 8 schema-locked columns."""

    def _get_columns(sync_conn: object) -> set[str]:
        insp: Inspector = inspect(sync_conn)  # type: ignore[arg-type]
        return {c["name"] for c in insp.get_columns("refresh_tokens")}

    async with engine.connect() as conn:
        column_names = await conn.run_sync(_get_columns)

    required = {
        "id",
        "token_hash",
        "user_id",
        "expires_at",
        "revoked_at",
        "reuse_count",
        "token_version",
        "created_at",
    }
    missing = required - column_names
    assert not missing, f"refresh_tokens missing columns: {missing}"


async def test_refresh_tokens_user_id_fk_cascade(engine: AsyncEngine) -> None:
    """``refresh_tokens.user_id`` FK references ``users.id`` ON DELETE CASCADE."""

    def _get_fks(sync_conn: object) -> list[dict]:
        insp: Inspector = inspect(sync_conn)  # type: ignore[arg-type]
        return list(insp.get_foreign_keys("refresh_tokens"))

    async with engine.connect() as conn:
        fks = await conn.run_sync(_get_fks)

    user_fk = next(
        (fk for fk in fks if "user_id" in fk.get("constrained_columns", [])), None
    )
    assert user_fk is not None, f"refresh_tokens.user_id FK missing; fks={fks}"
    assert user_fk["referred_table"] == "users"
    assert user_fk["referred_columns"] == ["id"]
    assert user_fk.get("options", {}).get("ondelete") == "CASCADE"


async def test_refresh_tokens_token_hash_unique_index(engine: AsyncEngine) -> None:
    """``ix_refresh_tokens_token_hash`` exists, unique=True."""

    def _get_indexes(sync_conn: object) -> list[dict]:
        insp: Inspector = inspect(sync_conn)  # type: ignore[arg-type]
        return list(insp.get_indexes("refresh_tokens"))

    async with engine.connect() as conn:
        indexes = await conn.run_sync(_get_indexes)

    th_idx = next(
        (
            i
            for i in indexes
            if i.get("name") == "ix_refresh_tokens_token_hash"
            or (i.get("unique") and "token_hash" in i.get("column_names", []))
        ),
        None,
    )
    assert th_idx is not None, f"ix_refresh_tokens_token_hash missing; indexes={indexes}"
    assert th_idx.get("unique") is True


async def test_refresh_tokens_user_id_index(engine: AsyncEngine) -> None:
    """``ix_refresh_tokens_user_id`` exists for FK lookup performance."""

    def _get_indexes(sync_conn: object) -> list[dict]:
        insp: Inspector = inspect(sync_conn)  # type: ignore[arg-type]
        return list(insp.get_indexes("refresh_tokens"))

    async with engine.connect() as conn:
        indexes = await conn.run_sync(_get_indexes)

    ui_idx = next(
        (
            i
            for i in indexes
            if i.get("name") == "ix_refresh_tokens_user_id"
            or "user_id" in i.get("column_names", [])
        ),
        None,
    )
    assert ui_idx is not None, f"ix_refresh_tokens_user_id missing; indexes={indexes}"


async def test_refresh_tokens_reuse_count_server_default_zero(
    engine: AsyncEngine,
) -> None:
    """``refresh_tokens.reuse_count`` server_default is '0'."""

    def _get_defaults(sync_conn: object) -> dict[str, str | None]:
        insp: Inspector = inspect(sync_conn)  # type: ignore[arg-type]
        return {c["name"]: str(c.get("default")) for c in insp.get_columns("refresh_tokens")}

    async with engine.connect() as conn:
        defaults = await conn.run_sync(_get_defaults)

    # Postgres typically reports the literal default expression as a string
    # like "0" or "'0'::integer"; assert it contains a 0.
    assert defaults.get("reuse_count") is not None
    assert "0" in defaults["reuse_count"]
    assert defaults.get("token_version") is not None
    assert "0" in defaults["token_version"]
