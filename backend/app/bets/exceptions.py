"""Bet domain exceptions (Phase 5). Mirrors ``app/wallet/exceptions.py`` — domain
errors a caller (API layer, later) maps to 4xx, never raw 500s.
"""

from __future__ import annotations


class BetError(Exception):
    """Base class for bet-placement domain errors."""


class MarketNotFound(BetError):
    """No market exists for the given id (via the market port)."""


class MarketClosed(BetError):
    """The market is not OPEN, or its deadline has passed — bets are not accepted."""


class InvalidOutcome(BetError):
    """The chosen outcome does not belong to the market."""
