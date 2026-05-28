"""User + RefreshToken ORM models (D-02, D-08, AUTH-01, AUTH-09).

Schema is locked here; the Alembic 0002 migration (Plan 02-01 Task 3) creates
both tables to match these declarations verbatim. Pattern mirrors
``app/core/audit/models.py`` for UUID PK + tenant_id ghost + server_default.

D-02: ``User`` uses multiple inheritance — ``SQLAlchemyBaseUserTableUUID``
(fastapi-users 15.0.5) gives id/email/hashed_password/is_active/is_superuser/
is_verified; ``app.db.base.Base`` is our project ``DeclarativeBase``.

D-10: ``display_name`` is nullable so Phase 3 (wallet) + Phase 8 (CRM) avoid
ALTER TABLE. ``banned_at`` ships now (Phase 8 logic is deferred).

AUTH-09: ``token_version`` on both User and RefreshToken implements
password-reset session invalidation — ``DatabaseStrategy.read_token``
(Plan 02-02 / 02-03) rejects tokens whose snapshot version is lower than
the user's current version.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID as PyUUID
from uuid import uuid4

from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTableUUID
from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import get_settings
from app.db.base import Base


class User(SQLAlchemyBaseUserTableUUID, Base):
    """XPredict user.

    SQLAlchemyBaseUserTableUUID provides (locked by fastapi-users 15.0.5):
      - id           UUID PK (default=uuid4)
      - email        String(320) UNIQUE indexed
      - hashed_password String(1024)
      - is_active    Bool default True
      - is_superuser Bool default False
      - is_verified  Bool default False

    XPredict-specific columns appended below (D-08).
    """

    __tablename__ = "users"

    # D-10: optional display name for wallet UI (Phase 3) + CRM (Phase 8).
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Phase 8 ban state — column shipped now (CONTEXT line 23), logic deferred.
    banned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # AUTH-06 / Pitfall 6: bump on password reset to invalidate every prior
    # refresh token in one shot. ``DatabaseStrategy.read_token`` enforces this.
    token_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
        default=0,
    )

    # tenant_id ghost (PLT-01 / D-22) — copies the pattern from
    # ``app/core/audit/models.py`` lines 47-51 verbatim.
    tenant_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        default=lambda: get_settings().TENANT_ID_DEFAULT,
    )

    # AUTH-09 reuse-detection cleanup: cascade=all,delete-orphan so user
    # deletion (Phase 8) wipes every issued token.
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class RefreshToken(Base):
    """One row per refresh token issued. Hash-only storage (AUTH-09).

    ``token_hash`` stores SHA256 of the raw token — a DB breach must NOT
    leak live tokens (T-02-05 mitigation). ``token_version`` snapshots
    the issuing user's version at issue time so password reset (bump) can
    invalidate this row.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,  # WR-05: Python-side default
        server_default=func.gen_random_uuid(),  # raw SQL inserts
    )
    token_hash: Mapped[str] = mapped_column(
        Text,
        unique=True,
        nullable=False,
        index=True,
    )
    user_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    # ``reuse_count`` increments when the reuse-detection branch fires
    # (presenting an already-revoked token revokes ALL user tokens; the
    # counter on the surviving row records how many times this happened).
    reuse_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
        default=0,
    )
    # Snapshot of user.token_version at issue time. AUTH-06 belt-and-suspenders:
    # DatabaseStrategy.read_token returns None when user.token_version > this.
    token_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
        default=0,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="refresh_tokens")
