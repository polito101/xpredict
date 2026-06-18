"""Phase 4 -> Phase 5 market RESOLVE adapter (integration).

Implements the settlement :class:`~app.settlement.market_port.MarketResolvePort` over Phase 4's
``app/markets`` domain. Uses the SETTLEMENT session (passed in) so the market-status flip commits
ATOMICALLY with the ledger postings + the audit row (SC#5 — resolution is all-or-nothing).
Phase 4 has no resolve method (resolution is Phase 5's responsibility), so this writes the status
transition directly on the ``Market`` row, mirroring ``MarketService.close_market``:

  - ``mark_resolved``   : status -> RESOLVED, ``resolved_at`` = now, and persists
    ``winning_outcome_id`` / ``resolution_source`` / ``resolution_justification`` (STL-06).
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
        self,
        session: AsyncSession,
        *,
        market_id: UUID,
        winning_outcome_id: UUID,
        resolution_source: str,
        justification: str,
    ) -> None:
        market = await session.get(Market, market_id)
        if market is None:
            raise NoResultFound(f"no market {market_id}")
        # Defensive status precondition. This row has no resolve guard of its own and
        # SettlementService calls mark_resolved OUTSIDE its `if bets:` block, so the status
        # flip lands even when no money moves:
        #   - CANCELLED: a voided market must NEVER be force-RESOLVED — that forces win/loss
        #     payouts on a voided event. No production path resolves a CANCELLED market today
        #     (the enum has no writer); if a future cancel feature reaches here it is a bug,
        #     and it still needs a stake-REFUND path the ledger lacks (event_service.void_event).
        #   - RESOLVED: tolerate idempotently. Re-resolve is the EVA-03 replay canary; the
        #     bet-status PENDING filter is the ledger-side guard, so SKIP (don't re-stamp the
        #     winner / resolved_at) instead of raising — raising would fail every child of an
        #     idempotent resolve_event replay.
        if market.status == MarketStatus.CANCELLED.value:
            raise ValueError(f"cannot resolve CANCELLED market {market_id}")
        if market.status == MarketStatus.RESOLVED.value:
            return
        market.status = MarketStatus.RESOLVED.value
        market.resolved_at = datetime.now(UTC)
        # STL-06: persist the winner + source + justification on the SAME session so they
        # commit atomically with the payouts (no separate commit — caller owns the tx).
        market.winning_outcome_id = winning_outcome_id
        market.resolution_source = resolution_source
        market.resolution_justification = justification

    async def mark_unresolved(self, session: AsyncSession, *, market_id: UUID) -> None:
        market = await session.get(Market, market_id)
        if market is None:
            raise NoResultFound(f"no market {market_id}")
        market.status = MarketStatus.CLOSED.value
        market.resolved_at = None
