"""Bet ORM model (Phase 5).

A player's stake on one market outcome. ``market_id`` / ``outcome_id`` are plain UUIDs
during parallel development — the FK constraints to Phase 4's ``markets`` / ``outcomes``
tables are added by the integration migration ``0005`` (off ``0004``), NOT here, so this
slice stays migration-free and the single alembic head (``0003``) is preserved. The
market is validated at placement time via ``MarketReadPort``, not by a DB FK.

The money column (``stake``) uses ``Mapped[Money]`` so ``scripts/lint_money_columns.py``
passes (NUMERIC(18,4) + Decimal). Patterns reused verbatim from ``app/wallet/models.py``:
UUID PK dual-default (Python ``default=uuid4`` + ``server_default=gen_random_uuid()``,
WR-05) and the ``tenant_id`` ghost column (PLT-01).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID as PyUUID
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, Index, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.bets.constants import BET_PENDING
from app.core.config import get_settings
from app.db.base import Base
from app.db.types import Money, Odds


class Bet(Base):
    """One stake by ``user_id`` on ``outcome_id`` of ``market_id``.

    Created in the SAME ACID transaction as the stake's ledger movement (Phase 5 SC#1):
    a kill-mid-transaction failure must leave neither the bet nor its ledger entries.
    ``status`` walks ``PENDING`` -> ``SETTLED_WON`` / ``SETTLED_LOST`` at settlement.
    """

    __tablename__ = "bets"

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    # market_id / outcome_id: plain UUIDs for now; the FK to markets/outcomes is added
    # by the integration migration 0005. Validation flows through MarketReadPort.
    market_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    outcome_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    stake: Mapped[Money] = mapped_column()
    # The chosen outcome's price/probability in (0,1] locked at placement — the "odds
    # locked at placement" payout model (ARCHITECTURE.md): a winning bet pays stake /
    # odds_at_placement. Numeric(8,6) via the Odds alias (NOT money) so the money-column
    # lint stays green; mirrors Phase 4's Outcome.current_odds precision.
    odds_at_placement: Mapped[Odds] = mapped_column()
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=BET_PENDING)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # tenant_id ghost (PLT-01) — copied from app/wallet/models.py.
    tenant_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        default=lambda: get_settings().TENANT_ID_DEFAULT,
    )

    __table_args__ = (
        CheckConstraint("stake > 0", name="bets_stake_positive"),
        CheckConstraint(
            "status IN ('PENDING','SETTLED_WON','SETTLED_LOST')",
            name="bets_status_check",
        ),
        Index("bets_user_idx", "user_id"),
        Index("bets_market_idx", "market_id"),
    )
