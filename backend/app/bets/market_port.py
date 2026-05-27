"""The market-domain port Phase 5 consumes from Phase 4 — the integration contract.

Phase 5 (bets + settlement) depends on Phase 4 (Markets Domain & HouseAdapter) ONLY
through this narrow, read-only Protocol — NOT through Phase 4's concrete models or
``app/integrations/market_source.py`` (Pol owns those). During parallel development a
test stub satisfies it; at integration Phase 4's models implement it structurally
(``@runtime_checkable`` makes conformance testable), and the FK from
``bets.market_id`` / ``bets.outcome_id`` to the real ``markets`` / ``outcomes`` tables
is added by the integration migration ``0005`` (off Phase 4's ``0004``).

Kept deliberately MINIMAL — only what bet placement consumes (read + validate). The
resolution/write surface is added alongside ``SettlementService``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

# Market lifecycle states Phase 5 reasons about (mirror Phase 4 ROADMAP SC#2/#5).
MARKET_OPEN = "OPEN"
MARKET_CLOSED = "CLOSED"
MARKET_RESOLVED = "RESOLVED"


@dataclass(frozen=True, slots=True)
class OutcomeView:
    """A read-only view of one market outcome (binary v1: YES / NO)."""

    id: UUID
    label: str


@dataclass(frozen=True, slots=True)
class MarketView:
    """A read-only snapshot of a market — the only market data bet placement needs."""

    id: UUID
    status: str  # MARKET_OPEN | MARKET_CLOSED | MARKET_RESOLVED
    deadline: datetime
    outcomes: tuple[OutcomeView, ...]

    def is_open(self, now: datetime) -> bool:
        """A market accepts bets only while ``OPEN`` and strictly before its deadline."""
        return self.status == MARKET_OPEN and now < self.deadline

    def outcome(self, outcome_id: UUID) -> OutcomeView | None:
        """Return the matching outcome, or ``None`` if it does not belong to this market."""
        return next((o for o in self.outcomes if o.id == outcome_id), None)


@runtime_checkable
class MarketReadPort(Protocol):
    """The read contract Phase 5 needs from the market domain (Phase 4 satisfies it)."""

    async def get_market(self, market_id: UUID) -> MarketView | None:
        """Return the market snapshot, or ``None`` if no such market exists."""
        ...
