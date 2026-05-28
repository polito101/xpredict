"""Polymarket integration — Gamma API client, parser, and adapter.

Registers PolymarketAdapter in the MarketSource REGISTRY at import time,
following the same pattern as HouseAdapter in market_source.py line 86.
"""

from app.integrations.market_source import register_source
from app.integrations.polymarket.adapter import PolymarketAdapter
from app.markets.enums import MarketSourceEnum

register_source(MarketSourceEnum.POLYMARKET, PolymarketAdapter())

__all__ = ["PolymarketAdapter"]
