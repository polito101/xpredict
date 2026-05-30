"""Account / Transfer / Entry ORM models — the double-entry ledger (Phase 3).

Schema is LOCKED to STACK §3.2's UUID model (ARCHITECTURE.md BIGINT is
SUPERSEDED) and matches the validated spike harness DDL
(``.planning/spikes/_lib/harness.py`` SCHEMA_DDL) verbatim. The Alembic
``0003_phase3_wallet_ledger`` migration creates these tables to match — any
drift breaks the model<->migration contract checked by
``tests/wallet/test_models.py`` + ``tests/wallet/test_migration_0003.py``.

Invariants enforced at the DB layer (not here):
  - ``CHECK (balance >= 0)`` on accounts (WAL-08) — defense-in-depth.
  - ``transfers`` / ``entries`` are append-only: a BEFORE UPDATE OR DELETE
    deny-trigger + ``REVOKE UPDATE, DELETE`` (WAL-06), ported from the Phase 1
    audit_log pattern.
  - ``entries`` net to zero per transfer; ``accounts.balance`` is a
    denormalized cache whose truth is ``SUM(credit) - SUM(debit)`` over
    ``entries`` (reconciled nightly — SC#7).

Money columns (``balance``, ``amount``) use ``Mapped[Money]`` so the
``scripts/lint_money_columns.py`` gate passes (WAL-05 / NUMERIC(18,4)).

Patterns reused: UUID PK dual-default (Python ``default=uuid4`` +
``server_default=gen_random_uuid()``, WR-05) from ``app/auth/models.py``
RefreshToken; ``tenant_id`` ghost (PLT-01) from ``app/core/audit/models.py``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID as PyUUID
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import get_settings
from app.db.base import Base
from app.db.types import Money
from app.wallet.constants import PLAY_USD


class Account(Base):
    """A ledger account — a user wallet, a house/system account, or (Phase 4)
    a per-market liability account.

    ``balance`` is a denormalized cache (the truth is the sum over ``entries``);
    ``CHECK (balance >= 0)`` is a DB-level last line of defense (WAL-08), not the
    primary concurrency guard (that is ``SELECT ... FOR UPDATE`` in the service,
    Plan 03-02). ``version`` supports optimistic concurrency on non-hot paths.
    """

    __tablename__ = "accounts"

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,  # WR-05: Python-side default
        server_default=func.gen_random_uuid(),  # raw SQL inserts
    )
    owner_type: Mapped[str] = mapped_column(Text, nullable=False)
    """``system`` | ``user`` | ``market`` — see ``constants.OWNER_*``."""

    owner_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    """The user/market this account belongs to; NULL for system singletons."""

    kind: Mapped[str] = mapped_column(Text, nullable=False)
    """``user_wallet`` | ``house_promo`` | ``house_revenue`` — see ``constants.KIND_*``."""

    currency: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=PLAY_USD,
    )
    balance: Mapped[Money] = mapped_column(server_default="0")
    version: Mapped[int] = mapped_column(
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
    # tenant_id ghost (PLT-01 / D-22) — copied from app/core/audit/models.py.
    tenant_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        default=lambda: get_settings().TENANT_ID_DEFAULT,
    )

    __table_args__ = (
        UniqueConstraint(
            "owner_type",
            "owner_id",
            "kind",
            "currency",
            name="accounts_owner_kind_currency_key",
        ),
        CheckConstraint("balance >= 0", name="balance_non_negative"),
    )


class Transfer(Base):
    """An immutable business event that moves value across >=2 accounts.

    No ``updated_at`` / ``deleted_at`` — transfers are append-only (WAL-06),
    enforced by a deny-trigger + REVOKE in migration 0003. Idempotency is via
    the UNIQUE ``idempotency_key`` (a duplicate raises 23505, surfaced as a true
    idempotent response in Plan 03-04).
    """

    __tablename__ = "transfers"

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=func.gen_random_uuid(),
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    """``recharge`` | ``opening`` | ... — see ``constants.TRANSFER_*``."""

    idempotency_key: Mapped[str | None] = mapped_column(
        Text,
        unique=True,
        nullable=True,
    )
    actor_user_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    """The human actor, if any; NULL for system-initiated transfers (RESEARCH OQ2)."""

    # ``metadata`` is reserved on SQLAlchemy Declarative classes, so the Python
    # attribute is ``transfer_metadata`` mapped to the DB column ``metadata``.
    transfer_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default="{}",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class Entry(Base):
    """One leg of a double-entry transfer — append-only (WAL-06).

    Each transfer has >=2 entries that net to zero. ``amount`` is always
    positive (``CHECK (amount > 0)``); ``direction`` says whether this leg
    debits or credits ``account_id``. ``FK entries.transfer_id -> transfers.id``
    makes an orphan entry impossible.
    """

    __tablename__ = "entries"

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=func.gen_random_uuid(),
    )
    transfer_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transfers.id"),
        nullable=False,
    )
    account_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id"),
        nullable=False,
        index=True,
    )
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    """``debit`` | ``credit`` — see ``constants.DIRECTION_*``."""

    amount: Mapped[Money] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "direction IN ('debit','credit')",
            name="entries_direction_check",
        ),
        CheckConstraint("amount > 0", name="entries_amount_positive"),
        Index("entries_account_idx", "account_id"),
    )
