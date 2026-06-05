"""Tests for GammaMarket Pydantic v2 parser — state machine + Decimal handling.

Verifies all 4 VCR fixture types map to correct MarketStatus and that
stringified JSON fields are decoded properly. The closed-vs-resolved
safety test is the CRITICAL correctness gate for Phase 6.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.config import get_settings
from app.integrations.polymarket.schemas import (
    GammaEvent,
    GammaEventMarket,
    GammaMarket,
    GammaTag,
    resolve_category,
)
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


class TestGammaEventParser:
    """Tests for GammaEvent / GammaEventMarket / GammaTag against live fixtures.

    Covers the two Phase-14 divergences from GammaMarket: event-level FLOAT
    volume -> Decimal, and the GammaEventMarket subclass inheriting the
    spike-002 status truth table + stringified-JSON validators verbatim while
    adding ``group_item_title``.
    """

    def test_gamma_event_multi_outcome(self, gamma_events_multi: list[dict]) -> None:
        """Grouped event: float volume -> Decimal, 3 children, labels + inherited status."""
        ev = GammaEvent.model_validate(gamma_events_multi[0])
        assert ev.id == "538337"
        assert len(ev.markets) == 3
        # Event-level volume24hr is a raw FLOAT in /events; proves float -> Decimal.
        assert isinstance(ev.volume_24hr_decimal, Decimal)
        assert ev.volume_24hr_decimal > 0
        assert isinstance(ev.volume_total_decimal, Decimal)
        # Subclass-only field (the per-outcome display label).
        assert ev.markets[0].group_item_title == "64,000"
        assert isinstance(ev.markets[0], GammaEventMarket)
        # Inherited _derive_status truth table (closed=false, uma=None -> OPEN).
        assert ev.markets[0].internal_status == MarketStatus.OPEN
        # Inherited stringified-JSON list validator.
        assert ev.markets[0].outcomes_raw == ["Yes", "No"]

    def test_gamma_event_single_market_stays_standalone(
        self, gamma_events_single: list[dict]
    ) -> None:
        """A len==1 event parses with an empty group_item_title (EVT-07 standalone)."""
        ev = GammaEvent.model_validate(gamma_events_single[0])
        assert len(ev.markets) == 1
        assert ev.markets[0].group_item_title == ""

    def test_category_first_by_priority(self, gamma_events_single: list[dict]) -> None:
        """Dual-tagged (World 101970 + Politics 2) event resolves to Politics (higher priority)."""
        ev = GammaEvent.model_validate(gamma_events_single[0])
        assert resolve_category(ev, get_settings().POLYMARKET_CATEGORIES) == "Politics"

    def test_resolve_category_none_when_unmapped(self) -> None:
        """An event with no allow-listed tag resolves to None (caller skips it)."""
        ev = GammaEvent.model_validate(
            {"id": "x1", "tags": [{"id": "999999", "label": "Niche", "slug": "niche"}]}
        )
        assert resolve_category(ev, get_settings().POLYMARKET_CATEGORIES) is None

    def test_gamma_tag_parses(self, gamma_tags_categories: list[dict]) -> None:
        """A GammaTag parses id/label/slug from a /tags element."""
        tag = GammaTag.model_validate(gamma_tags_categories[0])
        assert tag.id == "2"
        assert tag.label == "Politics"
        assert tag.slug == "politics"
