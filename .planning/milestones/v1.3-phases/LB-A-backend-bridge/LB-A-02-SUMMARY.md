---
phase: LB-A-backend-bridge
plan: 02
subsystem: integrations/livebets
tags: [livebets, ledger, tests, testcontainers, alembic, fastapi, idempotency, verification]
requires:
  - app.integrations.livebets.service.LiveBetsBridge
  - app.integrations.livebets.service.LiveBetsVerificationError
  - app.integrations.livebets.constants.LIVEBETS_ESCROW_ACCOUNT_ID
  - app.integrations.livebets.router.livebets_router
  - app.integrations.livebets.router.get_livebets_client
  - app.wallet.constants.HOUSE_PROMO_ACCOUNT_ID
  - app.wallet.constants.HOUSE_REVENUE_ACCOUNT_ID
  - app.auth.deps.current_active_player
  - "DB: livebets_escrow singleton + livebets_bets mirror table (migration 0011)"
provides:
  - "Test suite: backend/tests/integrations/livebets/ (3 modules, 21 tests, hermetic)"
  - "Proof: LB-A bridge money path + two-layer idempotency + server-side verification"
  - "Proof: migration 0011 additive + reversible against real Postgres 16"
  - "Proof: /api/live/* auth gate (401) + GET /tables + POST /session happy path"
affects:
  - backend/app/integrations/livebets/service.py  # wave-1 record_settled autobegin fix (deviation)
tech-stack:
  added: []   # pytest, pytest-asyncio, testcontainers, httpx already in pyproject.toml — no new package
  patterns:
    - "Hermetic bridge tests: FakeLiveBetsClient (no network) is the ONLY bet source; committed-session helpers + BEFORE/AFTER deltas on shared singletons + fresh uuid4 per test (mirrors test_resolve_market.py)"
    - "Reversible-migration test in ISOLATION: its own throwaway PostgresContainer driven by alembic.command (sync), never the shared session-scoped engine — touches only DATABASE_URL_SYNC so the async pool is undisturbed (no teardown socket leak)"
    - "Router auth-gate + happy-path via httpx ASGITransport (no Docker) + app.dependency_overrides cleared per test"
    - "SECONDARY 23505 guard proven by pre-inserting a colliding per-leg key while the mirror row is still PENDING (the only way to reach the two-leg WON collision path)"
key-files:
  created:
    - backend/tests/integrations/__init__.py
    - backend/tests/integrations/livebets/__init__.py
    - backend/tests/integrations/livebets/test_livebets_bridge.py
    - backend/tests/integrations/livebets/test_migration_0011.py
    - backend/tests/integrations/livebets/test_livebets_router.py
  modified:
    - backend/app/integrations/livebets/service.py   # wave-1 fix only (see Deviations)
decisions:
  - "Migration test uses its OWN module-scoped PostgresContainer (cheap correctness over shared-state cleverness, as the plan endorses): a downgrade against the session-scoped engine would poison the schema for every later test. It mutates ONLY DATABASE_URL_SYNC (alembic is sync) and leaves the async DATABASE_URL + lazy engine caches untouched — disturbing the async engine is what leaked an asyncpg socket at session teardown (exit 1 with all tests green); isolating it restores a clean exit 0."
  - "Router DB-touching placed/settled happy path is NOT re-exercised here — the bridge tests already prove the money path end-to-end. The router module asserts only the auth gate (all 4 routes 401) + the no-DB GET /tables + POST /session happy path (the plan's lighter split)."
  - "POST /session happy path supplies table_id in the request body so it needs no LIVEBETS_DEFAULT_TABLE_ID (which defaults to None in the test env)."
  - "Added tests/integrations/__init__.py (parent package marker, not in the plan's files_modified) to match the universal project convention that every test package has an __init__.py — guards against future basename-collision fragility under pytest's prepend import mode. Trivial empty file; suite green with and without it."
  - "A module-level filterwarnings('ignore::pytest.PytestUnraisableExceptionWarning') on the migration module down-grades the benign alembic NullPool connection-finalizer warning (Connection.__del__ at GC) to non-fatal — it weakens NO assertion (every schema assertion still runs and passes), mirroring the targeted third-party ignore entries already in pyproject.toml."
metrics:
  duration: ~40m
  completed: 2026-06-06
  tasks: 2
  files: 5 created + 1 modified
  commits: 3
---

# Phase LB-A Plan 02: Bridge test suite Summary

Hermetic backend test suite (`backend/tests/integrations/livebets/`, 3 modules, 21 tests) proving the LB-A live-bets bridge correct against real Postgres 16 (testcontainers) with a faked client (no live network): the placed->won / placed->lost / refund money path with escrow netting to zero, two-layer idempotency (mirror-row primary + `transfers.idempotency_key` 23505 secondary), server-side verification rejecting mismatches with zero ledger effect, an additive+reversible migration test, and the `/api/live/*` auth gate. **While running the suite it exposed — and this plan fixed — a real wave-1 bug: `record_settled` ran DB reads before `session.begin()`, autobeginning a transaction so `begin()` raised on every settle.** New suite: 21 passed. Regression (wallet/bets/settlement): 130 passed — zero behavior change.

## What was built

### Task 1 — `test_livebets_bridge.py` (12 tests, reviewed + kept from the prior run)
Mirrors `tests/settlement/test_resolve_market.py` exactly: `pytest.mark.integration` + `asyncio(loop_scope="session")`, the `engine` fixture runs `alembic upgrade head` (so migration 0011 creates `livebets_escrow` + `livebets_bets` in the container — no `Base.metadata` table-create fixture), committed-session helpers (`_seed_wallet` / `_balance` verbatim), BEFORE/AFTER deltas on the shared `house_promo` / `house_revenue` / `livebets_escrow` singletons, fresh `uuid4()` wallets + `bet_id`s per test. `FakeLiveBetsClient` (in-memory, `get_bet`/`mint_session`/`list_tables`) is the only bet source.

Behaviors proven:
- **placed->won**: wallet -stake then +stake +(payout-stake); `livebets_escrow` delta over the full cycle == 0; winnings come from `house_promo`; mirror row WON + `settled_at`; the deferred `bets` table is untouched; 3 transfers carry the `bet_id` (placed + stake-return + winnings).
- **placed->lost**: wallet down by the full stake; escrow nets to zero; `house_revenue` gains the stake; mirror LOST.
- **refund — REFUNDED and VOIDED (parametrized, both real refund statuses; no `VOID`)**: wallet whole again; escrow nets to zero; neither house account touched; mirror REFUNDED / VOIDED.
- **won with payout == stake**: only the stake-return leg posts (no zero-amount winnings entry, `CHECK (amount > 0)` never tripped); `house_promo` untouched; exactly 2 transfers.
- **idempotency PRIMARY guard**: duplicate `record_placed` and duplicate `record_settled` -> `applied=False`, no extra transfer, balances unchanged.
- **idempotency SECONDARY (23505) guard, two-leg WON path**: pre-insert a colliding `livebets:{bet_id}:settled:stake` transfer while the mirror row is still PENDING (so the primary guard does not short-circuit), then settle WON -> the bridge catches 23505, returns `applied=False`, the whole tx rolls back (wallet + escrow exactly at post-placement, mirror still PENDING, no settle legs committed).
- **verification rejects mismatch**: `record_placed` on a non-PENDING bet; `record_settled` while live-bets still says PENDING; WON with no `payout` -> `LiveBetsVerificationError`, zero ledger effect.
- **server-side stake authority**: the request carries only `bet_id`; exactly the live-bets stake moves (and back on win).

### Task 2 — `test_migration_0011.py` (3 tests) + `test_livebets_router.py` (6 tests)
- **`test_migration_0011.py`** (SC2, sync — `pytest.mark.integration` only): drives Alembic against its **own throwaway `PostgresContainer`** (module-scoped), never the shared session-scoped `engine`. Asserts (1) `0011` chains from `0010_phase12_resolution_stakes`; (2) after `upgrade head` the `livebets_bets` table + its `livebets_bets_user_idx` exist and the `livebets_escrow` singleton row exists exactly once (system-owned, `kind=livebets_escrow`); (3) after `downgrade -1` both the table and the singleton are gone (then restores head on the isolated container). All psycopg2 engines explicitly disposed; only `DATABASE_URL_SYNC` is touched.
- **`test_livebets_router.py`** (SC1, via httpx ASGITransport, no Docker): all four `/api/live/*` routes (`POST /bets/{uuid}/placed`, `POST /bets/{uuid}/settled`, `POST /session`, `GET /tables`) return **401** unauthenticated (real `current_active_player` gate). With `current_active_player` + `get_livebets_client` overridden (a no-network `FakeLiveBetsClient`), `GET /tables` returns the faked catalog (200) and `POST /session` the faked token (200). Overrides cleared after every test.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] wave-1: `record_settled` performed DB reads before `session.begin()` (autobegin) — `begin()` raised on every settle**

- **Found during:** Task 1 — running `test_livebets_bridge.py` (the prior run's RED). The first `placed->won` test failed at the settle step.
- **Authorization:** Explicitly authorized by the task brief (the one specific wave-1 fix).
- **Issue:** In `LiveBetsBridge.record_settled` (`backend/app/integrations/livebets/service.py`), the mirror-row `select(LiveBetsBet)...`, the primary idempotency guard (`mirror.status != PENDING`), and `WalletService._resolve_user_wallet_id(...)` all ran **before** `async with session.begin():`. Those reads autobegin an implicit transaction on the `AsyncSession`, so the subsequent `session.begin()` raised:
  ```
  sqlalchemy.exc.InvalidRequestError: A transaction is already begun on this Session.
  ```
  Confirmed by the SQL trace (an implicit `BEGIN` → mirror `SELECT` → `_resolve_user_wallet_id` `SELECT` → `ROLLBACK`, then `begin()` blew up) and the exact exception at `session.py:1945`. This made **every** settled event (WON/LOST/REFUNDED/VOIDED) fail at runtime.
- **Fix (minimal — read-ordering only):** moved the mirror-row select, the primary idempotency guard, the `stake = mirror.stake` capture, the `_resolve_user_wallet_id` call, and the dependent leg-spec derivation **inside** the `async with session.begin():` block — exactly the ordering `record_placed` / `WalletService.recharge` / `WalletService.grant_signup_bonus` / `SettlementService.resolve_market` already use (begin first, then read/resolve). The non-DB `get_bet` verification (the `await client.get_bet(...)` + status check) correctly **stays before** `begin()`. The primary idempotency guard now early-returns from inside the block (committing an empty tx — a clean no-op). The `mirror is None` case raises from inside the block (rolls back, re-raises past the `except IntegrityError`). The 23505 secondary guard is unchanged structurally (`_post_transfer` raises `IntegrityError` inside `begin()`, caught at the `try` level, returns `status=verified.status`). **No ledger legs, idempotency keys, lock order, or any other logic changed.**
- **Before (abridged):**
  ```python
  verified = parse_verified_bet(await client.get_bet(str(bet_id)))
  if verified.status not in LIVEBETS_SETTLED_STATUSES: raise ...
  mirror = (await session.execute(select(LiveBetsBet)...)).scalar_one_or_none()   # <-- autobegins
  if mirror is None: raise ...
  if mirror.status != LIVEBETS_PENDING: return MirrorResult(..., applied=False)
  stake = mirror.stake
  wallet_id = await WalletService._resolve_user_wallet_id(session, user_id=user.id)  # <-- autobegins
  specs = [...]  # derived from wallet_id/stake
  try:
      async with session.begin():     # <-- InvalidRequestError: a transaction is already begun
          ... lock, post legs, flip mirror ...
  ```
- **After (abridged):**
  ```python
  verified = parse_verified_bet(await client.get_bet(str(bet_id)))   # non-DB, stays before begin()
  if verified.status not in LIVEBETS_SETTLED_STATUSES: raise ...
  try:
      async with session.begin():     # begin FIRST
          mirror = (await session.execute(select(LiveBetsBet)...)).scalar_one_or_none()
          if mirror is None: raise ...
          if mirror.status != LIVEBETS_PENDING: return MirrorResult(..., applied=False)  # empty-tx no-op
          stake = mirror.stake
          wallet_id = await WalletService._resolve_user_wallet_id(session, user_id=user.id)
          specs = [...]
          ... lock, post legs, flip mirror ...
  except IntegrityError as exc: ...  # unchanged 23505 secondary guard
  ```
- **Files modified:** `backend/app/integrations/livebets/service.py` (84 insertions, 73 deletions — pure re-indentation + comment updates; one method).
- **Commit:** `05a8086`
- **Verification that the fix is behavior-neutral elsewhere:** the regression suites (`tests/wallet tests/bets tests/settlement`) stay **130 passed** — the fix is confined to `record_settled` and changes only read ordering.

### Minor scope additions (Rule 3 — robustness, documented)

**2. Added `backend/tests/integrations/__init__.py`** (parent package marker, not in `files_modified`). Every test package in the project has an `__init__.py`; adding the parent guards against future basename-collision fragility under pytest's `prepend` import mode. Trivial empty file; suite is green with and without it.

**3. Isolated migration container + `DATABASE_URL_SYNC`-only env mutation + a targeted warning filter.** Not a plan deviation in substance (the plan explicitly allows the migration test to use its OWN `PostgresContainer`), but worth recording: an early version mutated the async `DATABASE_URL` and cleared the lazy engine caches, which leaked an asyncpg socket at session teardown (suite reported `21 passed` but exit code 1). Restricting the fixture to `DATABASE_URL_SYNC` (alembic is sync) and leaving the async engine untouched restored a clean **exit 0**. A module-level `filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning")` down-grades the benign alembic `NullPool` `Connection.__del__` GC warning to non-fatal without weakening any assertion.

## Authentication gates

None — no auth gates encountered (tests are hermetic; no external service login required).

## Verification

- **New suite:** `cd backend && uv run pytest tests/integrations/livebets -q` -> **21 passed** (exit 0).
- **Regression (zero behavior change, LB-A-SC2):** `cd backend && uv run pytest tests/wallet tests/bets tests/settlement -q` -> **130 passed** (exit 0).
- **Hermetic:** every test uses `FakeLiveBetsClient()` only; grep confirms no `LiveBetsClient()` / `LIVEBETS_API_BASE` / live base-URL call in the test files. The router test's `httpx.AsyncClient` targets only the in-process ASGI app (`base_url="http://test"`).

## Requirements satisfied

- **LB-A-SC6** — `pytest` green for the new module (placed->won, placed->lost, void/refund, duplicate no-op, escrow-nets-to-zero, verification-rejects-mismatch). ✅
- **LB-A-SC2** — migration applies + reverses cleanly; existing suites still pass (130). ✅
- **LB-A-SC4** — idempotency (both guards) + escrow-nets-to-zero proven by assertion. ✅
- **LB-A-SC5** — server-side verification proven (mismatch rejected without posting). ✅
- **LB-A-SC1** — all four `/api/live/*` routes reject unauthenticated requests (401). ✅

## Known stubs

None. No placeholder/empty-data stubs introduced; the test suite drives real ledger postings against real Postgres.

## Self-Check: PASSED

- `backend/tests/integrations/__init__.py` — FOUND
- `backend/tests/integrations/livebets/__init__.py` — FOUND
- `backend/tests/integrations/livebets/test_livebets_bridge.py` — FOUND
- `backend/tests/integrations/livebets/test_migration_0011.py` — FOUND
- `backend/tests/integrations/livebets/test_livebets_router.py` — FOUND
- Commit `05a8086` (fix) — FOUND
- Commit `c75d379` (Task 1 tests) — FOUND
- Commit `7fab2e4` (Task 2 tests) — FOUND
