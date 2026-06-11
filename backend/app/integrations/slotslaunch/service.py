"""CasinoService — Redis-cached SlotsLaunch catalog fetch + normalization.

The single rule of this surface: it NEVER 500s the player. Every failure mode —
token unset, inactive subscription, network/timeout, non-200, garbage JSON — maps
to ``CasinoCatalog(status="inactive", games=[])`` (a friendly empty state), HTTP
200. The surface lights up with ZERO code changes the moment the subscription is
activated (the inactive branch is never cached, so the first active fetch after
activation populates the grid).

Caching (T-u0q-03, quota mitigation): the ACTIVE catalog is cached in Redis under
``casino:catalog`` for ``SLOTSLAUNCH_CACHE_TTL_SECONDS`` (12h) so repeat ``/casino``
loads do not re-hit the upstream quota. The inactive/error branch is deliberately
NOT cached. A cold/unavailable Redis degrades to an in-request live fetch (the cache
is a quota optimization, not a correctness dependency).

Token handling (T-u0q-01 / T-u0q-02): the raw token is read only via
``get_settings()`` and appears ONLY inside the composed ``iframe_url``
(``{SLOTSLAUNCH_API_BASE}/iframe/{id}?token=...``) — never as a standalone field,
never logged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from app.core.config import get_settings
from app.integrations.slotslaunch.schemas import CasinoCatalog, CasinoGame

if TYPE_CHECKING:  # pragma: no cover - typing only
    from redis.asyncio import Redis

    from app.integrations.slotslaunch.client import SlotsLaunchClient

log = structlog.get_logger()

_CACHE_KEY = "casino:catalog"

# The empty/degraded surface — reused for every inactive/failure path.
_INACTIVE = CasinoCatalog(status="inactive", games=[])


def _compose_iframe_url(api_base: str, token: str, game_id: str) -> str:
    """Compose the canonical SlotsLaunch iframe launch URL for one game.

    ``{api_base}/iframe/{game_id}?token={token}`` — the only place the token is
    embedded (SlotsLaunch's documented domain-bound model). Never logged.
    """
    return f"{api_base}/iframe/{game_id}?token={token}"


def _normalize(raw: dict[str, object], *, api_base: str, token: str) -> CasinoCatalog:
    """Map the upstream ``{"data": [...]}`` body into an active ``CasinoCatalog``.

    Each ``data`` item becomes a ``CasinoGame`` with a backend-composed
    ``iframe_url``. A missing/garbage ``data`` (no list) yields an empty active
    catalog; the caller has already excluded the inactive ``error`` branch. Any
    per-item parse problem propagates to the caller's broad except (graceful
    inactive) — a demo surface never 500s on malformed upstream JSON (T-u0q-05).
    """
    data = raw.get("data")
    games: list[CasinoGame] = []
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            game_id = str(item["id"])
            games.append(
                CasinoGame(
                    id=game_id,
                    name=str(item.get("name") or ""),
                    provider=(str(item["provider"]) if item.get("provider") else None),
                    thumb=(str(item["thumb"]) if item.get("thumb") else None),
                    iframe_url=_compose_iframe_url(api_base, token, game_id),
                )
            )
    return CasinoCatalog(status="active", games=games)


async def _read_cache(redis: Redis) -> CasinoCatalog | None:
    """Return the cached active catalog, or ``None`` on miss / unavailable Redis."""
    try:
        cached = await redis.get(_CACHE_KEY)
    except Exception:
        return None
    if not cached:
        return None
    try:
        return CasinoCatalog.model_validate_json(cached)
    except Exception:
        return None


async def _write_cache(redis: Redis, catalog: CasinoCatalog, ttl: int) -> None:
    """Best-effort SET of the active catalog with a TTL; swallow Redis errors."""
    try:
        await redis.set(_CACHE_KEY, catalog.model_dump_json(), ex=ttl)
    except Exception:
        return


async def get_catalog(redis: Redis, client: SlotsLaunchClient) -> CasinoCatalog:
    """Return the casino catalog — Redis-cached active games, or a graceful inactive.

    Flow:
      1. Token unset -> inactive (never calls upstream).
      2. Redis hit -> return the cached active catalog (no upstream call).
      3. Miss -> fetch upstream. ``{"error": ...}`` body -> inactive (NOT cached, so
         it lights up immediately on activation). Otherwise normalize to active, cache
         it (TTL), and return.
      4. ANY exception (network, timeout, non-200, KeyError, JSON) -> inactive.
    """
    settings = get_settings()
    token = settings.SLOTSLAUNCH_TOKEN
    if not token:
        return _INACTIVE

    cached = await _read_cache(redis)
    if cached is not None:
        return cached

    try:
        raw = await client.fetch_games()
        if not isinstance(raw, dict) or "error" in raw:
            # Inactive subscription (or unexpected non-dict) -> graceful empty, NOT
            # cached so activation lights the grid up on the very next load.
            log.info("slotslaunch.catalog_inactive")
            return _INACTIVE
        catalog = _normalize(raw, api_base=settings.SLOTSLAUNCH_API_BASE, token=token)
        await _write_cache(redis, catalog, settings.SLOTSLAUNCH_CACHE_TTL_SECONDS)
        return catalog
    except Exception:
        log.warning("slotslaunch.catalog_fetch_failed")
        return _INACTIVE
