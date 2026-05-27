# Spike Wrap-Up Summary

**Date:** 2026-05-27
**Spikes processed:** 2
**Feature areas:** Wallet & Concurrency, Polymarket Integration
**Skill output:** `./.claude/skills/spike-findings-xpredict/`

## Processed Spikes
| # | Name | Type | Verdict | Feature Area |
|---|------|------|---------|--------------|
| 001 | async-wallet-concurrency | standard | VALIDATED | Wallet & Concurrency |
| 002 | polymarket-gamma-parser | standard | VALIDATED | Polymarket Integration |

## Key Findings

### Wallet & Concurrency (Phase 3)
- `SELECT ... FOR UPDATE` serializes concurrent wallet access with zero drift across 100 concurrent tasks
- Without FOR UPDATE, 49% of overdraw attempts bypass application logic (TOCTOU race quantified)
- Lock ordering by sorted account ID prevents deadlocks — without it, 96/100 bidirectional transfers deadlocked
- `CHECK (balance >= 0)` is defense-in-depth, not primary mechanism
- Performance: ~16ms/transfer with FOR UPDATE, vs ~240ms/transfer without lock ordering (15x slower)

### Polymarket Integration (Phase 6)
- Gamma API returns stringified JSON for `outcomes`, `outcomePrices`, `clobTokenIds` — requires `json.loads()` in Pydantic validators
- Dual numeric encoding: string fields (`volume`) for precision, float fields (`volumeNum`) for sorting only
- State machine: `closed=true` alone does NOT mean resolved — only `closed + umaResolutionStatus="resolved" + clear winner` is safe to settle
- `umaResolutionStatus` is absent (not null) when no UMA process started
- `umaResolutionStatuses` (plural) contains full UMA lifecycle history
- `extra='allow'` handles 50+ API fields and schema drift
