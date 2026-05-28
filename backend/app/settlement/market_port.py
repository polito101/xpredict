"""The market-domain WRITE port settlement consumes from Phase 4 — the resolution seam.

Mirrors ``app/bets/market_port.py`` (the read port) for the resolution direction: the
``SettlementService`` marks a market RESOLVED through this narrow Protocol, NOT Phase 4's
concrete ``app/markets`` service (Pol owns that). Unlike the read port, ``mark_resolved``
takes the settlement ``AsyncSession`` so the market-status flip lands in the SAME ACID
transaction as the ledger postings (SC#5 — resolve is all-or-nothing).

During parallel development a fake satisfies it; at integration Phase 4's service implements
it structurally (``@runtime_checkable`` makes conformance testable), executing the markets
UPDATE on the supplied session.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable
from uuid import UUID

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@runtime_checkable
class MarketResolvePort(Protocol):
    """The write contract settlement needs from the market domain (Phase 4 satisfies it)."""

    async def mark_resolved(
        self, session: AsyncSession, *, market_id: UUID, winning_outcome_id: UUID
    ) -> None:
        """Mark ``market_id`` RESOLVED with ``winning_outcome_id`` on the given session.

        Called INSIDE the settlement transaction so the status change commits atomically
        with the payouts. Implementations MUST use ``session`` (not their own) and MUST NOT
        commit — the caller owns the unit of work.
        """
        ...

    async def mark_unresolved(self, session: AsyncSession, *, market_id: UUID) -> None:
        """Revert ``market_id``'s resolution (the inverse of :meth:`mark_resolved`).

        Called INSIDE a reversal transaction (SC#8) so the market returns to a re-resolvable
        state (e.g. RESOLVED -> CLOSED, clearing ``resolved_at`` / ``settled_at``) atomically
        with the compensating ledger entries. Same session, no commit.
        """
        ...
