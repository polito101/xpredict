"""Pydantic API schemas for the admin settlement surface (Phase 5, SC#5 + SC#8).

Both requests are ``extra="forbid"`` with a mandatory non-blank ``justification`` (SC#5
"mandatory justification", SC#8 "reversal requires a justification"). Money in the responses
serializes as JSON strings (``DecimalStr``), never floats (SC#4).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

DecimalStr = Annotated[
    Decimal,
    PlainSerializer(lambda v: str(v), return_type=str, when_used="json"),
]


class ResolveMarketRequest(BaseModel):
    """Body for ``POST /admin/markets/{market_id}/resolve`` — the confirmed resolution."""

    model_config = ConfigDict(extra="forbid")

    winning_outcome_id: UUID
    justification: str = Field(min_length=1, description="Mandatory resolution justification.")


class ResolveMarketResponse(BaseModel):
    """Summary of a resolution — money as JSON strings (SC#4)."""

    market_id: UUID
    winning_outcome_id: UUID
    bets_settled: int
    total_payout: DecimalStr
    total_loser_stake: DecimalStr


class ReverseSettlementRequest(BaseModel):
    """Body for ``POST /admin/markets/{market_id}/reverse``."""

    model_config = ConfigDict(extra="forbid")

    justification: str = Field(min_length=1, description="Mandatory reversal justification.")


class ReverseSettlementResponse(BaseModel):
    """Summary of a reversal."""

    market_id: UUID
    bets_reversed: int
