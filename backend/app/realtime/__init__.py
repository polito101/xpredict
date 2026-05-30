"""Real-time WebSocket price broadcasting (MKT-04).

Lifts the VALIDATED spike 003 pipeline (FastAPI native WebSocket + redis.asyncio
pub/sub) into the app:

- ``manager``     — per-market ConnectionManager (set[WebSocket] + asyncio.Lock)
- ``subscriber``  — redis_subscriber background task: psubscribe('prices:*') → broadcast
- ``publisher``   — publish_odds_change(market_id, deltas): lean delta to prices:{id}
- ``router``      — public @websocket /ws/markets/{market_id}

The subscriber is started/cancelled in the app lifespan (app/main.py); producers
(admin odds edit, Polymarket poll) call ``publish_odds_change`` post-commit.
"""
