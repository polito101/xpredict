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
    _safe_decimal,
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


class TestSafeDecimalNonFinite:
    """Regression for 14-AUDIT C-1 — ``_safe_decimal`` rejects NaN / Infinity.

    BIDIRECTIONAL: these tests pass on the fixed ``is_finite()`` guard and FAIL if
    it is reverted. ``Decimal(str(float('nan')))`` builds ``Decimal('NaN')``
    WITHOUT raising, so without the guard ``_safe_decimal`` would return a NaN
    Decimal. The downstream volume floor then evaluates ``Decimal('NaN') >= floor``,
    which raises ``InvalidOperation`` — caught per-category and silently discarding
    a whole sync batch. Coercing non-finite to ``Decimal('0')`` floors it out
    cleanly instead (it falls below the $10k floor and is simply skipped).
    """

    def test_safe_decimal_nan_returns_zero(self) -> None:
        """``_safe_decimal(float('nan'))`` → ``Decimal('0')`` (not ``Decimal('NaN')``)."""
        result = _safe_decimal(float("nan"))
        assert result == Decimal("0")
        # Belt-and-suspenders: prove it is genuinely finite, not a NaN that happens
        # to compare-equal (it does NOT — a NaN compares unequal to everything).
        assert result.is_finite()

    def test_safe_decimal_positive_inf_returns_zero(self) -> None:
        """``_safe_decimal(float('inf'))`` → ``Decimal('0')`` (Infinity rejected)."""
        result = _safe_decimal(float("inf"))
        assert result == Decimal("0")
        assert result.is_finite()

    def test_safe_decimal_negative_inf_returns_zero(self) -> None:
        """``_safe_decimal(float('-inf'))`` → ``Decimal('0')`` (-Infinity rejected too)."""
        result = _safe_decimal(float("-inf"))
        assert result == Decimal("0")
        assert result.is_finite()

    def test_event_nan_volume_floors_out_without_raising(self) -> None:
        """A ``GammaEvent`` whose ``volume24hr`` is NaN yields ``Decimal('0')``.

        Reproduces the exact production shape: ``json`` parses a bare ``NaN`` token
        to ``float('nan')``, which flows into ``GammaEvent.volume_24hr`` (a raw
        ``float | None``). ``volume_24hr_decimal`` must coerce it to ``Decimal('0')``
        — and crucially the floor comparison ``>= Decimal('10000')`` must NOT raise.
        """
        ev = GammaEvent.model_validate(
            {"id": "nan-evt", "title": "NaN volume event", "volume24hr": float("nan")}
        )
        vol = ev.volume_24hr_decimal
        assert vol == Decimal("0")
        assert vol.is_finite()
        # The floor comparison that detonated pre-fix — must evaluate, never raise.
        assert (vol >= Decimal("10000")) is False


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

    def test_open_event_child_with_strike_price_stays_open(self) -> None:
        """spike-002 guard: an OPEN child with a "1" in outcomePrices stays OPEN, never RESOLVED.

        A strike price of exactly 1.0 (or 0.0) appears on perfectly OPEN markets —
        deep in-the-money but still trading. ``_derive_status`` only consults the
        winner check inside the ``closed=true & uma=resolved`` branch; an event with
        ``closed=false`` (uma=None) must short-circuit to OPEN regardless of any
        terminal-looking price. Mis-mapping this to RESOLVED would settle a live
        market on an unconfirmed price (the spike-002 correctness gate, event path).
        """
        ev = GammaEvent.model_validate(
            {
                "id": "open-strike-evt",
                "title": "Open event with a 1.0 strike child",
                "closed": False,
                "markets": [
                    {
                        "id": "open-strike-mkt",
                        "question": "Deep ITM but still open?",
                        "conditionId": "cond-open-strike",
                        "closed": False,
                        "outcomes": '["Yes","No"]',
                        "outcomePrices": '["1","0"]',  # terminal-looking, but OPEN
                        "clobTokenIds": '["s1","s2"]',
                        "groupItemTitle": "",
                    }
                ],
            }
        )
        child = ev.markets[0]
        assert child.internal_status == MarketStatus.OPEN
        assert child.internal_status != MarketStatus.RESOLVED
        # Sanity: the "1" really is present in the parsed prices (so the guard,
        # not a parse miss, is what kept it OPEN).
        assert "1" in child.outcome_prices_raw
