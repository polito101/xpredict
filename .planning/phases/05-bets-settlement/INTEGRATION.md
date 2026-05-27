# Phase 5 → main INTEGRATION RUNBOOK (for Pol)

> **Status: the FULL integration (Phase 1+2+3+4+5) is VERIFIED end-to-end.** It was assembled
> + tested on the pushed reference branch **`origin/integration/phase-05-full`** (a throwaway
> verification branch — NOT for direct merge; `main` stays PR-only / Pol-merges). This runbook
> is the exact, safe, ordered sequence to land it officially. Everything below was actually run
> and is green; nothing here is speculative.

---

## TL;DR — what's left to make Phase 5 live on `main`

1. **Pol merges Phase 3** to `main` — WITH the `0003 → 0004` migration renumber (below).
2. **Rebase Phase 5** (`gsd/phase-05-bets-settlement`) onto the new `main`; drop the now-merged
   Phase 3 commits.
3. **Apply the integration artifacts** (already written + verified on `integration/phase-05-full`):
   migration `0005`, the 2 adapters, the router wiring, the money-lint reconcile, the E2E test,
   the 404-test repurpose.
4. Run the suite per-directory + the E2E, open the Phase 5 PR, merge.

The CODE for steps 2–4 is done and verified — it just cannot land on `main` without step 1
(Pol-only) first, because `main` is PR-only and Phase 5 depends on Phase 3.

---

## What was VERIFIED on `integration/phase-05-full` (green)

| Suite | Result |
|-------|--------|
| `tests/integration/test_phase5_e2e.py` (bet → resolve → wallet → portfolio) | **1/1** |
| `tests/bets` | 39/39 |
| `tests/settlement` | 39/39 |
| `tests/markets` (Phase 4 regression) | 60/60 |
| `tests/wallet` (Phase 3 regression) | 38/38 |
| `ruff` / `ruff format` / `mypy` (touched files) / **money-lint** | clean |
| alembic | single linear head `0005_phase5_bets` |

Pre-existing failures NOT introduced here (see §Pre-existing debt): 2 auth `password_reset` tests.

The E2E proves the demo: a player bets 40 on YES (price 0.5) → wallet 100→60 → admin resolves
YES → wallet 60→**140** (payout 80) → market **RESOLVED** → portfolio shows the settled position
with realized P&L **+40**.

---

## STEP 1 — Merge Phase 3 to main, WITH the migration renumber (POL — PR-only)

Phase 3 (`gsd/phase-03-wallet-double-entry-ledger`) and Phase 4 (already merged) both created a
migration numbered `0003` off `0002` (the parallel-dev collision). Before/while merging Phase 3:

- **Rename** `0003_phase3_wallet_ledger.py` → **`0004_phase3_wallet_ledger.py`**.
- Inside it set `revision = "0004_phase3_wallet_ledger"` and
  `down_revision = "0003_phase4_markets"`.
- (The exact edited file is on `integration/phase-05-full` — copy it verbatim.)
- Verify: `uv run --directory backend python -m alembic heads` → exactly **one** head.

Result: `main` = 1+2+3+4, linear chain `0001 → 0002 → 0003_phase4_markets → 0004_phase3_wallet_ledger`.

> Phase 3 also still needs its GSD gates if not already done: `/gsd-verify-work 3` →
> `/gsd-code-review` → `/gsd-secure-phase 3` (see the Phase 3 handoff in `PHASES.md`).

## STEP 2 — Rebase Phase 5 onto the new main (Agustin/Cuco)

Rebase `gsd/phase-05-bets-settlement` onto `main` (now 1+2+3+4). Drop the duplicated, now-merged
Phase 3 commits; keep only the Phase 5 commits. **Do NOT rebase blindly** — the conflicts are
small and already resolved on the reference branch:

- `backend/app/main.py` — keep ALL routers (markets + wallet + bets + settlement).
- `backend/alembic/env.py` — import every model for metadata (markets + wallet + bets).
- planning docs (ROADMAP/STATE/PHASES) — doc-only.

## STEP 3 — Apply the verified integration artifacts (Agustin/Cuco)

All of these are DONE + green on `integration/phase-05-full` — copy them onto the rebased Phase 5:

1. **`backend/alembic/versions/0005_phase5_bets.py`** — the `bets` table off `0004`. **FK-less**
   (matches `app/bets/models.py`; the market is validated at the app layer via `MarketReadPort`
   → 404 on an unknown market). A DB-level FK to `markets`/`outcomes` is an OPTIONAL Phase 11
   hardening — note it would require every bet/settlement test to seed real markets first.
2. **`backend/app/bets/adapters.py`** — `HouseMarketReadAdapter` (`MarketReadPort` over
   `MarketService.get_market_by_id`; reads on its OWN session — the port contract, since
   `place_bet` validates BEFORE `session.begin()`).
3. **`backend/app/settlement/adapters.py`** — `HouseMarketResolveAdapter` (`MarketResolvePort`;
   writes `status` RESOLVED/CLOSED + `resolved_at` on the caller's session → atomic with the
   ledger).
4. **Router wiring**: `get_market_source` returns `HouseMarketReadAdapter()`,
   `get_market_resolver` returns `HouseMarketResolveAdapter()` — the endpoints stop returning
   503 (the `| None` + the 503 guards were removed; the 503 tests became 404-unknown-market).
5. **money-lint reconcile** — `app/markets/models.py` odds columns
   (`initial_odds`/`current_odds`/`probability`) now use the Phase 5 `Odds` alias
   (`app/db/types.py`, `Numeric(8,6)`, schema-identical). **⚠️ This touches Phase 4's model —
   POL CONFIRM.** Without it, money-lint fails with 3 errors on the integrated tree → CI gate
   blocker. No schema/migration change; markets 60/60 still green.
6. **`backend/tests/integration/test_phase5_e2e.py`** — the E2E proof.

## STEP 4 — Verify + ship (Agustin/Cuco → Pol merges)

- `cd backend && uv run pytest tests/<dir>` per directory (whole-suite one-process hits the
  pre-existing DEF-03-01 audit-immutability poisoning — run per-dir; all green per-dir).
- `uv run --directory backend python -m alembic heads` → one head `0005_phase5_bets`.
- money-lint / ruff / mypy clean.
- `/gsd-verify-work 5` → `/gsd-code-review` → mark `PHASES.md` row 5 `👀 In review` → `/gsd-ship`
  (PR via GitHub MCP, repo-rooted session). **Pol merges.**

---

## Decisions made during integration (review these)

| Decision | Rationale | Pol action |
|----------|-----------|------------|
| Alembic renumber `0003_phase3_wallet_ledger` → `0004` | Resolves the parallel-dev `0003` collision; linear chain | Apply at the Phase 3 merge |
| `bets` table FK-less | Matches the model; market validated via the port (404). Keeps the decoupled suite green | OK as-is; FK = optional Phase 11 hardening |
| money-lint reconcile via `Odds` alias on Phase 4 odds cols | Phase 4's `Numeric(8,6)` odds fail money-lint (3 errors); the alias fixes it schema-identically | **Confirm** (touches `app/markets/models.py`) |
| API versioning inconsistency | Phase 4 routes are under `/api/v1/...`; auth/wallet/bets/settlement are NOT | **Decide**: standardize on `/api/v1` or leave (NOT a blocker) |
| current-odds unrealized P&L | Portfolio OPEN positions show potential payout at LOCKED odds; live current-odds P&L needs a markets read | Optional enhancement (enrich `get_portfolio` with the market source) |

## Pre-existing debt (NOT introduced by Phase 5 / the integration)

- **auth** `tests/auth/test_password_reset.py::{test_reset_invalidates_sessions,
  test_audit_trail_on_reset}` fail on the Phase 2/3 base (documented since the Phase 3 work).
  Phase 2/3 concern — verify on a clean `main`.
- **DEF-03-01** — `tests/core/test_audit_immutability.py` poisons the session-scoped tx without
  savepoint isolation → the whole-suite one-process run cascade-fails; per-directory is green.
- **Frontend lint** — `next lint` (15.5 CLI) + direct `eslint` (v9 vs legacy `.eslintrc`,
  "circular structure" at config load) cannot lint any FE file locally; `tsc` + `vitest` were
  used instead. Frontend-tooling fix needed.

## What still requires a human (Pol) — cannot be done autonomously

- The merge of Phase 3 + Phase 5 to **`main`** (PR-only; only Pol merges).
- **Confirm** the money-lint reconcile touching `app/markets/models.py`.
- **Decide** the API-versioning convention (`/api/v1` standardization).

## Remaining Phase 5 surface that is Phase-4-coupled FRONTEND (separate effort, ~Phase 9)

NOT required for the integration / the API-level E2E demo, but for a full UI demo:
- Bet confirm modal + market list + odds display (SC#3 client) — needs Phase 4's markets UI.
- Resolution display per market (SC#7) — needs market context.
- Admin two-step resolve/reverse UI (SC#5) — needs the markets admin UI.

The **portfolio page** (`/portfolio`, SC#7) IS built + tested. The bet/settlement BACKEND + the
portfolio read are fully integrated and demoable at the API level (the E2E test).
