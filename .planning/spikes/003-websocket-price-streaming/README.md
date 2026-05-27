---
spike: 003
name: websocket-price-streaming
type: standard
validates: "Given a FastAPI WebSocket endpoint broadcasting odds changes, when a Celery task publishes a price update via Redis pub/sub, then a Next.js client receives the update in <2s with auto-reconnect on disconnect"
verdict: VALIDATED
related: [001-async-wallet-concurrency]
tags: [fastapi, websocket, redis, pubsub, nextjs, real-time]
---

# Spike 003: WebSocket Price Streaming

## What This Validates
Given a FastAPI WebSocket endpoint broadcasting odds changes via Redis pub/sub,
when a Celery task publishes a price update,
then a client receives the update in <2s with auto-reconnect on disconnect.

## Research

| Approach | Tool/Library | Pros | Cons | Status |
|----------|-------------|------|------|--------|
| FastAPI native WS + `redis.asyncio` pub/sub | Built-in | Zero new deps, full control, async native | Manual connection management | **Chosen** |
| `broadcaster` library | broadcaster | Abstracts pub/sub backend | Extra dep, stale maintenance | Skip |
| `fastapi-websocket-pubsub` | fastapi-websocket-pubsub | Structured protocol | Overkill, opinionated | Skip |
| SSE (Server-Sent Events) | Built-in | Simpler, HTTP-based | Unidirectional, no binary, worse reconnect | Backup |

**Chosen approach:** FastAPI native WebSocket + `redis.asyncio` pub/sub. Zero new deps needed (project already has `redis>=5.0` which includes `redis.asyncio`). Full control over connection lifecycle, backpressure handling, and per-market routing.

## How to Run

```bash
# Terminal 1: Start server
cd backend && uv run python ../.planning/spikes/003-websocket-price-streaming/spike_ws_server.py

# Terminal 2: Start publisher (simulates Celery task)
cd backend && uv run python ../.planning/spikes/003-websocket-price-streaming/spike_ws_publisher.py

# Terminal 3: Run automated test suite
cd backend && uv run python ../.planning/spikes/003-websocket-price-streaming/spike_ws_test.py

# Or open http://localhost:8099 for interactive dashboard
```

## What to Expect

- Server starts on port 8099 with interactive HTML dashboard
- Publisher sends random price updates every 1-3s to Redis
- Dashboard shows live YES/NO prices, latency, price chart, event log
- Auto-reconnect with exponential backoff on disconnect
- Stale badge appears after 30s of no data

## Investigation Trail

### Iteration 1: Core architecture
Built FastAPI WS endpoint with `redis.asyncio` pub/sub subscription in a background task.
Pattern: Celery → `redis.publish("prices:{market_id}", json)` → FastAPI subscriber → ConnectionManager → broadcast to all WS clients on that market.

### Iteration 2: Automated test suite (6 tests)
Wrote comprehensive tests instead of relying only on visual dashboard:
1. Basic connection + message receipt
2. End-to-end latency over 20 messages
3. Multi-client broadcast (5 clients, same market)
4. Cross-market isolation
5. Burst backpressure (100 rapid messages)
6. Reconnect simulation

### Key observation: latency is negligible
End-to-end latency (publisher → Redis → server → WS client) is sub-millisecond on average. The 2-second requirement from Phase 9 is trivially met — the bottleneck will be the Polymarket poll interval (30s), not the streaming pipeline.

### Key observation: zero message drops under burst
100 rapid messages published, 100/100 received in order. The `redis.asyncio` pub/sub + asyncio event loop handles backpressure without explicit flow control.

## Results

### Verdict: **VALIDATED**

### Test Results (6/6 PASS)

| Test | Result | Detail |
|------|--------|--------|
| Basic connection | PASS | Message received, latency 3.9ms |
| End-to-end latency | PASS | avg=0.8ms, p50=0.7ms, p95=4.4ms, max=4.4ms |
| Multi-client broadcast | PASS | 5/5 clients received 10/10 messages |
| Cross-market isolation | PASS | Zero cross-market leakage |
| Burst backpressure | PASS | 100/100 delivered, 0 dropped, all in order |
| Reconnect simulation | PASS | New connection immediately receives new messages |

### Key Findings

1. **Sub-millisecond latency.** avg=0.8ms end-to-end through the full Redis pub/sub → WS pipeline. The <2s Phase 9 requirement is met by 2500x margin.

2. **Zero message loss under burst.** 100 rapid messages delivered with 0 drops. No explicit backpressure mechanism needed — asyncio event loop + Redis pub/sub handles it natively.

3. **Perfect broadcast fidelity.** 5 concurrent clients on same market all received 100% of messages. ConnectionManager pattern with `set[WebSocket]` per market is sufficient.

4. **Clean market isolation.** `psubscribe("prices:*")` + routing by market_id in the channel name ensures zero cross-market leakage.

5. **Reconnect is trivial.** After disconnect, a new WebSocket connection immediately receives subsequent messages. No state to restore — prices are live-only (historical data comes from `odds_snapshots` table, not the stream).

6. **Zero new deps required.** `redis.asyncio` (from `redis>=5.0` already in project) + FastAPI native WebSocket is all that's needed.

### Architecture for Phase 9

```
Celery Beat (30s poll)
  -> Polymarket Gamma API
  -> Upsert odds_snapshots
  -> redis.publish("prices:{market_id}", json)

Admin edits house odds
  -> Update DB
  -> redis.publish("prices:{market_id}", json)

FastAPI server (background task)
  -> redis.asyncio psubscribe("prices:*")
  -> ConnectionManager.broadcast(market_id, data)
  -> All connected WS clients on that market

Next.js client
  -> new WebSocket("/ws/prices/{market_id}")
  -> onmessage: update price display
  -> onclose: exponential backoff reconnect
  -> Stale badge if no data >30s
```
