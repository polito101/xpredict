"""Phase 4 -> Phase 5 market READ adapter (integration).

Implements the bets :class:`~app.bets.market_port.MarketReadPort` over Phase 4's ``app/markets``
domain. Reads on its OWN session (a fresh ``_get_session_maker()`` session), NOT the caller's:
``BetService.place_bet`` calls ``get_market`` BEFORE its ``session.begin()``, and a read on the
request session would autobegin a transaction and make ``begin()`` raise (the documented port
contract). Maps ``Market`` -> ``MarketView`` and exposes each ``Outcome.current_odds`` as the
``price`` (verified to be a probability in (0,1] — no ``1/odds`` conversion). Wired into the bet
router's ``get_market_source`` at integration so ``POST /bets`` stops returning 503.
"""

from __future__ import annotations

from uuid import UUID

from app.bets.market_port import MarketView, OutcomeView
from app.db.session import _get_session_maker
from app.markets.service import MarketService


class HouseMarketReadAdapter:
    """Satisfies ``MarketReadPort`` using Phase 4's ``MarketService`` (own-session reads)."""

    async def get_market(self, market_id: UUID) -> MarketView | None:
        sm = _get_session_maker()
        async with sm() as session:
            market = await MarketService.get_market_by_id(session, market_id)
            if market is None:
                return None
            # Build the plain (frozen) DTO INSIDE the session scope — outcomes are
            # eager-loaded by get_market_by_id (Market.outcomes is lazy="raise").
            return MarketView(
                id=market.id,
                status=market.status,
                deadline=market.deadline,
                outcomes=tuple(
                    OutcomeView(id=o.id, label=o.label, price=o.current_odds)
                    for o in market.outcomes
                ),
                # BET-06: carry the per-market stake limits (added by 12-01). They are
                # eager-available on the loaded Market row; NULL => global fallback.
                min_stake=market.min_stake,
                max_stake=market.max_stake,
            )
