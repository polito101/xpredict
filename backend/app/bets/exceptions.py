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


class StakeOutOfRange(BetError):
    """The stake is outside the effective [min, max] range for this market (BET-06).

    The effective bounds prefer the per-market ``min_stake`` / ``max_stake`` (when set on
    the market) and fall back to the global ``BET_MIN_STAKE`` / ``BET_MAX_STAKE`` config.
    The router maps this to HTTP 422 with the message carried on the exception.
    """
