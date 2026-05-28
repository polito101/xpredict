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
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import get_settings
from app.db.base import Base
from app.db.types import Money
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
    )

    id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=func.gen_random_uuid(),
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False,
    )
    resolution_criteria: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="HOUSE",
    )
    source_market_id: Mapped[str | None] = mapped_column(
        String(200), nullable=True,
    )
    condition_id: Mapped[str | None] = mapped_column(
        String(200), nullable=True,
    )
    volume: Mapped[Money] = mapped_column(
        server_default="0", default=Decimal("0"),
    )
    volume_24hr: Mapped[Money] = mapped_column(
        server_default="0", default=Decimal("0"),
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="OPEN",
    )
    deadline: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    bet_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    tenant_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        default=lambda: get_settings().TENANT_ID_DEFAULT,
    )

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


class Outcome(Base):
    __tablename__ = "outcomes"

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
    initial_odds: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)
    current_odds: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)
    tenant_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        default=lambda: get_settings().TENANT_ID_DEFAULT,
    )

    market: Mapped[Market] = relationship(back_populates="outcomes")


class OddsSnapshot(Base):
    __tablename__ = "odds_snapshots"

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
    probability: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    tenant_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        default=lambda: get_settings().TENANT_ID_DEFAULT,
    )

    market: Mapped[Market] = relationship(back_populates="odds_snapshots")
