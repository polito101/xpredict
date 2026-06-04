---
phase: 03-wallet-double-entry-ledger
plan: 05
subsystem: payments
tags: [wallet, reads, balance, transactions, pagination, money-as-string, pydantic, fastapi, cookie-auth, stripe-stub, nextjs, server-component, vitest]

# Dependency graph
requires:
  - phase: 03-wallet-double-entry-ledger
    plan: 04
    provides: "MoneyStr (Annotated[Decimal, PlainSerializer] — SC#4), RechargeRequest/Response, wallet_admin_router + app/main.py router-mount pattern, the HTTP-integration test discipline (own committed sessions + unique-email isolation + autouse rate-limit reset)"
  - phase: 03-wallet-double-entry-ledger
    plan: 02
    provides: "WalletService read seam (get_balance, _resolve_user_wallet_id), the recharge(payment_provider='stripe') -> NotImplementedError v2 stub (SC#6), the self-committing recharge used to seed history in tests"
  - phase: 03-wallet-double-entry-ledger
    plan: 01
    provides: "Account/Transfer/Entry ORM models (entries.account_id index, transfer.transfer_metadata JSONB), house_promo singleton, KIND_USER_WALLET/PLAY_USD/DIRECTION_* constants"
  - phase: 02-auth-identity
    provides: "current_active_player (CookieTransport, active+verified gate), /auth/register + /auth/login cookie flow, lib/auth.ts getBackendUrl + cookie-forwarding pattern, vitest + Testing Library config (environmentMatchGlobs)"
provides:
  - "GET /wallet/me/balance — cookie-gated, self-scoped player balance read (WAL-03); money as a JSON string (SC#4); no user_id param (cross-user read structurally impossible, T-03-18)"
  - "GET /wallet/me/transactions?page=&page_size= — cookie-gated, self-scoped paginated history (WAL-04): kind/amount(string)/direction/created_at/reason + page/page_size/total/has_next"
  - "WalletService.get_transactions — read-only offset pagination over the caller's own wallet entries joined to transfers (newest first) + total count"
  - "BalanceResponse / TransactionItem / TransactionPage schemas reusing MoneyStr (SC#4 money-as-string on every money field)"
  - "frontend /wallet page (Next.js Server Component): play balance + recent activity + a DISABLED 'Add funds' button (SC#6/PLT-05 Stripe stub), money rendered as the backend string (SC#4), English copy avoiding 'deposit' (PITFALLS #3)"
affects: [phase-05, phase-08, phase-09, settlement, admin-crm, user-app-ux]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Player read endpoints are self-scoped by structure: Depends(current_active_player) + NO user_id path/query param — the wallet is always player.id's own, so T-03-18 (cross-user read) is impossible at the route surface, not just guarded"
    - "Read-only WalletService methods (get_balance/get_transactions) use only select() — no add/update/flush/commit/begin in their bodies (grep-verifiable); the immutable ledger is never mutated by a read"
    - "Offset pagination: total = SELECT count() over entries WHERE account_id == wallet; rows = entries JOIN transfers ORDER BY created_at DESC, id DESC LIMIT page_size OFFSET (page-1)*page_size; has_next = page*page_size < total"
    - "FastAPI dependency-injected params (Annotated[User|AsyncSession, Depends(...)]) MUST NOT live in a module with 'from __future__ import annotations' on Python 3.13 — the stringified annotation makes FastAPI mis-resolve them as query params (422). Runtime-import the types; mirror admin_router.py (Plan 02-02 D-C)."
    - "Async Next.js Server Component is unit-tested by mocking next/headers cookies() + global fetch, then `render(await Page())` — fully offline; the testable seam without splitting the component"

key-files:
  created:
    - backend/app/wallet/router.py
    - backend/tests/wallet/test_money_serialization.py
    - backend/tests/wallet/test_stripe_stub.py
    - frontend/src/app/wallet/page.tsx
    - frontend/src/app/wallet/__tests__/wallet-page.test.tsx
  modified:
    - backend/app/wallet/schemas.py
    - backend/app/wallet/service.py
    - backend/app/main.py

key-decisions:
  - "wallet/router.py intentionally OMITS 'from __future__ import annotations' and runtime-imports User/AsyncSession — discovered via the Task 2 behavioral test (the injected player/session were mis-resolved as query params → 422). Identical constraint to admin_router.py (Plan 02-02 D-C / 03-04). Rule-1 fix."
  - "get_transactions paginates over ENTRIES (not transfers) joined to their parent transfer — an entry is the leg that touches the caller's wallet, so direction is meaningful per-row and the count matches what the user actually sees on their wallet (WAL-04)."
  - "The read endpoints catch NoResultFound (no wallet) and return a defensive balance 0 / empty page rather than 500 — registration guarantees a wallet (SC#1), so this is belt-and-braces, never the happy path."
  - "get_balance already existed (minimal seam from 03-02); 03-05 only documented it as the WAL-03 read and added get_transactions alongside — no rewrite of locked 03-02 writer code."
  - "Frontend page is a Server Component that fetches server-side with the forwarded session cookie (mirrors lib/auth.ts), degrading to zero/empty offline; the disabled 'Add funds' button lives INLINE in page.tsx (satisfies the must_haves 'contains: disabled' on that exact path) and the test mocks cookies()+fetch to run offline."

patterns-established:
  - "Self-scoped read surface template (no user_id param + current_active_player) — Phase 5 bet history / Phase 9 user app reads should reuse it so cross-user reads stay structurally impossible"
  - "Money-as-string proven on the WIRE for reads too: the SC#4 test asserts isinstance(...,str) AND a quoted-substring in response.text for balance and every history amount — the regression guard now covers the read surface, not just recharge"
  - "Server-Component unit test via render(await Page()) with next/headers + fetch mocked — the offline test pattern for any future authenticated server-rendered page"

requirements-completed: [WAL-03, WAL-04, PLT-05]

# Metrics
duration: ~10min
completed: 2026-05-27
---

# Phase 03 Plan 05: Player Wallet Reads + Stripe Stub Summary

**The player-facing read slice: `GET /wallet/me/balance` (WAL-03) + `GET /wallet/me/transactions` (WAL-04), both cookie-gated by `current_active_player` and strictly self-scoped (no `user_id` param — cross-user read is structurally impossible, T-03-18), with every money value serialized as a JSON string (SC#4, asserted on the raw wire); plus the Stripe door-open stub (SC#6/PLT-05) — `recharge(payment_provider="stripe")` raises `NotImplementedError` and a DISABLED "Add funds" button on the new Next.js `/wallet` page. This is the FINAL plan of Phase 3 (6/6).**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-05-27T16:26:59Z
- **Completed:** 2026-05-27T16:37:32Z
- **Tasks:** 3 (full-stack: backend reads + tests, frontend page + test)
- **Files modified:** 8 (5 created, 3 modified)

## Accomplishments
- **`GET /wallet/me/balance`** (`app/wallet/router.py`) — the authenticated player's own wallet balance (WAL-03):
  - **Cookie-gated (T-03-18):** `Depends(current_active_player)` (the Phase 2 `active=True, verified=True` cookie gate). An unauthenticated request returns 401 (proven by `test_player_cannot_read_without_auth`).
  - **Self-scoped by structure:** NO `user_id` path/query parameter — the wallet is always `player.id`'s own, so a client cannot name another user's wallet on the wire (cross-user read is impossible, not merely guarded).
  - **Money-as-string (SC#4):** `BalanceResponse.balance` uses `MoneyStr`; the raw JSON carries `"balance":"100.0000"` (a quoted string), never a float.
- **`GET /wallet/me/transactions?page=&page_size=`** — a paginated history of the caller's own wallet (WAL-04): each item is `{kind, amount(string), direction, created_at, reason}` and the page carries `page/page_size/total/has_next`. Offset pagination over `entries` (the legs that touch the caller's wallet) joined to their parent `transfer`, newest first. `page` is `Query(ge=1)`, `page_size` is `Query(50, ge=1, le=200)`.
- **`WalletService.get_transactions`** (`app/wallet/service.py`) — the read-only paginator: resolves the caller's wallet id, counts its entries, then selects one page joined to transfers. Uses only `select()` — no `add`/`update`/`flush`/`commit`/`begin` (grep-verified read-only). `get_balance` (the minimal 03-02 seam) is now documented as the WAL-03 read.
- **`BalanceResponse` / `TransactionItem` / `TransactionPage`** (`app/wallet/schemas.py`) — read projections reusing the same `MoneyStr` money-as-string contract (no redefinition). Extended the module without touching the 03-04 recharge schemas.
- **`app/main.py`** — `wallet_router` mounted next to the 03-04 admin router; all prior routes intact (`/auth`, `/admin/auth`, `/admin/wallets`, `/healthz`, …) and the two new `/wallet/me/*` routes registered + listed.
- **SC#6 / PLT-05 Stripe stub** — `test_stripe_stub.py` proves `WalletService.recharge(payment_provider="stripe")` raises `NotImplementedError` as a FAST UNIT test (no Docker), so SC#6 lives in the `-m "not integration"` quick run. The frontend `/wallet` page carries a DISABLED "Add funds" button + "Coming soon" caption (the Stripe affordance is present but inert; v2 enables it behind the `stripe_recharge_enabled` flag, seeded FALSE in Phase 1).
- **`frontend/src/app/wallet/page.tsx`** — a Next.js Server Component showing the play balance (in `PLAY_USD`), recent activity (WAL-04) with an empty state, and the disabled "Add funds" button (SC#6). Money is rendered as the backend STRING (never parsed to a JS number — SC#4 precision); copy is English and avoids "deposit" (PITFALLS #3). Server-side fetch forwards the `xpredict_session` cookie (mirrors `lib/auth.ts`) and degrades to zero/empty offline.
- **Behavioral proof:** `test_money_serialization.py` (4 integration) + `test_stripe_stub.py` (2 unit) = 6 green; full `tests/wallet` = **35 passed**; project-wide non-integration regression = **65 passed / 2 skipped** (up from 63 in 03-04 — no regressions); `ruff check app/wallet/ app/main.py tests/wallet/` clean. Frontend `wallet-page.test.tsx` = 2 green; full frontend suite = **29 passed** (27 baseline + 2 new), the only failed suite being the pre-existing `middleware.test.ts` (DEF-FE-01, out of scope, untouched); `tsc --noEmit` clean except that same pre-existing error.

## Task Commits

Each task was committed atomically:

1. **Task 1: player read schemas + WalletService.get_transactions + wallet_router + main wiring** — `8d58b03` (feat)
2. **Task 2: SC#4 money-as-string reads + SC#6 Stripe-stub tests** — `62758c6` (test; carries the Rule-1 future-import fix to the Task 1 router — see Deviations)
3. **Task 3: player /wallet page with a disabled "Add funds" button** — `645956e` (feat)

**Plan metadata:** _(this SUMMARY + STATE + ROADMAP + REQUIREMENTS — final docs commit)_

_Note: Tasks 1-2 carried `tdd="true"`. As in 03-02 / 03-04, the plan splits the feature so Task 1 is the implementation and Task 2 the behavioral test suite that exercises it; the genuine RED→GREEN proof lives in Task 2 (it surfaced a real production bug in the Task 1 router — the FastAPI future-import 422 — fixed as a deviation before the suite went green). The plan is `type: execute` (not plan-level `type: tdd`), so the per-plan RED/GREEN/REFACTOR gate-commit sequence does not apply; commits are `feat` (Tasks 1, 3) + `test` (Task 2)._

## Files Created/Modified
- `backend/app/wallet/router.py` (created) — `wallet_router` (`prefix="/wallet/me"`): `GET /balance` (→ `BalanceResponse`) + `GET /transactions` (→ `TransactionPage`), both `Depends(current_active_player)` + `Depends(get_async_session)`, no `user_id` param, `NoResultFound` → defensive 0/empty. Intentionally no `from __future__ import annotations` (see Deviations).
- `backend/app/wallet/schemas.py` (modified) — added `BalanceResponse` (`balance: MoneyStr`, `currency`), `TransactionItem` (`kind`, `amount: MoneyStr`, `direction`, `created_at: datetime`, `reason: str | None`), `TransactionPage` (`items`, `page`, `page_size`, `total`, `has_next`); reuses the existing `MoneyStr`. Imported `datetime`. 03-04 recharge schemas untouched.
- `backend/app/wallet/service.py` (modified) — added `get_transactions(session, *, user_id, page=1, page_size=50) -> tuple[list, int]` (read-only paginator); documented `get_balance` as the WAL-03 read. Imported `func`.
- `backend/app/main.py` (modified) — `from app.wallet.router import wallet_router` + `app.include_router(wallet_router)` (2 lines; nothing else touched).
- `backend/tests/wallet/test_money_serialization.py` (created) — 4 integration tests: balance is a JSON string (SC#4), every history amount is a string, pagination disjoint + correct `has_next` (WAL-04), unauthenticated read → 401 (T-03-18). Drives the live app + testcontainer; seeds history via the 03-04 admin recharge endpoint; autouse rate-limit reset + `engine` side-effect fixture.
- `backend/tests/wallet/test_stripe_stub.py` (created) — 2 fast UNIT tests (no Docker): `recharge(payment_provider="stripe")` raises `NotImplementedError` (SC#6) + the `PROVIDER_STRIPE` literal guard.
- `frontend/src/app/wallet/page.tsx` (created) — the player wallet Server Component (balance + history + disabled "Add funds").
- `frontend/src/app/wallet/__tests__/wallet-page.test.tsx` (created) — 2 Vitest + Testing Library tests: the "Add funds" button is `toBeDisabled()` and the balance/currency region renders, offline (cookies() + fetch mocked); live-data path + offline-fallback path; asserts copy has no "deposit".

## Decisions Made
- **`wallet/router.py` omits `from __future__ import annotations`.** On Python 3.13, FastAPI's `inspect.signature` dependency resolver mis-handles `Annotated[User, Depends(...)]` when the annotation is a forward-ref string — the injected `player`/`session` params were resolved as **query** params and the endpoint returned `422 {"loc":["query","player"],"msg":"Field required"}`. The fix (and the codebase's documented constraint, `admin_router.py` lines 22-26 / Plan 02-02 D-C) is to omit the future-import and runtime-import `User` + `AsyncSession`. This was caught by the Task 2 behavioral test (RED→GREEN). (Deviation Rule 1.)
- **Pagination is over `entries`, not `transfers`.** A transfer can touch two accounts; the row the player cares about is the *entry* leg that hit *their* wallet (it carries the per-row `direction`). Counting/paginating entries makes `total` match what the user sees and keeps `direction` meaningful. (WAL-04.)
- **Defensive `NoResultFound` → 0 / empty page.** Registration co-creates the wallet (SC#1), so a player with no wallet should not occur; the handlers still degrade gracefully rather than 500 (belt-and-braces).
- **`get_balance` reused, not rewritten.** The minimal read seam shipped in 03-02; 03-05 documented it as the WAL-03 read and only *added* `get_transactions` — no change to the locked 03-02 writer/concurrency code.
- **Frontend is a Server Component with an inline disabled button.** The must_haves require `page.tsx` to literally `contain: "disabled"`, so the SC#6 button lives inline (not in a split child); the test mocks `next/headers` `cookies()` + global `fetch` and renders `await WalletPage()` to stay fully offline. Money is rendered as the backend string (never `Number(...)`) to preserve `NUMERIC(18,4)` precision (PITFALLS #4).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `wallet/router.py` `from __future__ import annotations` made FastAPI mis-resolve the injected dependencies as query params (422)**
- **Found during:** Task 2 (the first integration test, `test_balance_is_json_string`, got `422 {"loc":["query","player"],"msg":"Field required"}` instead of 200)
- **Issue:** The router was authored with `from __future__ import annotations` and imported `User` / `AsyncSession` only under `TYPE_CHECKING`. With the future-import, the `Annotated[User, Depends(current_active_player)]` / `Annotated[AsyncSession, Depends(get_async_session)]` annotations become forward-ref **strings**; FastAPI's signature resolver on Python 3.13 then fails to recognise them as `Depends` and treats `player`/`session` as required **query** parameters — every read 422'd before the handler ran. This is the exact constraint the shipped `admin_router.py` documents (lines 22-26, Plan 02-02 D-C) and deliberately avoids.
- **Fix:** Removed `from __future__ import annotations` from `app/wallet/router.py` and moved `User` + `AsyncSession` (and `Decimal`) to runtime imports.
- **Files modified:** backend/app/wallet/router.py
- **Verification:** `inspect.signature(endpoint)` shows `player`/`session` as proper params; all 4 money-serialization integration tests + the route-listing assert green; ruff clean.
- **Committed in:** `62758c6` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (a bug in the Task 1 router, caught by running the Task 2 behavioral suite — the RED→GREEN proof). No schema, migration, or external-contract change; the route paths, request/response shapes, and method signatures are exactly as the plan specified.
**Impact on plan:** The fix was necessary to make the plan's own verification pass on production code (the read endpoints 422'd without it). It changes only the module's import form, not its behavior surface.

## Issues Encountered
- **The route-listing verify command needs the test env vars.** `uv run python -c "from app.main import app ..."` fails with a `Settings` validation error outside pytest because `app.auth.rate_limit` instantiates `Settings()` at import and the DB/Redis/SECRET_KEY env vars aren't set. Verified the import by passing the same `_DEFAULT_TEST_ENV` values `tests/conftest.py` seeds (DATABASE_URL / DATABASE_URL_SYNC / REDIS_URL / SECRET_KEY / SLOWAPI_STORAGE_URI / FRONTEND_BASE_URL / ENVIRONMENT) inline — routes confirmed registered. Not a code issue; the plan's bare verify command assumed those env vars were present.
- **SQLAlchemy `echo` floods test output in dev.** `app/db/session.py` sets `echo=settings.is_dev`, so the testcontainer runs print every statement; the real assertion was buried. Ran the failing test with output filtered to surface the 422 traceback. No fix needed (dev-only echo).
- **`ResourceWarning: unclosed socket`** prints after the integration suite — the known testcontainers Docker-probe teardown artifact (also in 03-01/02/04), not a failure; every suite reports green.
- **DEF-03-01 honored:** backend verification used per-file / per-directory runs (`tests/wallet`) + `-m "not integration"`, never the whole-suite single-process run that cascade-fails on the pre-existing `tests/core/test_audit_immutability.py` session poisoning (Phase 1 file, out of scope).
- **DEF-FE-01 honored:** the pre-existing failing frontend suite `src/__tests__/middleware.test.ts` (Phase 2 — a test was added for a `middleware.ts` that does not exist) was NOT touched. It remains the only failing frontend suite and the only `tsc` error; my work added 2 passing tests with zero new failures.

## User Setup Required
None — no external service configuration. The reads are served from the existing ledger; the Stripe top-up remains the v2 stub behind the already-seeded `stripe_recharge_enabled=FALSE` flag (no Stripe key/secret needed). The frontend `/wallet` page reads `BACKEND_URL` from the server env (defaults to `http://localhost:8000` in dev).

## Known Stubs
- **`WalletService.recharge(payment_provider="stripe")` → `NotImplementedError`** and the **DISABLED "Add funds" button** are the intentional, plan-mandated SC#6 / PLT-05 stub — the "door is open" for v2 (the method signature + the UI affordance exist now; enabling real Stripe needs no breaking refactor, only flipping `stripe_recharge_enabled` and replacing the raise). NOT goal-blocking: the v1 wallet read capability (balance + history) is fully wired to live ledger data.
- **No data stub on the read path:** `/wallet/me/balance` + `/wallet/me/transactions` return real values from the committed ledger; the frontend page fetches them server-side. The page's zero/empty *fallback* fires only when the backend is unreachable or the session cookie is absent (defensive degradation, not a hardcoded placeholder) — a follow-up phase (User App UX, Phase 9) can harden this into a redirect to `/login`.

## Next Phase Readiness
- **Phase 3 is COMPLETE (6/6).** The wallet domain now has: the ledger schema (03-01), the race-safe writer (03-02), registration auto-provisioning (03-03), the admin recharge endpoint + SC#5 firewall (03-04), the nightly reconciliation safety net (03-06), and — this plan — the player read surface (WAL-03/WAL-04) + the float firewall on reads (SC#4) + the Stripe door-open stub (SC#6/PLT-05).
- **Phase 5 (bets/settlement):** reuses `WalletService.transfer` for stake debits / payout credits; the self-scoped read template here is the pattern for a bet-history endpoint; `MoneyStr` is the money-as-string contract every new wallet response inherits.
- **Phase 8 (admin CRM):** the admin can already recharge (03-04); a player-balance read for the CRM would reuse `WalletService.get_balance` / `get_transactions` behind the admin gate (note: those CRM reads WILL take a `user_id` and must be admin-gated — the player surface here is deliberately self-scoped only).
- **Phase 9 (user app UX):** the `/wallet` page is the seam to polish — wire the offline fallback into a real `/login` redirect, add loading/error states, and surface pagination controls.
- No blockers.

---
*Phase: 03-wallet-double-entry-ledger*
*Completed: 2026-05-27*

## Self-Check: PASSED

All 5 created files verified present on disk (`app/wallet/router.py`, `tests/wallet/test_money_serialization.py`, `tests/wallet/test_stripe_stub.py`, `frontend/src/app/wallet/page.tsx`, `frontend/src/app/wallet/__tests__/wallet-page.test.tsx`) plus this SUMMARY; the 3 modified files (`app/wallet/schemas.py`, `app/wallet/service.py`, `app/main.py`) carry their changes. All three task commits (`8d58b03`, `62758c6`, `645956e`) verified in git history. Plan verification gates all pass: `ruff check app/wallet/ app/main.py tests/wallet/` clean; `pytest tests/wallet/test_money_serialization.py tests/wallet/test_stripe_stub.py -q` → 6 passed (Docker); `pytest -m "not integration" tests/wallet -q` → 6 passed including the Stripe-stub unit test (no Docker); full `tests/wallet` → 35 passed; project-wide `-m "not integration"` → 65 passed / 2 skipped (no regressions); the route table contains `/wallet/me/balance` + `/wallet/me/transactions` behind `current_active_player`. Frontend: `vitest run src/app/wallet` → 2 passed; full frontend suite → 29 passed (27 baseline + 2 new), the only failed suite being the pre-existing `middleware.test.ts` (DEF-FE-01, untouched); `tsc --noEmit` clean except that same pre-existing error.
