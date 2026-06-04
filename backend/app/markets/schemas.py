from __future__ import annotations

import math
from datetime import UTC, datetime
from decimal import Decimal
from typing import Generic, TypeVar
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

T = TypeVar("T")


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


class _StakeLimitFields(BaseModel):
    """Shared per-market stake-limit fields + cross-field validation (BET-06).

    Mixed into both ``MarketCreate`` and ``MarketUpdate`` so the bound constraints
    (WR-02: ``gt=0`` — a stake bound of 0 is out of domain; stake must be > 0) and
    the ``min_stake <= max_stake`` cross-field check (WR-01) live in ONE place. Both
    bounds stay Optional/nullable — NULL means "fall back to the global
    ``BET_MIN_STAKE`` / ``BET_MAX_STAKE``". The client `refine` already enforces the
    same range, but a direct API caller could bypass it, so the server re-validates.
    """

    # BET-06 per-market stake limits (optional; NULL = global default).
    min_stake: Decimal | None = Field(default=None, gt=0)
    max_stake: Decimal | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _validate_stake_range(self) -> _StakeLimitFields:
        # Only meaningful when BOTH bounds are supplied. An inverted range would make
        # every bet impossible once the limits are actually persisted (CR-01) — reject
        # it at the edge with a 422 rather than silently shipping an unbettable market.
        if (
            self.min_stake is not None
            and self.max_stake is not None
            and self.min_stake > self.max_stake
        ):
            raise ValueError("min_stake must be less than or equal to max_stake")
        return self


class MarketCreate(_StakeLimitFields):
    question: str = Field(min_length=1, max_length=500)
    resolution_criteria: str = Field(min_length=1, max_length=2000)
    deadline: datetime
    initial_odds_yes: Decimal = Field(default=Decimal("0.5"), gt=0, lt=1)
    category: str | None = Field(default=None, max_length=100)

    @field_validator("deadline")
    @classmethod
    def deadline_must_be_future(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            v = v.replace(tzinfo=UTC)
        if v <= datetime.now(UTC):
            raise ValueError("Deadline must be in the future")
        return v


class MarketUpdate(_StakeLimitFields):
    resolution_criteria: str | None = Field(default=None, max_length=2000)
    deadline: datetime | None = None
    odds_yes: Decimal | None = Field(default=None, gt=0, lt=1)
    category: str | None = None

    @field_validator("deadline")
    @classmethod
    def deadline_must_be_future(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return v
        if v.tzinfo is None:
            v = v.replace(tzinfo=UTC)
        if v <= datetime.now(UTC):
            raise ValueError("Deadline must be in the future")
        return v


class OutcomeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    label: str
    initial_odds: Decimal
    current_odds: Decimal

    @field_serializer("initial_odds", "current_odds")
    @classmethod
    def serialize_decimal(cls, v: Decimal) -> str:
        return str(v)


class MarketRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    question: str
    slug: str
    resolution_criteria: str
    category: str | None
    source: str
    source_market_id: str | None
    status: str
    deadline: datetime
    bet_count: int
    volume: Decimal = Decimal("0")
    volume_24hr: Decimal = Decimal("0")
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    resolved_at: datetime | None
    # STL-06: the resolution projection exposed publicly on a RESOLVED market.
    winning_outcome_id: UUID | None = None
    resolution_source: str | None = None
    resolution_justification: str | None = None
    # BET-06: per-market stake limits (NULL = the global default applies).
    min_stake: Decimal | None = None
    max_stake: Decimal | None = None
    outcomes: list[OutcomeRead]

    @field_serializer("volume", "volume_24hr")
    @classmethod
    def serialize_volume_decimal(cls, v: Decimal) -> str:
        return str(v)

    @field_serializer("min_stake", "max_stake")
    @classmethod
    def serialize_stake_decimal(cls, v: Decimal | None) -> str | None:
        # Money on the wire is a JSON string (WAL-05 / CONVENTIONS); None stays null.
        return str(v) if v is not None else None


class MarketListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    question: str
    slug: str
    category: str | None
    source: str
    source_market_id: str | None = None
    polymarket_slug: str | None = None
    status: str
    deadline: datetime
    bet_count: int
    created_at: datetime
    volume: Decimal = Decimal("0")
    volume_24hr: Decimal = Decimal("0")
    source_url: str | None = None
    outcomes: list[OutcomeRead]

    @field_serializer("volume", "volume_24hr")
    @classmethod
    def serialize_decimal(cls, v: Decimal) -> str:
        return str(v)

    @model_validator(mode="after")
    def compute_source_url(self) -> MarketListItem:
        """Derive source_url from source + polymarket_slug (T-06-07).

        Uses the Gamma API slug for the URL path — the numeric
        source_market_id is not a valid Polymarket event URL segment.
        """
        if self.source == "POLYMARKET" and self.polymarket_slug:
            self.source_url = f"https://polymarket.com/event/{self.polymarket_slug}"
        else:
            self.source_url = None
        return self


class PricePoint(BaseModel):
    """One point on the YES-probability price-history series (MKT-03).

    ``probability`` is the YES outcome's odds at ``ts`` (an ``OddsSnapshot`` row, or
    the hourly-bucket representative for the 30d window). Serialized as a JSON STRING
    (SP-1) — never a lossy float; ``ts`` is tz-aware ISO-8601 (SP-2).
    """

    ts: datetime
    probability: Decimal

    @field_serializer("probability")
    @classmethod
    def serialize_decimal(cls, v: Decimal) -> str:
        return str(v)


class PriceHistoryResponse(BaseModel):
    """The price-history payload for one window (24h / 7d / 30d).

    ``points`` is empty or single-element for a low-data market (<2 snapshots), which
    the frontend renders as the friendly 'not enough history yet' placeholder.
    """

    window: str
    points: list[PricePoint]


class ActivityItem(BaseModel):
    """One anonymized recent-activity row (MKT-03, T-09-05).

    ANONYMIZED SERVER-SIDE: this schema intentionally has NO ``user_id`` / ``email`` /
    ``display_name`` / ``user`` field — only the chosen outcome label, the stake
    amount (string on the wire, SP-1), and the tz-aware timestamp. The browser must
    never receive a user identity (CONTEXT Area 1, 09-RESEARCH Pattern 8). Do NOT add
    a user-identity field here.
    """

    outcome: str
    amount: Decimal
    created_at: datetime

    @field_serializer("amount")
    @classmethod
    def serialize_decimal(cls, v: Decimal) -> str:
        return str(v)


def paginated_response(
    items: list[T],
    total: int,
    page: int,
    page_size: int,
) -> PaginatedResponse[T]:
    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=max(1, math.ceil(total / page_size)),
    )
