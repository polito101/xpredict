"""Public read DTOs for the Phase-16 catalog API (BRW-01..05).

The catalog is a single bounded grid mixing standalone binary ``markets`` and
multi-outcome ``market_groups`` (events). A :class:`CatalogItem` is discriminated
by ``type`` ("market" vs "event"); for a binary market the ``outcomes`` list holds
the single YES leg, for an event one row per child (its ``group_item_title`` label
+ that child's YES price). Money/odds (``volume``, ``yes_price``) are serialized as
JSON STRINGS (the repo money-on-the-wire convention — never a lossy float), mirroring
``markets/schemas.py`` ``OutcomeRead``.

These are public, unauthenticated reads: the schemas deliberately expose ONLY the
outcome label + YES price + (derived) status — never a resolver identity, per-user
payout, or justification author (V4 public-safe projection, threat T-16-04).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_serializer


class CatalogOutcome(BaseModel):
    """One catalog-card outcome row: a label + the YES-leg price (as a string)."""

    model_config = ConfigDict(from_attributes=True)

    label: str
    yes_outcome_id: UUID | None
    yes_price: Decimal

    @field_serializer("yes_price")
    @classmethod
    def _serialize_price(cls, v: Decimal) -> str:
        # Money/odds on the wire is a JSON string (CONVENTIONS) — never a float.
        return str(v)


class CatalogItem(BaseModel):
    """A unified catalog card: a standalone ``market`` or a multi-outcome ``event``.

    ``status`` is the PUBLIC status {open, closing_soon, resolved} (the derived
    event status / stored market status mapped into the public filter vocabulary).
    ``volume`` for an event is the SUM of its children's volume (market_groups has
    no volume column).
    """

    model_config = ConfigDict(from_attributes=True)

    type: Literal["market", "event"]
    id: UUID
    slug: str
    title: str
    category: str | None
    source: str
    status: str
    deadline: datetime | None
    volume: Decimal
    created_at: datetime
    outcomes: list[CatalogOutcome]

    @field_serializer("volume")
    @classmethod
    def _serialize_volume(cls, v: Decimal) -> str:
        return str(v)


class EventOutcomeRead(BaseModel):
    """One per-outcome row on the event-detail page (a child market's YES leg)."""

    model_config = ConfigDict(from_attributes=True)

    label: str
    yes_outcome_id: UUID | None
    yes_price: Decimal
    market_id: UUID
    child_slug: str
    child_status: str

    @field_serializer("yes_price")
    @classmethod
    def _serialize_price(cls, v: Decimal) -> str:
        return str(v)


class EventDetail(BaseModel):
    """An event (``market_groups`` row) + its per-outcome child rows + derived status.

    ``status`` here is the raw ``derive_event_status`` value
    {open, partially_resolved, resolved, void} — the detail page shows the true
    derived state (richer than the public catalog filter vocabulary).
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    title: str
    category: str | None
    source: str
    status: str
    deadline: datetime | None
    created_at: datetime
    outcomes: list[EventOutcomeRead]
