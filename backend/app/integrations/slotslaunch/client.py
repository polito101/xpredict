"""SlotsLaunchClient — async HTTP client for the SlotsLaunch demo-slots API.

Follows ``app/integrations/polymarket/client.py``: a lazy ``httpx.AsyncClient``
singleton (``_get_client``), bounded ``httpx.Limits``, an ``httpx.Timeout(15.0,
connect=5.0)``, and a ``tenacity`` retry on transient ``(httpx.NetworkError,
httpx.TimeoutException)`` with ``reraise=True``.

The catalog endpoint is ``GET {SLOTSLAUNCH_API_BASE}/api/games``. The token is
DOMAIN-BOUND: every call MUST carry the ``Origin: {SLOTSLAUNCH_ORIGIN}`` header
(SlotsLaunch validates the token against that domain). The token is passed as a
``token`` query param.

INACTIVE-SUBSCRIPTION CONTRACT: while the subscription is not active, the upstream
returns HTTP 200 with a body ``{"error": "Your Slots Launch subscription is not
active"}``. ``fetch_games`` deliberately does NOT raise on this body — it returns
the parsed dict AS-IS so the service can branch on the ``error`` key and degrade to
a graceful inactive surface (a demo surface must never 500). Only non-200 HTTP
status codes raise (via ``raise_for_status``), which the service also catches.

Never log the token (the structlog scrubber covers token-like keys, but this client
also never passes it into a log event).
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


class SlotsLaunchClient:
    """Async client for the SlotsLaunch API with a lazy AsyncClient singleton."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """Create the ``httpx.AsyncClient`` if None or closed.

        The ``Origin`` header is set as a default header on the client — the token
        is domain-bound to ``SLOTSLAUNCH_ORIGIN`` and SlotsLaunch rejects calls that
        omit it. The token itself is sent per-request as a query param (never logged).
        """
        if self._client is None or self._client.is_closed:
            settings = get_settings()
            self._client = httpx.AsyncClient(
                base_url=settings.SLOTSLAUNCH_API_BASE,
                headers={"Origin": settings.SLOTSLAUNCH_ORIGIN},
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
    async def fetch_games(self, per_page: int = 150) -> dict[str, object]:
        """Fetch the demo-slots catalog — ``GET /api/games``.

        ``per_page`` is the page size (SlotsLaunch caps it at 150). The token is
        passed as the ``token`` query param; the ``Origin`` header (set on the
        client) carries the domain binding.

        Returns the parsed JSON dict. Does NOT raise on the inactive-subscription
        200 body ``{"error": ...}`` — that is returned as-is so the service branches
        on the ``error`` key. Only a non-200 HTTP status raises (``raise_for_status``).
        Never logs the token.
        """
        settings = get_settings()
        client = self._get_client()
        resp = await client.get(
            "/api/games",
            params={"token": settings.SLOTSLAUNCH_TOKEN, "per_page": str(per_page)},
        )
        resp.raise_for_status()
        result: dict[str, object] = resp.json()
        # Deliberately do NOT inspect/branch here — the service decides active vs
        # inactive on the `error` key. Log only the shape (count), never the token.
        data = result.get("data")
        log.info(
            "slotslaunch.fetch_games",
            game_count=len(data) if isinstance(data, list) else 0,
            inactive="error" in result,
        )
        return result

    async def close(self) -> None:
        """Close the underlying httpx client if open (mirrors GammaClient.close)."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
