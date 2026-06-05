---
phase: LB-A-backend-bridge
plan: 01
subsystem: integrations/livebets
tags: [livebets, ledger, integration, alembic, fastapi]
requires:
  - app.wallet.service.WalletService._post_transfer
  - app.wallet.constants.HOUSE_PROMO_ACCOUNT_ID
  - app.wallet.constants.HOUSE_REVENUE_ACCOUNT_ID
  - app.auth.deps.current_active_player
provides:
  - app.integrations.livebets.client.LiveBetsClient
  - app.integrations.livebets.service.LiveBetsBridge
  - app.integrations.livebets.router.livebets_router
  - app.integrations.livebets.models.LiveBetsBet
  - app.integrations.livebets.constants.LIVEBETS_ESCROW_ACCOUNT_ID
  - "DB: livebets_escrow singleton account + livebets_bets mirror table (migration 0011)"
affects:
  - backend/app/main.py  # mounts livebets_router
tech-stack:
  added: []   # no new third-party dependency (httpx/tenacity/pydantic/sqlalchemy/alembic/fastapi-users already present)
  patterns:
    - "Server-side-verified, idempotent ledger mirror via WalletService._post_transfer in one owned tx (mirrors app/bets + app/settlement)"
    - "Two-layer idempotency: livebets_bets mirror-row primary guard + UNIQUE transfers.idempotency_key (23505) secondary guard"
    - "Canonical UUID lock order (sorted(..., key=str)) + FOR UPDATE before every post"
    - "Lazy httpx.AsyncClient singleton + tenacity retry with X-API-Key auth (mirrors polymarket GammaClient)"
key-files:
  created:
    - backend/alembic/versions/0011_livebets_bridge.py
    - backend/app/integrations/livebets/__init__.py
    - backend/app/integrations/livebets/constants.py
    - backend/app/integrations/livebets/models.py
    - backend/app/integrations/livebets/client.py
    - backend/app/integrations/livebets/schemas.py
    - backend/app/integrations/livebets/service.py
    - backend/app/integrations/livebets/router.py
  modified:
    - backend/app/core/config.py
    - backend/app/main.py
    - .env.example
decisions:
  - "Loss sink = house_revenue (NOT house_promo): the design §8 table shows losses -> house_promo, but the CONTEXT open item + app/settlement/service.py's loser sweep (market_liability -> house_revenue) win. Recorded in migration + service docstrings."
  - "LiveBetsVerificationError defined INLINE in service.py (not a sibling exceptions.py) to stay strictly within the plan's files_modified allowlist. The plan explicitly permits the inline option."
  - "Live-bets status enum is PENDING|WON|LOST|REFUNDED|VOIDED (no VOID); REFUNDED + VOIDED both take the stake-return leg (escrow -> wallet)."
  - "Two-leg WON settle uses distinct idempotency keys livebets:{bet_id}:settled:stake / :winnings; LOST/REFUNDED/VOIDED single legs use the bare livebets:{bet_id}:settled."
  - "Settled payout field name parsed defensively: prefer 'payout', fall back to 'potential_payout', absent-on-WON => raise (verification failure, never guess)."
metrics:
  duration: ~50m
  completed: 2026-06-05
  tasks: 2
  files: 11
  commits: 2
---

# Phase LB-A Plan 01: Backend bridge Summary

Additive `app/integrations/livebets/` module that mirrors live-bets bets into XPredict's own double-entry ledger — server-side-verified against `GET /v2/bets/{id}`, idempotent by `bet_id`, reusing `WalletService._post_transfer` exactly as `app/bets` and `app/settlement` do — plus a reversible Alembic migration (`livebets_escrow` singleton + `livebets_bets` mirror table), `LIVEBETS_*` settings, and the mounted `/api/live/*` router. Zero behavior change to existing wallet/bets/settlement tables. Tests ship in LB-A-02.

## What was built

### Task 1 — additive schema + config foundation (commit `ede15dc`)
- **`constants.py`** — plain `str`/`UUID` literals (no enums): `KIND_LIVEBETS_ESCROW`, `LIVEBETS_ESCROW_ACCOUNT_ID = ...00b1` (singleton, distinct from house `...00a1`/`...00a2`), five `livebets_*` transfer kinds, the live-bets status set (`PENDING|WON|LOST|REFUNDED|VOIDED` + `LIVEBETS_REFUND_STATUSES` + `LIVEBETS_SETTLED_STATUSES`), and idempotency-key helpers (`placed_idempotency_key`, `settled_idempotency_key`, `settled_stake_idempotency_key`, `settled_winnings_idempotency_key`).
- **`models.py`** — `LiveBetsBet` ORM (`bet_id` PK, NOT server-defaulted; FK-less `user_id`; nullable `table_id`/`market_id`; `Mapped[Money]` `stake`; status CHECK; `created_at`/`settled_at`; `tenant_id` ghost).
- **`__init__.py`** — one-line docstring; deliberately registers nothing (livebets is not a `MarketSource`, unlike polymarket).
- **`0011_livebets_bridge.py`** — additive reversible migration; `revision = "0011_livebets_bridge"` (20 chars, under the varchar(32) limit), `down_revision = "0010_phase12_resolution_stakes"` (confirmed the current head via `alembic heads`). Creates `livebets_bets` (matching the model verbatim) + `livebets_bets_user_idx`, and seeds the `livebets_escrow` singleton with the same `ON CONFLICT DO NOTHING` idempotent pattern as the house seed in 0004. Downgrade deletes the escrow account by id, drops the index, drops the table.
- **`config.py`** — appended `LIVEBETS_API_BASE` (`http://localhost:8080`), `LIVEBETS_API_KEY` (optional), `LIVEBETS_DEFAULT_TABLE_ID`, `LIVEBETS_ENABLE_WEBHOOK=False`, `LIVEBETS_WEBHOOK_SECRET`.
- **`.env.example`** — `# Live-bets demo (v1.3, LB-A)` block with placeholders only.

### Task 2 — client + service + router (commit `ebe52ed`)
- **`client.py`** — `LiveBetsClient`: lazy `httpx.AsyncClient` singleton, bounded limits/timeout, tenacity retry on `(NetworkError, TimeoutException)` with `reraise=True`, `X-API-Key` default header (raises `RuntimeError("LIVEBETS_API_KEY is not configured")` from `_get_client` if unset). `mint_session` / `get_bet` / `list_tables` / `close`. A live-bets `403 SCOPE_MISMATCH` is mapped to `RuntimeError("live-bets key missing required scope (need bets:read) — see LB-C")`, not a generic 500 (the M1 cross-phase dependency).
- **`schemas.py`** — `SessionResponse`, `TableItem` (`extra="ignore"`), `TablesResponse`, `MirrorResult(applied=...)`, and a `VerifiedBet` + `parse_verified_bet` parser: money is `Decimal` (never float); `bet_id`/`status`/`stake` required (missing stake => raise); `payout` prefers `payout`, falls back to `potential_payout`, else `None`.
- **`service.py`** — `LiveBetsBridge.record_placed` / `record_settled`. Verify-first (read-only, before `session.begin()`), then one owned transaction with canonical UUID lock order (`sorted(..., key=str)` + `with_for_update()`) and `WalletService._post_transfer` per leg. Idempotency: mirror-row primary guard (`on_conflict_do_nothing` on placed / `status != PENDING` on settled) + `IntegrityError`/`23505` secondary guard. `LiveBetsVerificationError` defined inline. Ledger flows: placed `wallet -> escrow` (stake); WON `escrow -> wallet` (stake) + `house_promo -> wallet` (payout-stake, skipped when `<= 0`); LOST `escrow -> house_revenue` (stake); REFUNDED/VOIDED `escrow -> wallet` (stake).
- **`router.py`** — `livebets_router` (`prefix="/api/live"`), all four routes under `current_active_player`, `get_livebets_client()` override seam, `LiveBetsVerificationError -> 409` / `NoResultFound -> 404`. No `from __future__ import annotations` (the documented FastAPI 3.13 forward-ref constraint).
- **`main.py`** — `livebets_router` imported (isort-correct position) and `include_router(livebets_router)` after `bets_router`.

## Verification (all run, all pass)

| Check | Command | Result |
|-------|---------|--------|
| T1.v1 parse | `python -c "ast.parse(...)" migration+constants+models` | `parse-ok` |
| T1.v2 settings | `Settings()` LIVEBETS defaults | `settings-ok` |
| T1.v3 money lint | `python scripts/lint_money_columns.py` | `OK: 8 files checked, 2 warnings` (warnings pre-existing in `app/markets/models.py`, not in scope) |
| T2.v1 parse | `python -c "ast.parse(...)" client+schemas+service+router` | `parse-ok` |
| T2.v2 routes | route-presence assertion on `app.routes` | `routes-mounted` (all 4 `/api/live/*`) |
| T2.v3 contracts | `LiveBetsBridge` + `LiveBetsClient` method presence | `contracts-ok` |
| T2.v4 ruff | `ruff check app/integrations/livebets/` | `All checks passed!` |
| module imports | `python -c "import ...livebets..."` | `module-imports-clean` |
| alembic heads | `alembic heads` | `0011_livebets_bridge (head)`, chained off `0010_phase12_resolution_stakes` |
| no new dep | `git diff --stat backend/pyproject.toml backend/uv.lock` | empty (no dependency change) |
| additive only | `git diff --name-only HEAD~2 HEAD` | exactly the plan's `files_modified` (11 files); no wallet/bets/settlement source touched |
| ruff (touched) | `ruff check app/main.py app/core/config.py app/integrations/livebets/` | `All checks passed!` |

### Extra: real-DB migration up/down (beyond the plan; LB-A-02 owns the formal migration test)
Against a throwaway Postgres 16 container (removed after):
- `alembic upgrade head` → full chain runs through `0011`; `livebets_bets` table exists, `livebets_escrow` seeded (id `...00b1`, kind `livebets_escrow`, system, balance 0), status CHECK present.
- `alembic downgrade -1` → table dropped, escrow account removed, index gone, `accounts`/`transfers`/`entries`/`bets` intact, revision back to `0010_phase12_resolution_stakes`.

## Deviations from Plan

**1. [Plan-permitted choice] `LiveBetsVerificationError` defined inline in `service.py` instead of a sibling `exceptions.py`.**
- **Why:** The plan offers "a small `exceptions.py` OR inline at the top of `service.py`". An `exceptions.py` is NOT in the plan's `files_modified`, and the executor HARD CONSTRAINT is to modify only listed files. Inlining honors the plan's explicit alternative while staying within the allowlist. The router imports it from `service.py`.

**2. [Setup accommodation, not a code change] `<verify>` commands that instantiate `Settings()`/`app` were run with the canonical base env seeded inline.**
- **Why:** This fresh worktree has no `.env`/`.env.local`, so bare `Settings()` raises `ValidationError` for the four required base vars (`DATABASE_URL`, `DATABASE_URL_SYNC`, `REDIS_URL`, `SECRET_KEY`). I supplied the SAME values the test suite's `conftest._DEFAULT_TEST_ENV` uses, so the verify faithfully exercises my additions. Pure-AST/ruff/money-lint checks need no env and ran bare. This is an environment gap in the worktree, not a deviation from the plan's intent, and changes no code.

No other deviations — the plan executed as written (no auto-fixed bugs, no added critical functionality beyond plan, no architectural changes).

## Known Stubs
None. The only "placeholder" is the intentional `LIVEBETS_API_KEY=lbk_sandbox_...` in `.env.example` (gitleaks-clean placeholder, required by the plan). No stub UI values, no TODO/FIXME in the implementation. The webhook receiver is intentionally OUT of scope (CONTEXT) and was not built; `LIVEBETS_ENABLE_WEBHOOK` stays `False`.

## Notes for downstream (LB-A-02 tests / LB-B / LB-C)
- **LB-A-02** owns the bridge unit tests (faked `LiveBetsClient`, no network) + the formal migration up/down test. Inject the client via `record_placed(..., client=fake)` / `record_settled(..., client=fake)` or override `get_livebets_client` via `app.dependency_overrides`. Idempotency-key literals to assert against live in `constants.py` (`placed_idempotency_key` etc.).
- **LB-C** must issue the operator key WITH `bets:read` (sandbox keys are `bets:place`+`catalog:read` only). Without it, `get_bet` surfaces `RuntimeError("...need bets:read...see LB-C")` and every verification fails by design.
- Escrow-nets-to-zero is structural (placed +stake; settle -stake), documented in the service docstring; LB-A-02 asserts it across placed→won and placed→lost.

## Self-Check: PASSED
All 8 created module/migration files + the SUMMARY exist on disk; both commits (`ede15dc`, `ebe52ed`) exist in git history.
