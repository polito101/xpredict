from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID as PyUUID
from uuid import uuid4

from slugify import slugify as _slugify
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import get_settings
from app.db.base import Base
from app.db.types import (
    Money,
    Odds,  # integration: odds precision alias (Numeric(8,6), NOT money)
)
from app.markets.enums import MarketSourceEnum, MarketStatus


def generate_slug(question: str) -> str:
    base = _slugify(question, max_length=80)
    suffix = uuid4().hex[:6]
    return f"{base}-{suffix}"


class Market(Base):
    __tablename__ = "markets"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({', '.join(repr(s.value) for s in MarketStatus)})",
            name="ck_markets_status",
        ),
        CheckConstraint(
            f"source IN ({', '.join(repr(s.value) for s in MarketSourceEnum)})",
            name="ck_markets_source",
        ),
        # Phase 13 catalog/search indexes — declared here AND in migration 0011
        # (byte-identical names) so Base.metadata matches the DB (drift-avoidance).
        Index(
            "ix_markets_question_trgm",
            "question",
            postgresql_using="gin",
            postgresql_ops={"question": "gin_trgm_ops"},
        ),
        Index("ix_markets_category", "category"),
        Index("ix_markets_status_volume_24hr", "status", "volume_24hr"),
    )

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=func.gen_random_uuid(),
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
    )
    resolution_criteria: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="HOUSE",
    )
    source_market_id: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )
    condition_id: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )
    polymarket_slug: Mapped[str | None] = mapped_column(
        String(300),
        nullable=True,
    )
    volume: Mapped[Money] = mapped_column(
        server_default="0",
        default=Decimal("0"),
    )
    volume_24hr: Mapped[Money] = mapped_column(
        server_default="0",
        default=Decimal("0"),
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="OPEN",
    )
    deadline: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    bet_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
        default=0,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    uma_resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    # --- STL-06 resolution projection (persisted inside the settlement ACID tx) ----------
    # The winner/source/justification are written by HouseMarketResolveAdapter.mark_resolved
    # on the settlement session so they commit atomically with the payouts + audit row.
    # Previously the winner lived ONLY in the admin-gated audit log -> the player saw no
    # winner and get_market_public 404'd a RESOLVED market.
    winning_outcome_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    resolution_source: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )
    resolution_justification: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    # --- BET-06 per-market stake limits (NULL = use the global BET_MIN/MAX_STAKE default) -
    # Documented NULLABLE-money exception (db/types.py, Pitfall 4): Mapped[Decimal | None]
    # + Numeric(18, 4), NOT Mapped[Money] (which is NOT-NULL). money-lint accepts this form.
    min_stake: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4),
        nullable=True,
    )
    max_stake: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4),
        nullable=True,
    )
    tenant_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        default=lambda: get_settings().TENANT_ID_DEFAULT,
    )
    # --- EVT-01 multi-outcome event-of-binaries seam (Phase 13) ------------------
    # A child market belongs to at most one market_groups row. ON DELETE SET NULL
    # (never CASCADE): deleting a group must ORPHAN its children back to standalone,
    # never delete markets that carry bets/odds/ledger state. NULL = standalone
    # binary market (the existing, byte-for-byte-unchanged path).
    group_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("market_groups.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    group_item_title: Mapped[str | None] = mapped_column(Text, nullable=True)

    outcomes: Mapped[list[Outcome]] = relationship(
        back_populates="market",
        cascade="all, delete-orphan",
        lazy="raise",
    )
    odds_snapshots: Mapped[list[OddsSnapshot]] = relationship(
        back_populates="market",
        cascade="all, delete-orphan",
        lazy="raise",
    )
    group: Mapped[MarketGroup | None] = relationship(
        back_populates="markets",
        lazy="raise",
    )


class MarketGroup(Base):
    """A multi-outcome event grouping N independent binary YES/NO markets (EVT-01).

    Each child :class:`Market` is still a 2-outcome binary (the ``MKT-08``
    ``trg_binary_outcomes_only`` trigger is untouched); grouping happens one level
    up here. Event status is DERIVED from constituent markets in Phase 15 — this
    table deliberately stores NO ``status``/``winning_outcome`` column (EVT-06) and
    no money column. Mirrors the migration 0011 ``market_groups`` set exactly.
    """

    __tablename__ = "market_groups"
    __table_args__ = (
        CheckConstraint(
            f"source IN ({', '.join(repr(s.value) for s in MarketSourceEnum)})",
            name="ck_market_groups_source",
        ),
        # Declared here AND in migration 0011 (byte-identical names) so
        # Base.metadata matches the DB (the repo's drift-avoidance convention).
        Index(
            "ix_market_groups_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
        Index(
            "ix_market_groups_source_source_event_id",
            "source",
            "source_event_id",
            unique=True,
            postgresql_where=text("source_event_id IS NOT NULL"),
        ),
        Index("ix_market_groups_category", "category"),
    )

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=func.gen_random_uuid(),
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="HOUSE",
    )
    source_event_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    slug: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    tenant_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        default=lambda: get_settings().TENANT_ID_DEFAULT,
    )

    # NO cascade="all, delete-orphan": the FK is ON DELETE SET NULL, so deleting a
    # group must ORPHAN its children (not delete financial rows). lazy="raise"
    # keeps the explicit-eager-load discipline used by the existing relationships.
    markets: Mapped[list[Market]] = relationship(
        back_populates="group",
        lazy="raise",
    )


class Outcome(Base):
    __tablename__ = "outcomes"
    __table_args__ = (
        CheckConstraint(
            "initial_odds >= 0 AND initial_odds <= 1",
            name="ck_outcomes_initial_odds_range",
        ),
        CheckConstraint(
            "current_odds >= 0 AND current_odds <= 1",
            name="ck_outcomes_current_odds_range",
        ),
    )

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=func.gen_random_uuid(),
    )
    market_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("markets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label: Mapped[str] = mapped_column(String(50), nullable=False)
    initial_odds: Mapped[Odds] = mapped_column()
    current_odds: Mapped[Odds] = mapped_column()
    tenant_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        default=lambda: get_settings().TENANT_ID_DEFAULT,
    )

    market: Mapped[Market] = relationship(back_populates="outcomes")


class OddsSnapshot(Base):
    __tablename__ = "odds_snapshots"
    __table_args__ = (
        CheckConstraint(
            "probability >= 0 AND probability <= 1",
            name="ck_odds_snapshots_probability_range",
        ),
        # Phase 13 per-outcome price-history index — declared here AND in migration
        # 0011 (byte-identical name) so Base.metadata matches the DB. ADDITIVE
        # alongside the existing single-column index on outcome_id (index=True
        # below); the existing one is NOT dropped.
        Index(
            "ix_odds_snapshots_outcome_id_snapshot_at",
            "outcome_id",
            "snapshot_at",
        ),
    )

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=func.gen_random_uuid(),
    )
    market_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("markets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    outcome_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("outcomes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    probability: Mapped[Odds] = mapped_column()
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    tenant_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        default=lambda: get_settings().TENANT_ID_DEFAULT,
    )

    market: Mapped[Market] = relationship(back_populates="odds_snapshots")
