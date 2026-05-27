from __future__ import annotations

import enum


class MarketStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    RESOLVED = "RESOLVED"
    CANCELLED = "CANCELLED"


class MarketSourceEnum(str, enum.Enum):
    HOUSE = "HOUSE"
    POLYMARKET = "POLYMARKET"
