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


class MarketCreate(BaseModel):
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


class MarketUpdate(BaseModel):
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
    outcomes: list[OutcomeRead]

    @field_serializer("volume", "volume_24hr")
    @classmethod
    def serialize_volume_decimal(cls, v: Decimal) -> str:
        return str(v)


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
