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
