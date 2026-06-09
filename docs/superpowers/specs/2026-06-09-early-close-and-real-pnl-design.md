# Early Close + Real Open P&L — Design

**Date:** 2026-06-09
**Status:** Approved (inline) → spec
**Scope:** Two changes to the bets/portfolio subsystem, shipped as two separate commits on one branch / one PR.

- **B — Real Open P&L:** the portfolio's "Open P&L" currently shows *potential winnings if the outcome wins* (always ≥ 0). Replace it with the real, mark-to-market unrealized P&L (signed), keeping the potential-win figure as a separate, honestly-labeled value.
- **A — Early close:** let a user close (cash out) an open position before market resolution at the current fair value. The house is the counterparty (as it already is at settlement).

Sequencing: **B first, then A.** B builds the live current-value computation that A reuses.

---

## 1. Background (confirmed in code)

- A position = one immutable `Bet` row — fixed-odds stake, **no shares/quantity** ([backend/app/bets/models.py:31](../../../backend/app/bets/models.py)). `odds_at_placement` (a probability in `(0,1]`) is the entry price, locked at placement.
- Pricing is **fixed-odds**, the **house is the counterparty** — not parimutuel, not AMM, no order book. Winnings funded by `HOUSE_PROMO_ACCOUNT_ID`; loser stakes swept to `HOUSE_REVENUE_ACCOUNT_ID`. Per-market `market_liability` account just holds stakes and nets to zero.
- "Current price" = `Outcome.current_odds` (probability `[0,1]`, [backend/app/markets/models.py:305](../../../backend/app/markets/models.py)):
  - **Polymarket-proxy:** mirrored from Polymarket, refreshed by Celery beat ~every 300 s (up to ~5 min stale).
  - **House:** static, admin-set; does **not** drift with volume.
- Ledger is double-entry, append-only. Account/transfer `kind` are **Text, not enums** → new kinds need no migration. `bets.status` is a CHECK-constrained Text (`PENDING` / `SETTLED_WON` / `SETTLED_LOST`) → a new value **does** need a migration.

### The Open P&L bug — root cause

[backend/app/bets/portfolio.py:84](../../../backend/app/bets/portfolio.py) (open branch):

```python
potential = compute_payout(p.stake, p.odds_at_placement)   # stake / odds_at_placement
potential_pnl = profit_or_loss(p.stake, potential)         # potential - stake
```

So the displayed "Open P&L" is `stake / odds_at_placement − stake`, which is **mathematically ≥ 0** (since `odds_at_placement ∈ (0,1]`). It uses the **entry** price as if it were current, and reports the **full win-scenario payout**, not current value. It is literally "what you'd win if this resolves YES" — and is even captioned "If this outcome wins" on the frontend. The real unrealized P&L was deliberately deferred ("layered on once the market read port is wired") and never wired.

---

## 2. The correct P&L math

A bet of stake `S` at entry price `p0 = odds_at_placement` is equivalent to holding `N = S / p0` binary units that each pay `$1` if the outcome resolves YES (decimal odds `1/p0`, price per unit `p0`).

At current price `pc = current_odds` of **that outcome**:

```
current_value     = S × (pc / p0)          # = N × pc
unrealized_pnl    = current_value − S
                  = S × (pc / p0 − 1)
                  = S × (pc − p0) / p0
```

- `pc > p0` (outcome became more likely) → **positive** P&L.
- `pc < p0` (less likely) → **negative** P&L.
- `pc = p0` → 0.

This same `current_value` is the **fair cash-out value** for early close (risk-neutral, no fee → liquidation value = expected value). All quantization uses the existing helpers in [backend/app/settlement/payout.py](../../../backend/app/settlement/payout.py) for consistency.

> Note: an earlier draft formula `S × (p0 / pc)` was **inverted** and is wrong; the correct value is `S × (pc / p0)`.

---

## 3. Change B — Real Open P&L

### Backend
- `BetService.get_portfolio` ([backend/app/bets/service.py:166](../../../backend/app/bets/service.py)) reads live `current_odds` for each open bet's outcome via the existing `MarketReadPort` (the same port `place_bet` uses). Batch the lookups (one query for all outcomes in the portfolio) — no N+1.
- `portfolio.py` open branch computes, per position:
  - `current_value = quantize(stake × current_odds / odds_at_placement)`
  - `unrealized_pnl = current_value − stake` (signed)
  - keep `potential_pnl` as-is (separate field).
- **Fallback:** if `current_odds` is unavailable for an outcome (not found / read error), set `current_value = stake`, `unrealized_pnl = 0`, and flag the position (e.g. `priced=false`) rather than failing the whole portfolio.
- `PortfolioResponse` / position schema ([backend/app/bets/schemas.py:80](../../../backend/app/bets/schemas.py)) gains: `current_odds`, `current_value`, `unrealized_pnl`. `potential_pnl` retained.

### Frontend ([frontend/src/app/portfolio/page.tsx:187](../../../frontend/src/app/portfolio/page.tsx))
- "Open P&L" stat tile sums `unrealized_pnl` (signed; red/green — the `PnL` component's negative branch already exists and is currently dead code for open positions).
- A separate, clearly-labeled figure "Si gana, cobras" = `potential_pnl`.
- Per open position: real P&L (signed) + the potential-win figure. Caption no longer claims the P&L is the win scenario.

---

## 4. Change A — Early close

### Migration
`bets` table:
- Widen the `bets_status_check` CHECK to include `CLOSED`.
- Add `closed_at TIMESTAMPTZ NULL`.
- Add `exit_odds NUMERIC(8,6) NULL` (CHECK `>= 0 AND <= 1`).

Realized P&L on close is derivable from `stake`, `odds_at_placement`, `exit_odds`; not stored separately.

### Service — `BetService.sell_position(bet_id, user)`
One ACID transaction, mirroring `place_bet` / settlement patterns:
1. `SELECT ... FOR UPDATE` the bet; verify `bet.user_id == user.id`, `status == PENDING`, and the **market is still open** (via `MarketReadPort` — reject if resolved/closed). Lock wallet + `market_liability` accounts `FOR UPDATE` in a consistent order to avoid deadlock with settlement.
2. Read `current_odds` of the bet's outcome → `payout = quantize(stake × current_odds / odds_at_placement)`. No fee.
3. Ledger postings (Transfer `kind="bet_closed"`, idempotency keys `close:{bet_id}:{leg}`):
   - **Gain** (`payout ≥ stake`): `market_liability → user_wallet` for `stake`; `house_promo → user_wallet` for `payout − stake`.
   - **Loss** (`payout < stake`): `market_liability → user_wallet` for `payout`; `market_liability → house_revenue` for `stake − payout`.
   - Either way the bet's `market_liability` contribution nets to 0 (it received exactly `stake` at placement).
4. Set `status=CLOSED`, `closed_at=now`, `exit_odds=current_odds`. Persist; update the wallet balance cache via the existing `WalletService` path (optimistic `version`).

Edge cases:
- `current_odds == 0` → `payout = 0` (outcome now deemed impossible); allowed — user salvages nothing, full loss.
- `current_odds == 1` → pays like a full win; allowed.
- Concurrent close vs. settlement: settlement filters `PENDING` only, so a `CLOSED` bet is skipped; `FOR UPDATE` + status check make the transition atomic. Re-closing a `CLOSED` bet → rejected (status check) / idempotency key collision.

### API
`POST /bets/{bet_id}/sell` ([backend/app/bets/router.py:147](../../../backend/app/bets/router.py)) — replace the hard 405 with the service call. Gated like `place_bet` (active + verified + not-banned). Response: `{ payout, pnl, new_balance, exit_odds }`. Errors: 404 (not owner / not found), 409 (already closed / market resolved).

### Frontend
- `frontend/src/lib/bet-actions.ts`: add `sellPositionAction(betId)` → `POST /bets/{id}/sell`.
- `portfolio/page.tsx`: a **"Cerrar / Cash out"** button per open position, showing the current cash-out value (= `current_value` from B) and the resulting P&L, behind a confirm. On success, revalidate the portfolio.

---

## 5. Testing

**Backend (`cd backend && uv run pytest`, testcontainers + Docker):**
- P&L unit: `current_value`/`unrealized_pnl` for `pc > p0` (+), `pc < p0` (−), `pc == p0` (0), missing-price fallback.
- Close integration: gain / loss / break-even — assert ledger entries net to zero, `market_liability` for the bet ends at 0, user balance matches `payout`, house accounts move correctly.
- Close guards: rejected when market resolved, bet not owned, already `CLOSED`; idempotency (replaying the same close is a no-op).
- Race: close vs. settlement on the same bet — exactly one wins, no double pay.

**Frontend (`cd frontend && pnpm vitest run`):**
- Open P&L tile renders a negative value (red, signed).
- "Si gana" figure renders separately.
- Close button triggers `sellPositionAction` and reflects the new balance.

---

## 6. Out of scope (YAGNI for v1)

- Fees/spread on close (chosen: fair value, no house edge).
- Odds-freshness gating for Polymarket (accepted: ~5 min staleness for the demo).
- Partial close (only whole-position close).
- Persisting a separate realized-P&L column (derivable from `exit_odds`).
- Any AMM / order book / price-discovery engine.

---

## 7. Risks / notes

- **House-market staleness:** house `current_odds` is admin-set and static, so early close there returns ≈ stake until an admin moves the odds — expected, not a bug.
- **Polymarket staleness (~5 min):** a user could close against a price the house knows is stale. Accepted for the demo; revisit with freshness gating or a spread if it becomes a real-money concern.
- **No house edge anywhere** in v1 means early close is exactly fair — fine for a demo, deliberately flagged for the SaaS phase.
