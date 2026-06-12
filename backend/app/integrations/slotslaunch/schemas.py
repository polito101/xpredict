"""Pydantic v2 schemas for the SlotsLaunch casino-demo proxy (quick task 260611-u0q).

Two outward models:
  - ``CasinoGame`` — one normalized demo-slot tile. ``iframe_url`` is the
    BACKEND-COMPOSED launch URL (``{SLOTSLAUNCH_API_BASE}/iframe/{id}?token=...``);
    the raw token is NEVER a standalone field — it appears only embedded inside
    ``iframe_url`` (SlotsLaunch's documented domain-bound model, accepted by design,
    T-u0q-02). The frontend env never carries the token.
  - ``CasinoCatalog`` — the ``GET /api/v1/casino/games`` response: a ``status``
    discriminator (``active`` | ``inactive``) plus the (possibly empty) game list.
    ``inactive`` carries ``games=[]`` and is the graceful degraded surface (the
    subscription is off, upstream failed, or the token is unset) — always HTTP 200.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class CasinoGame(BaseModel):
    """One normalized demo-slot tile surfaced to the frontend grid.

    ``iframe_url`` is the only field that carries the token (composed by the
    backend); ``id``/``name``/``provider``/``thumb`` are token-free.
    """

    id: str
    name: str
    provider: str | None = None
    thumb: str | None = None
    iframe_url: str


class CasinoCatalog(BaseModel):
    """The ``GET /api/v1/casino/games`` payload — status + (possibly empty) games."""

    status: Literal["active", "inactive"]
    games: list[CasinoGame]
