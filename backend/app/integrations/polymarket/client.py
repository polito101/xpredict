"""GammaClient — async HTTP client for the Polymarket Gamma API.

Wraps ``httpx.AsyncClient`` with lazy singleton pattern and ``tenacity``
retry on transient errors (network, timeout). Connection pool is bounded
to prevent resource exhaustion (T-06-02).

No auth required — Gamma API is public. Rate limit is 300 req/10s
(verified: docs.polymarket.com); our top-25 poll fires ~2 req/min.
"""

from __future__ import annotations

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.core.config import get_settings

log = structlog.get_logger()


class GammaClient:
    """Async client for Gamma API with lazy httpx.AsyncClient singleton."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """Create httpx.AsyncClient if None or closed."""
        if self._client is None or self._client.is_closed:
            settings = get_settings()
            self._client = httpx.AsyncClient(
                base_url=settings.GAMMA_API_BASE_URL,
                timeout=httpx.Timeout(15.0, connect=5.0),
                limits=httpx.Limits(
                    max_connections=10,
                    max_keepalive_connections=5,
                ),
            )
        return self._client

    @retry(
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=10, jitter=2),
        reraise=True,
    )
    async def fetch_top_markets(self, limit: int = 25) -> list[dict[str, object]]:
        """Fetch top markets by 24h volume from Gamma API.

        Single batch call (not per-market) — MKT-05 rate-limit compliance.
        """
        client = self._get_client()
        resp = await client.get(
            "/markets",
            params={
                "active": "true",
                "closed": "false",
                "order": "volume24hr",
                "limit": str(limit),
            },
        )
        resp.raise_for_status()
        data: list[dict[str, object]] = resp.json()
        log.info(
            "gamma.fetch_top_markets",
            market_count=len(data) if isinstance(data, list) else 0,
            limit=limit,
        )
        return data

    @retry(
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=10, jitter=2),
        reraise=True,
    )
    async def fetch_market_by_id(self, market_id: str) -> dict[str, object] | None:
        """Fetch a single market by Gamma ID. Returns None on 404."""
        client = self._get_client()
        resp = await client.get(f"/markets/{market_id}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        result: dict[str, object] = resp.json()
        return result

    async def close(self) -> None:
        """Close the underlying httpx client if open."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
