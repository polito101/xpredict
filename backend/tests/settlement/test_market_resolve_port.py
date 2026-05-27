"""MarketResolvePort contract (Phase 5 -> Phase 4 resolution seam).

Pure unit test (no DB): pins the narrow write contract settlement consumes from Phase 4.
A fake stands in during parallel development; at integration Phase 4's market service
implements it structurally (``@runtime_checkable`` makes conformance testable). Mirrors
``tests/bets/test_market_port.py`` for the read direction.
"""

from __future__ import annotations

from uuid import UUID

from app.settlement.market_port import MarketResolvePort


class _FakeResolver:
    """Minimal structural implementation of the resolve port."""

    async def mark_resolved(
        self, session, *, market_id: UUID, winning_outcome_id: UUID
    ) -> None:  # pragma: no cover - exercised in the integration suite
        return None


def test_fake_satisfies_market_resolve_port() -> None:
    """A type implementing ``mark_resolved`` structurally conforms to the runtime port."""
    assert isinstance(_FakeResolver(), MarketResolvePort)


def test_plain_object_does_not_satisfy_port() -> None:
    """An object without ``mark_resolved`` is NOT a MarketResolvePort."""
    assert not isinstance(object(), MarketResolvePort)
