"""Pydantic API schemas for the bet surface (Phase 5, SC#2).

``PlaceBetRequest`` is ``extra="forbid"`` (no stray fields) with a server-validated
positive ``stake``. ``BetResponse`` serializes ``stake`` and ``odds_at_placement`` as JSON
STRINGS (``DecimalStr``), never floats — the same money/precision-as-string discipline as
``app/wallet/schemas.py`` (SC#4 / PITFALLS #4). ``odds_at_placement`` is a probability in
(0,1], not money, but the string contract is identical (no lossy JSON float).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

# Decimals serialize as JSON strings (never float). Pydantic v2 already does this for
# Decimal; the explicit serializer is the prescribed regression guard (mirrors MoneyStr).
DecimalStr = Annotated[
    Decimal,
    PlainSerializer(lambda v: str(v), return_type=str, when_used="json"),
]


class PlaceBetRequest(BaseModel):
    """Body for ``POST /bets`` — stake on one market outcome."""

    model_config = ConfigDict(extra="forbid")

    market_id: UUID
    outcome_id: UUID
    stake: Decimal = Field(gt=0, description="Stake amount (positive Decimal).")


class BetResponse(BaseModel):
    """A placed bet — ``stake`` + ``odds_at_placement`` as JSON strings (SC#4)."""

    bet_id: UUID
    market_id: UUID
    outcome_id: UUID
    stake: DecimalStr
    odds_at_placement: DecimalStr
    status: str


# --------------------------------------------------------------------------- #
# Portfolio read surface (SC#7 / BET-07) — open + settled positions with P&L.
# Built from app/bets/portfolio dataclasses (from_attributes); decimals as strings.
# --------------------------------------------------------------------------- #
class OpenPositionItem(BaseModel):
    """A pending bet — payout/P&L are POTENTIAL (if the outcome wins, at locked odds)."""

    model_config = ConfigDict(from_attributes=True)

    bet_id: UUID
    market_id: UUID
    outcome_id: UUID
    stake: DecimalStr
    odds_at_placement: DecimalStr
    potential_payout: DecimalStr
    potential_pnl: DecimalStr
    current_value: DecimalStr
    unrealized_pnl: DecimalStr
    priced: bool


class SettledPositionItem(BaseModel):
    """A resolved bet — payout/P&L are REALIZED (exactly what settlement posted)."""

    model_config = ConfigDict(from_attributes=True)

    bet_id: UUID
    market_id: UUID
    outcome_id: UUID
    stake: DecimalStr
    odds_at_placement: DecimalStr
    status: str
    won: bool
    payout: DecimalStr
    realized_pnl: DecimalStr
    exit_odds: DecimalStr | None = None


class PortfolioResponse(BaseModel):
    """The player's portfolio — open positions + settled positions (SC#7)."""

    open: list[OpenPositionItem]
    settled: list[SettledPositionItem]


class SellPositionResponse(BaseModel):
    """Result of closing (cashing out) a position — money/odds as JSON strings (SC#4)."""

    bet_id: UUID
    payout: DecimalStr
    pnl: DecimalStr
    exit_odds: DecimalStr
    new_balance: DecimalStr
