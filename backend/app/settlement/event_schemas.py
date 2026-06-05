"""Request/response schemas for the admin house-event surface (EVA-01, EVA-02).

Create/edit a multi-outcome HOUSE event = one ``market_groups`` row + N binary
YES/NO child markets. Every request is ``extra="forbid"`` (reject unknown keys);
``OutcomeInput.initial_odds`` is bounded ``(0, 1)``; the outcomes list requires
``>= 2`` (EVT-07 — grouping only applies to ≥2 outcomes). Money/odds in responses
serialize as JSON strings (``DecimalStr``), never floats.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.settlement.schemas import DecimalStr


class OutcomeInput(BaseModel):
    """One outcome of a house event: a label + its initial YES odds."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=100)
    initial_odds: Decimal = Field(gt=0, lt=1)


def _future_deadline(v: datetime | None) -> datetime | None:
    """Mirror ``MarketCreate.deadline_must_be_future`` — reject a past deadline."""
    if v is None:
        return v
    if v.tzinfo is None:
        v = v.replace(tzinfo=UTC)
    if v <= datetime.now(UTC):
        raise ValueError("Deadline must be in the future")
    return v


class CreateEventRequest(BaseModel):
    """Body for ``POST /admin/events`` — create a house multi-outcome event."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=500)
    category: str | None = Field(default=None, max_length=100)
    deadline: datetime
    resolution_criteria: str | None = Field(default=None, max_length=2000)
    slug: str | None = Field(default=None, max_length=100)
    outcomes: list[OutcomeInput] = Field(min_length=2)

    @field_validator("deadline")
    @classmethod
    def _deadline_future(cls, v: datetime) -> datetime:
        checked = _future_deadline(v)
        assert checked is not None  # noqa: S101 — deadline is required (not Optional) here
        return checked


class UpdateEventRequest(BaseModel):
    """Body for ``PATCH /admin/events/{group_id}`` — pre-bet edit (all fields optional).

    Outcome add/remove is modelled as a whole-list REPLACE: supply the full new
    ``outcomes`` list (≥2) to replace the children, or omit it to leave them untouched
    (RESEARCH Pattern 6). The 423 edit-lock guard runs at the endpoint BEFORE this.
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=500)
    category: str | None = Field(default=None, max_length=100)
    deadline: datetime | None = None
    outcomes: list[OutcomeInput] | None = Field(default=None, min_length=2)

    @field_validator("deadline")
    @classmethod
    def _deadline_future(cls, v: datetime | None) -> datetime | None:
        return _future_deadline(v)


class EventChildRead(BaseModel):
    """One child-market row of a house event (its YES leg + status)."""

    model_config = ConfigDict(from_attributes=True)

    market_id: UUID
    label: str
    slug: str
    status: str
    yes_outcome_id: UUID | None
    yes_price: DecimalStr


class EventCreatedResponse(BaseModel):
    """The created house event + its child outcome rows (money as JSON strings)."""

    id: UUID
    title: str
    slug: str
    category: str | None
    source: str
    deadline: datetime | None
    outcomes: list[EventChildRead]


class EventDetailResponse(BaseModel):
    """The edited house event + its child outcome rows (same shape as create)."""

    id: UUID
    title: str
    slug: str
    category: str | None
    source: str
    deadline: datetime | None
    outcomes: list[EventChildRead]
