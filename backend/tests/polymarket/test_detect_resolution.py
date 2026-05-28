"""Phase 7 — STL-01: Polymarket auto-resolution Beat task tests.

These stubs are Wave 0 scaffolds; the real implementations are filled by Plan 07-02.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.skip(reason="Wave 0 scaffold — filled by Plan 07-02")
def test_candidate_query_returns_expired_markets() -> None:
    """Candidate query returns only POLYMARKET OPEN/CLOSED markets whose deadline has passed."""


@pytest.mark.skip(reason="Wave 0 scaffold — filled by Plan 07-02")
def test_grace_period_triggers_resolution() -> None:
    """First tick sets uma_resolved_at; second tick (past grace window) calls resolve_market."""


@pytest.mark.skip(reason="Wave 0 scaffold — filled by Plan 07-02")
def test_closed_proposed_not_settled() -> None:
    """A market with closed=true and umaResolutionStatus='proposed' is never auto-settled (SC#3)."""


@pytest.mark.skip(reason="Wave 0 scaffold — filled by Plan 07-02")
def test_integration_proposed_not_settled() -> None:
    """Integration: closed/proposed market reaches task, bets remain PENDING (SC#3)."""


@pytest.mark.skip(reason="Wave 0 scaffold — filled by Plan 07-02")
def test_reversal_after_auto_settlement() -> None:
    """Auto-settle then reverse; compensating entries restore balances (SC#6)."""
