"""Phase 4 -> Phase 5 market RESOLVE adapter (integration).

Implements the settlement :class:`~app.settlement.market_port.MarketResolvePort` over Phase 4's
``app/markets`` domain. Uses the SETTLEMENT session (passed in) so the market-status flip commits
ATOMICALLY with the ledger postings + the audit row (SC#5 — resolution is all-or-nothing).
Phase 4 has no resolve method (resolution is Phase 5's responsibility), so this writes the status
transition directly on the ``Market`` row, mirroring ``MarketService.close_market``:

  - ``mark_resolved``   : status -> RESOLVED, ``resolved_at`` = now.
  - ``mark_unresolved`` : status -> CLOSED, ``resolved_at`` = None (re-resolvable after a reversal).

Wired into the settlement admin router's ``get_market_resolver`` at integration so
``POST /admin/markets/{id}/resolve`` (and ``/reverse``) stop returning 503.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from app.markets.enums import MarketStatus
from app.markets.models import Market


class HouseMarketResolveAdapter:
    """Satisfies ``MarketResolvePort`` using Phase 4's market domain (caller-session writes)."""

    async def mark_resolved(
        self, session: AsyncSession, *, market_id: UUID, winning_outcome_id: UUID
    ) -> None:
        market = await session.get(Market, market_id)
        if market is None:
            raise NoResultFound(f"no market {market_id}")
        market.status = MarketStatus.RESOLVED.value
        market.resolved_at = datetime.now(UTC)

    async def mark_unresolved(self, session: AsyncSession, *, market_id: UUID) -> None:
        market = await session.get(Market, market_id)
        if market is None:
            raise NoResultFound(f"no market {market_id}")
        market.status = MarketStatus.CLOSED.value
        market.resolved_at = None
