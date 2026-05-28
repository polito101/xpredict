"""Tests for GammaMarket Pydantic v2 parser — state machine + Decimal handling.

Verifies all 4 VCR fixture types map to correct MarketStatus and that
stringified JSON fields are decoded properly. The closed-vs-resolved
safety test is the CRITICAL correctness gate for Phase 6.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.integrations.polymarket.schemas import GammaMarket
from app.markets.enums import MarketStatus

pytestmark = [pytest.mark.unit]


class TestGammaMarketParser:
    """Tests for GammaMarket parsing from VCR fixture data."""

    def test_active_market(self, gamma_active: dict) -> None:
        """Active market with no UMA process -> OPEN."""
        market = GammaMarket.model_validate(gamma_active)
        assert market.internal_status == MarketStatus.OPEN
        assert isinstance(market.volume, Decimal)
        assert len(market.outcomes_raw) == 2

    def test_closed_not_resolved(self, gamma_closed_not_resolved: dict) -> None:
        """CRITICAL: closed=true + umaResolutionStatus=proposed -> CLOSED (not RESOLVED).

        This is the single most dangerous pitfall in Polymarket integration.
        Settling on proposed status would pay out based on unconfirmed resolution.
        """
        market = GammaMarket.model_validate(gamma_closed_not_resolved)
        assert market.internal_status == MarketStatus.CLOSED
        assert market.internal_status != MarketStatus.RESOLVED

    def test_disputed_market(self, gamma_disputed: dict) -> None:
        """Active market under UMA dispute -> OPEN (still trading)."""
        market = GammaMarket.model_validate(gamma_disputed)
        assert market.internal_status == MarketStatus.OPEN

    def test_resolved_market(self, gamma_resolved: dict) -> None:
        """closed=true + umaResolutionStatus=resolved + clear winner -> RESOLVED."""
        market = GammaMarket.model_validate(gamma_resolved)
        assert market.internal_status == MarketStatus.RESOLVED

    def test_stringified_json_parsing(self) -> None:
        """Stringified JSON string for outcomes field parses to list."""
        raw = {
            "id": "test-1",
            "question": "Test?",
            "outcomes": '["Yes","No"]',
            "outcomePrices": '["0.5","0.5"]',
            "clobTokenIds": '["111","222"]',
            "volume": "1000",
        }
        market = GammaMarket.model_validate(raw)
        assert market.outcomes_raw == ["Yes", "No"]
        assert market.outcome_prices_raw == ["0.5", "0.5"]
        assert market.clob_token_ids == ["111", "222"]

    def test_decimal_volume_not_float(self, gamma_active: dict) -> None:
        """Volume MUST be Decimal, never float."""
        market = GammaMarket.model_validate(gamma_active)
        assert isinstance(market.volume, Decimal)
        assert isinstance(market.liquidity, Decimal)
        assert isinstance(market.volume_24hr_decimal, Decimal)

    def test_missing_uma_status(self) -> None:
        """Missing umaResolutionStatus key -> None, status OPEN."""
        raw = {
            "id": "test-2",
            "question": "No UMA?",
        }
        market = GammaMarket.model_validate(raw)
        assert market.uma_resolution_status is None
        assert market.internal_status == MarketStatus.OPEN
