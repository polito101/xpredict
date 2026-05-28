"""
Spike 002: polymarket-gamma-parser

Pydantic v2 parser for Polymarket Gamma API /markets responses.
Handles: string-encoded decimals, mixed numeric types, optional fields,
and the umaResolutionStatus state machine.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator


class InternalMarketStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    PROPOSED = "PROPOSED"
    DISPUTED = "DISPUTED"
    RESOLVED = "RESOLVED"


class GammaOutcome(BaseModel):
    label: str
    price: Decimal
    clob_token_id: str


class GammaMarket(BaseModel):
    """
    Parses a single market from the Gamma API response.

    Design decisions:
    - extra='allow' in production (log unknown fields for schema drift detection)
    - All money/volume fields normalized to Decimal from strings
    - umaResolutionStatus is optional (absent when no UMA process)
    - Internal status derived from closed + umaResolutionStatus state machine
    """

    model_config = {"extra": "allow"}

    id: str
    question: str
    slug: str = ""
    condition_id: str = Field(alias="conditionId", default="")
    description: str = ""

    outcomes_raw: list[str] = Field(alias="outcomes", default_factory=list)
    outcome_prices_raw: list[str] = Field(alias="outcomePrices", default_factory=list)
    clob_token_ids: list[str] = Field(alias="clobTokenIds", default_factory=list)

    volume_str: str = Field(alias="volume", default="0")
    liquidity_str: str = Field(alias="liquidity", default="0")
    volume_24hr: float | None = Field(alias="volume24hr", default=None)

    end_date: datetime | None = Field(alias="endDate", default=None)
    end_date_iso: str | None = Field(alias="endDateIso", default=None)

    active: bool = False
    closed: bool = False
    accepting_orders: bool = Field(alias="acceptingOrders", default=False)
    automatically_resolved: bool = Field(alias="automaticallyResolved", default=False)

    uma_resolution_status: str | None = Field(alias="umaResolutionStatus", default=None)
    uma_resolution_statuses: list[str] = Field(alias="umaResolutionStatuses", default_factory=list)
    uma_bond: str | None = Field(alias="umaBond", default=None)

    @field_validator(
        "outcomes_raw", "outcome_prices_raw", "clob_token_ids", "uma_resolution_statuses",
        mode="before",
    )
    @classmethod
    def parse_stringified_json_list(cls, v: str | list | None) -> list:
        """Handle Gamma API's stringified JSON arrays: '["Yes","No"]' -> ["Yes","No"]."""
        if v is None:
            return []
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass
            return []
        return []

    resolution_source: str = Field(alias="resolutionSource", default="")
    resolved_by: str = Field(alias="resolvedBy", default="")

    # Derived fields (computed after validation)
    volume: Decimal = Decimal("0")
    liquidity: Decimal = Decimal("0")
    parsed_outcomes: list[GammaOutcome] = Field(default_factory=list)
    internal_status: InternalMarketStatus = InternalMarketStatus.OPEN

    @field_validator("volume_str", "liquidity_str", mode="before")
    @classmethod
    def coerce_numeric_string(cls, v: str | int | float | None) -> str:
        if v is None:
            return "0"
        return str(v)

    @model_validator(mode="after")
    def compute_derived(self) -> GammaMarket:
        self.volume = _safe_decimal(self.volume_str)
        self.liquidity = _safe_decimal(self.liquidity_str)

        outcomes = self.outcomes_raw or []
        prices = self.outcome_prices_raw or []
        tokens = self.clob_token_ids or []

        self.parsed_outcomes = []
        for i, label in enumerate(outcomes):
            price = _safe_decimal(prices[i]) if i < len(prices) else Decimal("0")
            token = tokens[i] if i < len(tokens) else ""
            self.parsed_outcomes.append(GammaOutcome(label=label, price=price, clob_token_id=token))

        self.internal_status = _derive_status(
            closed=self.closed,
            uma_status=self.uma_resolution_status,
            outcome_prices=prices,
        )
        return self

    def is_safe_to_settle(self) -> bool:
        return self.internal_status == InternalMarketStatus.RESOLVED

    def winning_outcome(self) -> str | None:
        if self.internal_status != InternalMarketStatus.RESOLVED:
            return None
        for o in self.parsed_outcomes:
            if o.price == Decimal("1"):
                return o.label
        return None


def _safe_decimal(value: str | int | float | None) -> Decimal:
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return Decimal("0")


def _derive_status(
    closed: bool,
    uma_status: str | None,
    outcome_prices: list[str],
) -> InternalMarketStatus:
    """
    State machine for determining internal market status.

    CRITICAL: closed=true does NOT mean resolved.
    Only uma_resolution_status="resolved" means resolved.
    """
    if not closed and uma_status is None:
        return InternalMarketStatus.OPEN

    if not closed and uma_status == "proposed":
        return InternalMarketStatus.PROPOSED

    if not closed and uma_status == "disputed":
        return InternalMarketStatus.DISPUTED

    if closed and uma_status == "resolved":
        has_winner = any(p in ("0", "1", "0.0", "1.0") for p in outcome_prices)
        if has_winner:
            return InternalMarketStatus.RESOLVED
        return InternalMarketStatus.CLOSED

    if closed and uma_status in ("proposed", "disputed", None):
        return InternalMarketStatus.CLOSED

    if not closed and uma_status == "resolved":
        return InternalMarketStatus.RESOLVED

    return InternalMarketStatus.OPEN
