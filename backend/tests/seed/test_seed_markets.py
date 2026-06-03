"""Bloque 2 (Fase B seed harness): demo market specs (pure builder).

House markets are the spine of the demo (home + market-detail + charts), so the
list must be DETERMINISTIC, every market valid for ``MarketCreate`` (odds strictly
in (0,1), a future deadline) and a fixed subset flagged for resolution in Bloque 5
(so the portfolio later shows settled positions with P&L).

The DB-touching ``seed_markets`` (admin + OPEN markets via MarketService) is
covered in ``test_seed_markets_db.py``.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from bin.seed_demo import SeedConfig, build_market_specs

pytestmark = pytest.mark.unit


def test_build_market_specs_deterministic_valid_and_split() -> None:
    """Specs are deterministic, MarketCreate-valid, and split open/to-resolve."""
    cfg = SeedConfig(n_markets=10, n_resolved_markets=3)

    specs = build_market_specs(cfg)
    # Deterministic: a second call yields identical specs (reproducible demo).
    assert build_market_specs(cfg) == specs

    assert len(specs) == 10
    # Unique questions (a believable home — no repeats at this size).
    assert len({s.question for s in specs}) == 10

    # Exactly n_resolved flagged with a winning side; the rest stay open-only.
    resolved = [s for s in specs if s.resolve_to is not None]
    assert len(resolved) == 3

    for s in specs:
        # MarketCreate constraints: odds strictly inside (0, 1), future deadline.
        assert Decimal("0") < s.initial_odds_yes < Decimal("1")
        assert s.deadline_offset_days > 0
        assert s.question and s.resolution_criteria and s.category
        if s.resolve_to is not None:
            assert s.resolve_to in ("YES", "NO")
