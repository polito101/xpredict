# Spike Wrap-Up Summary

**Date:** 2026-05-27
**Spikes processed:** 4
**Feature areas:** Wallet & Concurrency, Polymarket Integration, Real-Time Streaming, Settlement
**Skill output:** `./.claude/skills/spike-findings-xpredict/`

## Processed Spikes
| # | Name | Type | Verdict | Feature Area |
|---|------|------|---------|--------------|
| 001 | async-wallet-concurrency | standard | VALIDATED | Wallet & Concurrency |
| 002 | polymarket-gamma-parser | standard | VALIDATED | Polymarket Integration |
| 003 | websocket-price-streaming | standard | VALIDATED | Real-Time Streaming |
| 004 | settlement-acid-transaction | standard | VALIDATED | Settlement |

## Key Findings

### Wallet & Concurrency (Phase 3)
- `SELECT ... FOR UPDATE` serializes concurrent wallet access with zero drift across 100 concurrent tasks
- Without FOR UPDATE, 49% of overdraw attempts bypass application logic (TOCTOU race quantified)
- Lock ordering by sorted account ID prevents deadlocks -- without it, 96/100 bidirectional transfers deadlocked
- `CHECK (balance >= 0)` is defense-in-depth, not primary mechanism
- Performance: ~16ms/transfer with FOR UPDATE, vs ~240ms/transfer without lock ordering (15x slower)

### Polymarket Integration (Phase 6)
- Gamma API returns stringified JSON for `outcomes`, `outcomePrices`, `clobTokenIds` -- requires `json.loads()` in Pydantic validators
- Dual numeric encoding: string fields (`volume`) for precision, float fields (`volumeNum`) for sorting only
- State machine: `closed=true` alone does NOT mean resolved -- only `closed + umaResolutionStatus="resolved" + clear winner` is safe to settle
- `umaResolutionStatus` is absent (not null) when no UMA process started
- `umaResolutionStatuses` (plural) contains full UMA lifecycle history
- `extra='allow'` handles 50+ API fields and schema drift

### Real-Time Streaming (Phase 9)
- Sub-millisecond latency end-to-end (avg=0.8ms) through Redis pub/sub -> FastAPI WS -> client; <2s requirement met by 2500x margin
- Zero message loss under burst (100 rapid messages, 0 drops, all in order)
- Perfect broadcast fidelity (5 concurrent clients, 100% message delivery)
- Clean market isolation via `psubscribe("prices:*")` + channel routing
- Reconnect is trivial -- no state to restore, prices are live-only
- Zero new deps required (`redis.asyncio` + FastAPI native WebSocket)

### Settlement (Phase 5)
- One ACID transaction handles 50 bets with 50+ ledger entries in ~155ms
- FOR UPDATE on market row serializes concurrent settlements (1 settled, 1 idempotent_skip)
- CRITICAL: need SETTLING status transition before querying bets to prevent late-bet pot imbalance
- Losers' stakes are already in the pot -- no separate debit; remaining pot sweeps to house_revenue
- `settled_at IS NULL` is the idempotency gate
- Double-entry invariant holds: SUM(operational entries) = 0
- In balanced 50/50 binary market, house_revenue = 0 (house profits only from market imbalance)
