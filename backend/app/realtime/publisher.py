"""publish_odds_change — emit a lean odds-change delta to prices:{market_id}.

Called at the two producer sites (09-RESEARCH Pattern 3), ALWAYS post-commit
(Pitfall 3 / T-09-03) so clients never render a rolled-back price:

  1. Admin odds edit — ``app/markets/router.py::update_market`` after session.commit().
  2. Polymarket poll  — ``app/integrations/polymarket/tasks.py`` after the poll's
     session.commit(), per-market, only for markets whose sync committed.

The production payload is the lean delta the CONTEXT locked (Area 3):
``{type:"price_update", market_id, outcomes:[{outcome_id, odds}], ts}`` — odds are
strings (``str(Decimal)``; SP-1/SP-4), already-public data, NO PII (T-09-02). The
spike's dev-only ``_latency_ms``/``_server_ts`` forensic fields are never emitted.

This module uses the SYNC ``redis`` client — simplest for the request-context
admin-edit call. The poll path holds its own ``AioRedis`` and publishes the same
payload shape directly (RESEARCH Open Q2).
"""

from __future__ import annotations

import json
import time
from decimal import Decimal
from uuid import UUID

import redis
from redis.asyncio import Redis as AioRedis

from app.core.config import get_settings

# Odds column scale — Numeric(8,6) (app/db/types.py Odds). Delta odds are quantized
# to this scale so the WS string EXACTLY matches what GET /markets/{slug} emits via
# OutcomeRead (str(current_odds) after the DB round-trip), e.g. "0.700000". Without
# this, an in-memory Decimal("0.7") would serialize to "0.7" and the frontend would
# see a different string from the socket than from its SSR fetch (SP-1/SP-4).
_ODDS_QUANTUM = Decimal("0.000001")


def format_odds(value: Decimal) -> str:
    """Format an odds Decimal as the canonical Numeric(8,6) string (6 dp)."""
    return str(value.quantize(_ODDS_QUANTUM))


def build_price_update_payload(
    market_id: str | UUID, deltas: list[dict[str, str]]
) -> dict[str, object]:
    """Build the lean price_update payload shared by both producer sites.

    ``deltas`` is a list of ``{"outcome_id": str, "odds": str}`` dicts — the caller
    builds them from the committed outcomes (string odds), so the shape is identical
    whether published via the sync client here or the poll's async client.
    """
    return {
        "type": "price_update",
        "market_id": str(market_id),
        "outcomes": deltas,
        "ts": time.time(),
    }


def publish_odds_change(market_id: str | UUID, deltas: list[dict[str, str]]) -> None:
    """Publish a lean odds-change delta to ``prices:{market_id}`` (sync client).

    Used by the admin-edit producer site. A short-lived sync ``redis`` client keeps
    the request-context call simple; the connection is closed after publishing.
    """
    payload = build_price_update_payload(market_id, deltas)
    # redis.from_url (sync module fn) is untyped in the stubs — the async classmethod
    # used elsewhere is typed; this is the one place the sync client is constructed.
    client = redis.from_url(str(get_settings().REDIS_URL))  # type: ignore[no-untyped-call]
    try:
        client.publish(f"prices:{market_id}", json.dumps(payload))
    finally:
        client.close()


async def publish_odds_change_async(
    redis_client: AioRedis,
    market_id: str | UUID,
    deltas: list[dict[str, str]],
) -> None:
    """Publish a lean odds-change delta using an already-held async Redis client.

    Used by the Polymarket poll, which already holds an ``AioRedis`` for its SETNX
    lock (RESEARCH Open Q2) — reuse it rather than opening a second connection.
    Same payload shape as ``publish_odds_change``.
    """
    payload = build_price_update_payload(market_id, deltas)
    await redis_client.publish(f"prices:{market_id}", json.dumps(payload))
