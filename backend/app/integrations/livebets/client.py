"""LiveBetsClient — async HTTP client for the live-bets operator plane (v1.3, LB-A).

Follows ``app/integrations/polymarket/client.py``: a lazy ``httpx.AsyncClient``
singleton (``_get_client``), bounded ``httpx.Limits``, an ``httpx.Timeout``, and a
``tenacity`` retry on transient ``(httpx.NetworkError, httpx.TimeoutException)``
with ``reraise=True`` and a deliberate ``wait_exponential_jitter(initial=1, max=10,
jitter=2)`` backoff.

Retry is applied ONLY to the idempotent ``GET`` endpoints (``get_bet``,
``list_tables``). It is deliberately NOT applied to ``mint_session`` (``POST
/v2/sessions``): that endpoint is non-idempotent and live-bets does not document a
session Idempotency-Key, so a post-success timeout retried would mint duplicate
sessions (WR-04). A transient failure on ``mint_session`` surfaces to the caller.

Difference from the public Gamma client: live-bets is AUTHENTICATED. Every request
carries ``X-API-Key`` from ``settings.LIVEBETS_API_KEY`` (set as a default header on
the ``AsyncClient``). ``_get_client`` raises a clear ``RuntimeError`` if the key is
unset, so a misconfigured deployment fails loudly instead of sending an empty key.

Endpoints (verified against ``live-bets/docs/INTEGRATION-GUIDE.md`` §Step 2 + §Scopes):
  - ``POST /v2/sessions``        — mint a player session (no scope; operator key).
  - ``GET  /v2/bets/{id}``       — server-side verification source (scope ``bets:read``).
  - ``GET  /v2/catalog/tables``  — list tables (scope ``catalog:read``).

Cross-phase dependency (M1): sandbox keys are pre-scoped ``bets:place`` +
``catalog:read`` ONLY. The demo operator key MUST be issued WITH ``bets:read``
(provisioned in LB-C); without it live-bets returns ``403 SCOPE_MISMATCH`` and every
``get_bet`` verification fails. A ``403`` from ``get_bet`` / ``mint_session`` is
mapped to a clear configuration ``RuntimeError`` (need ``bets:read``), NOT a generic
500, so the operator knows exactly what to fix.

Never log the API key (CONVENTIONS §8 scrubber covers ``api_key``, but we also never
pass it into a log event).
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


def _raise_scope_or_status(exc: httpx.HTTPStatusError) -> None:
    """Map a live-bets ``403 SCOPE_MISMATCH`` to a clear config error, else re-raise.

    A ``403`` from the operator plane means the key lacks the scope the endpoint
    requires (for ``get_bet`` that is ``bets:read``, the cross-phase M1 dependency
    provisioned in LB-C). Surfacing it as a configuration ``RuntimeError`` — not a
    bare ``HTTPStatusError`` the router would turn into a 500 — tells the operator
    exactly what to fix.
    """
    if exc.response.status_code == 403:
        raise RuntimeError(
            "live-bets key missing required scope (need bets:read) — see LB-C"
        ) from exc
    raise exc


class LiveBetsClient:
    """Async client for the live-bets operator API with a lazy AsyncClient singleton."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """Create the ``httpx.AsyncClient`` if None or closed.

        Raises ``RuntimeError`` if ``LIVEBETS_API_KEY`` is unset — the operator
        plane requires auth, so a missing key is a hard configuration error rather
        than an empty header that live-bets would reject with a confusing 401.
        """
        if self._client is None or self._client.is_closed:
            settings = get_settings()
            if settings.LIVEBETS_API_KEY is None:
                raise RuntimeError("LIVEBETS_API_KEY is not configured")
            self._client = httpx.AsyncClient(
                base_url=settings.LIVEBETS_API_BASE,
                headers={"X-API-Key": settings.LIVEBETS_API_KEY},
                timeout=httpx.Timeout(15.0, connect=5.0),
                limits=httpx.Limits(
                    max_connections=10,
                    max_keepalive_connections=5,
                ),
            )
        return self._client

    # NO @retry here (WR-04): POST /v2/sessions is non-idempotent and live-bets does
    # not document a session Idempotency-Key (unlike POST /v2/bets). A post-success
    # timeout retried would mint DUPLICATE sessions. Retry stays only on the idempotent
    # GETs (get_bet / list_tables). A transient failure here surfaces to the caller.
    async def mint_session(
        self, player_ref: str, table_id: str, ttl_seconds: int | None = None
    ) -> dict[str, object]:
        """Mint a live-bets player session — ``POST /v2/sessions``.

        ``player_ref`` is the XPredict user id (opaque to live-bets, <=128 chars);
        ``table_id`` is a table from the operator catalog. ``ttl_seconds`` is omitted
        from the body when ``None`` (live-bets defaults to 3600). Returns the parsed
        JSON (``{session_token, expires_at}``).
        """
        client = self._get_client()
        body: dict[str, object] = {"player_ref": player_ref, "table_id": table_id}
        if ttl_seconds is not None:
            body["ttl_seconds"] = ttl_seconds
        resp = await client.post("/v2/sessions", json=body)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            _raise_scope_or_status(exc)
        result: dict[str, object] = resp.json()
        return result

    @retry(
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=10, jitter=2),
        reraise=True,
    )
    async def get_bet(self, bet_id: str) -> dict[str, object]:
        """Fetch a bet by id — ``GET /v2/bets/{bet_id}`` (scope ``bets:read``).

        This is the server-side verification source: ``LiveBetsBridge`` reads the
        authoritative ``status`` / ``stake`` / ``payout`` from here before posting
        any ledger move. A ``403`` is mapped to a clear scope-config ``RuntimeError``
        (need ``bets:read`` — the M1 cross-phase dependency).
        """
        client = self._get_client()
        resp = await client.get(f"/v2/bets/{bet_id}")
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            _raise_scope_or_status(exc)
        result: dict[str, object] = resp.json()
        return result

    @retry(
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=10, jitter=2),
        reraise=True,
    )
    async def list_tables(self) -> list[dict[str, object]]:
        """List operator catalog tables — ``GET /v2/catalog/tables`` (scope ``catalog:read``)."""
        client = self._get_client()
        resp = await client.get("/v2/catalog/tables")
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            _raise_scope_or_status(exc)
        result: list[dict[str, object]] = resp.json()
        return result

    async def close(self) -> None:
        """Close the underlying httpx client if open (mirrors GammaClient.close)."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
