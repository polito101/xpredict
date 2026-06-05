"""LiveBetsBet ORM model (v1.3, LB-A) — the ``livebets_bets`` mirror table.

A local mirror of a live-bets bet: the live-bets ``bet_id`` (PK, supplied by
live-bets — NOT server-defaulted), the owning XPredict ``user_id``, the live-bets
identifiers, the authoritative ``stake`` read from ``GET /v2/bets/{id}`` at
placement, and the lifecycle ``status``. The mirror row is the server-side truth
the settled handler reads (it never trusts a client-supplied amount) AND the
PRIMARY idempotency guard (``status != PENDING`` => replay no-op), exactly as the
``bets.status`` filter is the primary guard in ``app/settlement/service.py``.

Conventions followed (``backend/CONVENTIONS.md``):
  - money column ``stake`` uses ``Mapped[Money]`` (NUMERIC(18,4)) so
    ``scripts/lint_money_columns.py`` passes (§1 / WAL-05).
  - ``user_id`` is a plain UUID with NO database FK — matching ``bets.user_id``
    (FK-less by project convention; see the ``0005`` migration note). Validation
    flows through live-bets verification, not a DB FK.
  - ``tenant_id`` ghost column (§2 / PLT-01) — nullable UUID defaulting to
    ``Settings.TENANT_ID_DEFAULT``.
  - status CHECK matches live-bets' REAL ``BetStatus`` enum
    (``PENDING|WON|LOST|REFUNDED|VOIDED`` — NO ``VOID``).

The model<->migration DDL is kept identical to ``0011_livebets_bridge.py`` (the
project asserts model/migration parity elsewhere; do not drift).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID as PyUUID

from sqlalchemy import CheckConstraint, DateTime, Index, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import get_settings
from app.db.base import Base
from app.db.types import Money
from app.integrations.livebets.constants import LIVEBETS_PENDING


class LiveBetsBet(Base):
    """One mirrored live-bets bet owned by an XPredict ``user_id``.

    ``status`` walks ``PENDING`` -> ``WON`` / ``LOST`` / ``REFUNDED`` / ``VOIDED``
    when ``LiveBetsBridge.record_settled`` mirrors the terminal state; the
    PENDING-only filter is the primary idempotency guard for settlement replays.
    """

    __tablename__ = "livebets_bets"

    # The live-bets UUID — supplied by live-bets, NOT server-defaulted.
    bet_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    # The owning XPredict user — plain UUID, NO DB FK (matches bets.user_id).
    user_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    # live-bets identifiers; nullable — placement may know the table, the market
    # id comes from get_bet and may be absent on some payloads.
    table_id: Mapped[PyUUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    market_id: Mapped[PyUUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    stake: Mapped[Money] = mapped_column()
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=LIVEBETS_PENDING)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    settled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # tenant_id ghost (PLT-01 / CONVENTIONS §2) — copied from app/bets/models.py.
    tenant_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        default=lambda: get_settings().TENANT_ID_DEFAULT,
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING','WON','LOST','REFUNDED','VOIDED')",
            name="livebets_bets_status_check",
        ),
        Index("livebets_bets_user_idx", "user_id"),
    )
