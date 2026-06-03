"""Bloque 4 (Fase B seed harness): demo bet specs (pure builder).

Bets are spread deterministically across users and markets, ALWAYS spanning both
YES and NO on every market so a resolved market produces both winners and losers
(non-trivial settled P&L in the portfolio). Stakes are Decimal-from-string and
small relative to the funded balance so no placement overdraws.

The DB-touching ``seed_bets`` (via BetService.place_bet) is covered in
``test_seed_bets_db.py``.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from bin.seed_demo import SeedConfig, build_bet_specs

pytestmark = pytest.mark.unit


def test_build_bet_specs_deterministic_spans_both_sides() -> None:
    """Specs are deterministic; every market carries at least one YES and one NO."""
    cfg = SeedConfig(n_users=4, n_markets=3, n_resolved_markets=2)

    specs = build_bet_specs(cfg)
    assert build_bet_specs(cfg) == specs  # deterministic
    assert len(specs) > 0

    for j in range(cfg.n_markets):
        sides = {s.side for s in specs if s.market_index == j}
        assert sides == {"YES", "NO"}, f"market {j} missing a side: {sides}"

    for s in specs:
        assert s.stake > Decimal("0")
        assert 0 <= s.user_index < cfg.n_users
        assert 0 <= s.market_index < cfg.n_markets
        assert s.side in ("YES", "NO")
