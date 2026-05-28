"""ORM + schema shape tests for AUTH-01, D-02, D-08, D-09, D-10.

Tests verify class hierarchy, column properties via ``__table__.columns``,
relationship configuration, and ``UserRead`` serialization (``is_superuser``
hidden, ``is_admin`` exposed).

These tests run as plain unit tests — they introspect the SQLAlchemy
metadata + Pydantic model shape WITHOUT requiring a live Postgres connection.
Integration of the schema with Alembic 0002 lives in
``test_migration_0002.py``.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTableUUID
from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.types import DateTime

from app.auth.models import RefreshToken, User
from app.auth.schemas import UserCreate, UserRead, UserUpdate
from app.db.base import Base

# ---------------------------------------------------------------------------
# D-02: multiple inheritance (User extends both fastapi-users mixin AND Base)
# ---------------------------------------------------------------------------


def test_user_multiple_inheritance() -> None:
    """``User`` MRO must include BOTH SQLAlchemyBaseUserTableUUID AND Base."""
    mro = User.__mro__
    assert (
        SQLAlchemyBaseUserTableUUID in mro
    ), f"User must inherit SQLAlchemyBaseUserTableUUID; got MRO={[c.__name__ for c in mro]}"
    assert Base in mro, f"User must inherit app.db.base.Base; got MRO={[c.__name__ for c in mro]}"


def test_user_tablename() -> None:
    assert User.__tablename__ == "users"


# ---------------------------------------------------------------------------
# D-08: required custom columns on users
# ---------------------------------------------------------------------------


def test_user_has_custom_columns() -> None:
    """``User`` declares Phase 2 custom columns (D-08, D-10)."""
    cols = User.__table__.columns

    # display_name nullable Text
    assert "display_name" in cols
    assert isinstance(cols["display_name"].type, Text)
    assert cols["display_name"].nullable is True

    # banned_at nullable timestamptz
    assert "banned_at" in cols
    assert isinstance(cols["banned_at"].type, DateTime)
    assert cols["banned_at"].nullable is True

    # token_version int NOT NULL server_default '0'
    assert "token_version" in cols
    assert isinstance(cols["token_version"].type, Integer)
    assert cols["token_version"].nullable is False
    # server_default is a TextClause("'0'") or similar — compare via .text or arg
    sd = cols["token_version"].server_default
    assert sd is not None
    assert "0" in str(sd.arg) if hasattr(sd, "arg") else "0" in str(sd)

    # tenant_id nullable UUID
    assert "tenant_id" in cols
    assert isinstance(cols["tenant_id"].type, PG_UUID)
    assert cols["tenant_id"].nullable is True


def test_user_has_fastapi_users_base_columns() -> None:
    """``User`` inherits id/email/hashed_password/is_active/is_superuser/is_verified."""
    cols = User.__table__.columns
    required = {
        "id",
        "email",
        "hashed_password",
        "is_active",
        "is_superuser",
        "is_verified",
    }
    missing = required - set(cols.keys())
    assert not missing, f"User missing fastapi-users columns: {missing}"


# ---------------------------------------------------------------------------
# Relationship: user.refresh_tokens cascades on delete-orphan
# ---------------------------------------------------------------------------


def test_user_refresh_tokens_relationship() -> None:
    """``User.refresh_tokens`` is a list[RefreshToken] with cascade=all,delete-orphan."""
    rel = User.__mapper__.relationships.get("refresh_tokens")
    assert rel is not None, "User missing refresh_tokens relationship"
    # The mapper-resolved class for the relationship target must be RefreshToken
    assert rel.mapper.class_ is RefreshToken
    # delete-orphan is the critical cascade for AUTH-09 cleanup
    assert "delete-orphan" in rel.cascade
    assert "all" in str(rel.cascade) or rel.cascade.delete


# ---------------------------------------------------------------------------
# D-08: RefreshToken schema
# ---------------------------------------------------------------------------


def test_refresh_token_tablename() -> None:
    assert RefreshToken.__tablename__ == "refresh_tokens"


def test_refresh_token_has_required_columns() -> None:
    """RefreshToken has all 8 schema-locked columns (D-08, AUTH-09)."""
    cols = RefreshToken.__table__.columns
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
    missing = required - set(cols.keys())
    assert not missing, f"RefreshToken missing columns: {missing}"


def test_refresh_token_id_is_uuid_pk_with_dual_default() -> None:
    """``RefreshToken.id`` is UUID PK with BOTH default=uuid4 AND server_default."""
    col = RefreshToken.__table__.columns["id"]
    assert isinstance(col.type, PG_UUID)
    assert col.primary_key is True
    # Python-side default produces a UUID object (uuid4 callable)
    assert col.default is not None
    # server_default for raw SQL inserts
    assert col.server_default is not None


def test_refresh_token_token_hash_unique() -> None:
    """``token_hash`` is UNIQUE + NOT NULL (security: never duplicate stored hashes)."""
    col = RefreshToken.__table__.columns["token_hash"]
    assert col.nullable is False
    assert isinstance(col.type, Text)
    # Either the column itself is unique=True OR a unique index exists in __table_args__
    is_unique = col.unique or any(
        idx.unique and "token_hash" in [c.name for c in idx.columns]
        for idx in RefreshToken.__table__.indexes
    )
    assert is_unique, "RefreshToken.token_hash must be UNIQUE"


def test_refresh_token_user_id_fk_cascade() -> None:
    """``user_id`` FK references ``users.id`` ON DELETE CASCADE."""
    col = RefreshToken.__table__.columns["user_id"]
    assert col.nullable is False
    assert isinstance(col.type, PG_UUID)
    fks = list(col.foreign_keys)
    assert len(fks) == 1
    fk: ForeignKey = fks[0]
    # FK column reference is "users.id"
    assert fk.column.table.name == "users"
    assert fk.column.name == "id"
    assert fk.ondelete == "CASCADE"


def test_refresh_token_reuse_count_default_zero() -> None:
    col = RefreshToken.__table__.columns["reuse_count"]
    assert isinstance(col.type, Integer)
    assert col.nullable is False
    sd = col.server_default
    assert sd is not None
    assert "0" in str(sd.arg) if hasattr(sd, "arg") else "0" in str(sd)


def test_refresh_token_token_version_default_zero() -> None:
    col = RefreshToken.__table__.columns["token_version"]
    assert isinstance(col.type, Integer)
    assert col.nullable is False
    sd = col.server_default
    assert sd is not None
    assert "0" in str(sd.arg) if hasattr(sd, "arg") else "0" in str(sd)


def test_refresh_token_created_at_server_default_now() -> None:
    col = RefreshToken.__table__.columns["created_at"]
    assert col.nullable is False
    assert col.server_default is not None


# ---------------------------------------------------------------------------
# D-09: UserRead exposes is_admin, hides is_superuser
# ---------------------------------------------------------------------------


def test_user_read_maps_is_superuser_to_is_admin() -> None:
    """UserRead(is_superuser=True).model_dump() -> contains is_admin=True, NOT is_superuser."""
    user_id = uuid.uuid4()
    r = UserRead(
        id=user_id,
        email="admin@xpredict.example.com",
        is_active=True,
        is_verified=True,
        is_superuser=True,
    )
    dumped = r.model_dump()
    assert "is_admin" in dumped, f"UserRead.model_dump() missing is_admin: {dumped}"
    assert dumped["is_admin"] is True
    # Defense-in-depth: is_superuser MUST NOT appear in the wire payload.
    assert "is_superuser" not in dumped, f"UserRead leaks is_superuser to model_dump(): {dumped}"


def test_user_read_player_dump() -> None:
    """Regular player (is_superuser=False) dumps is_admin=False."""
    r = UserRead(
        id=uuid.uuid4(),
        email="player@xpredict.example.com",
        is_active=True,
        is_verified=False,
        is_superuser=False,
        display_name="Alice",
    )
    dumped = r.model_dump()
    assert dumped["is_admin"] is False
    assert "is_superuser" not in dumped
    assert dumped["display_name"] == "Alice"


def test_user_read_display_name_optional() -> None:
    """display_name is optional and defaults to None."""
    r = UserRead(
        id=uuid.uuid4(),
        email="p@example.com",
        is_active=True,
        is_verified=False,
        is_superuser=False,
    )
    assert r.display_name is None


# ---------------------------------------------------------------------------
# D-10: UserCreate / UserUpdate accept display_name
# ---------------------------------------------------------------------------


def test_user_create_accepts_display_name() -> None:
    """UserCreate has optional display_name field for register payload."""
    payload = UserCreate(
        email="new@xpredict.example.com",
        password="ValidPass123!",
        display_name="Bob",
    )
    assert payload.display_name == "Bob"


def test_user_create_display_name_optional() -> None:
    """display_name is omittable in register payload."""
    payload = UserCreate(email="new@xpredict.example.com", password="ValidPass123!")
    assert payload.display_name is None


def test_user_update_accepts_display_name() -> None:
    """UserUpdate (PATCH /auth/users/me) accepts display_name."""
    payload = UserUpdate(display_name="Carol")
    assert payload.display_name == "Carol"


# ---------------------------------------------------------------------------
# Smoke: instantiating Settings inside the User column python-default works
# ---------------------------------------------------------------------------


def test_user_tenant_id_default_callable_resolves(monkeypatch: pytest.MonkeyPatch) -> None:
    """User.tenant_id default lambda reads Settings.TENANT_ID_DEFAULT at call time."""
    # Just call the default callable directly
    col = User.__table__.columns["tenant_id"]
    assert col.default is not None
    # Default is a ColumnDefault wrapping the lambda
    default_val = col.default.arg(None) if callable(col.default.arg) else col.default.arg
    assert isinstance(default_val, uuid.UUID)
    assert str(default_val) == "00000000-0000-0000-0000-000000000001"
