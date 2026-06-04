---
phase: 03-wallet-double-entry-ledger
plan: 04
subsystem: payments
tags: [wallet, recharge, admin, fastapi, idempotency, money-as-string, pydantic, audit, regulatory-firewall, bearer-auth]

# Dependency graph
requires:
  - phase: 03-wallet-double-entry-ledger
    plan: 02
    provides: "WalletService.recharge (house->user, idempotent via 23505->return-existing, canonical lock order, stripe stub), PROVIDER_HOUSE constant, _resolve_user_wallet_id (scalar_one -> NoResultFound when no wallet)"
  - phase: 03-wallet-double-entry-ledger
    plan: 01
    provides: "Account/Transfer/Entry ORM models, transfers.idempotency_key UNIQUE, entries.account_id FK -> accounts only, house_promo singleton (1e9 opening balance), funded_wallet pattern, OWNER_USER/KIND_USER_WALLET/DIRECTION_* constants"
  - phase: 02-auth-identity
    provides: "current_active_admin (BearerTransport + is_superuser gate, AUTH-07), admin Bearer login at /admin/auth/login, slowapi rate-limit reset pattern, cross-surface isolation (player cookie != admin)"
  - phase: 01-scaffold-foundations
    provides: "AuditService.record caller-owned-tx contract, get_async_session request-session dependency, testcontainers engine/_get_session_maker fixtures, app/main.py router-mount pattern, Settings()-at-import"
provides:
  - "POST /admin/wallets/{user_id}/recharge — the FIRST money-moving endpoint: admin-only (current_active_admin), Idempotency-Key required (400 if absent), debits house_promo + credits the path user only, audited (wallet.recharge), money-as-string response"
  - "RechargeRequest (extra=forbid, amount gt=0, reason required) — the SC#5/WAL-09 firewall at the schema boundary: no destination field, any dst_user_id is a hard 422"
  - "RechargeResponse with MoneyStr (Annotated[Decimal, PlainSerializer]) — SC#4 money-as-string contract, regression-proof against a future float change; idempotent_replay flag"
  - "SC#5 negative-test guard at three layers (schema / route-inventory / Entry FK) proving no user-to-user transfer path exists — runs in the quick non-integration pass (no Docker)"
affects: [03-05, phase-05, phase-08, wallet-reads, settlement, admin-crm, recharge]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "MoneyStr = Annotated[Decimal, PlainSerializer(lambda v: str(v), return_type=str, when_used='json')] — explicit defense-in-depth money-as-string (SC#4); the SC#4 test asserts on raw JSON text, never the parsed value"
    - "Idempotency-Key via Annotated[str | None, Header()] = None (FastAPI maps underscore->hyphen); a missing key is a 400 (client must supply it, Assumption A3) — never server-generated"
    - "RechargeRequest model_config = ConfigDict(extra='forbid') as a regulatory firewall AT THE SCHEMA BOUNDARY — a dst_user_id-style param is a hard 422, making SC#5/WAL-09 observable on the wire (PITFALLS #3)"
    - "Endpoint built on a self-committing service: recharge owns its session.begin(), so the request handler rollback()s its own pre-read tx before calling recharge, then audits + commits AFTER — action-then-audit, mirroring the auth surface (NOT same-tx-as-transfer, see Decisions)"
    - "Capture ORM ids (admin.id, transfer.id) into plain variables BEFORE any rollback/begin/commit churn on the request session — post-churn attribute access triggers a lazy reload outside the async greenlet (MissingGreenlet)"

key-files:
  created:
    - backend/app/wallet/schemas.py
    - backend/app/wallet/admin_router.py
    - backend/tests/wallet/test_recharge.py
    - backend/tests/wallet/test_no_user_to_user.py
  modified:
    - backend/app/main.py

key-decisions:
  - "Audit is action-THEN-audit (recharge commits the transfer atomically via its own session.begin(), then the handler writes the wallet.recharge audit row on the request session and commits) — NOT same-tx-as-transfer. The shipped 03-02 recharge is self-committing; rewriting it to caller-owned-tx would touch its validated SC#2 concurrency invariants (Rule 4 territory). The auth surface uses the same independent action-then-audit pattern (Pitfall 9 doctrine)."
  - "idempotent_replay is detected by a pre-read SELECT on transfers.idempotency_key before recharge; that read autobegins a tx so the handler rollback()s it before recharge's session.begin() (or recharge raises InvalidRequestError — the same autobegin nuance 03-02 documented)"
  - "current_active_admin imported from app.auth.deps (the lazy __getattr__ re-export), not app.auth.admin_router directly — the documented consumer path that breaks the import cycle"
  - "Map _resolve_user_wallet_id's scalar_one() NoResultFound -> 404, InsufficientBalance/ValueError -> 400; the schema's amount gt=0 + extra=forbid catch most bad input as 422 before the service is reached"

patterns-established:
  - "HTTP-integration tests for self-committing endpoints: drive the app over its own request session, assert against committed state via _get_session_maker() sessions, isolate by a UNIQUE email + UNIQUE idempotency key per test (the immutable ledger is never deleted; scope assertions to the run's own wallet/key — the 03-02 discipline)"
  - "accounts.owner_id is a plain column (NOT a FK to users), so test cleanup deletes the user row only and leaves the immutable wallet/entries behind — no FK block, no immutable-row delete attempt"
  - "Autouse slowapi rate-limit reset is required in any test module that registers/logs-in repeatedly from 127.0.0.1 — tests/auth/conftest.py's reset is NOT inherited by tests/wallet"
  - "SC#5 firewall is a permanent three-layer regression guard (schema extra=forbid / route inventory / Entry.account_id FK targets accounts only), with at least the unit layer running without Docker"

requirements-completed: [WAL-09]

# Metrics
duration: ~13min
completed: 2026-05-27
---

# Phase 03 Plan 04: Admin Recharge Endpoint + SC#5 Firewall Summary

**`POST /admin/wallets/{user_id}/recharge` — the first money-moving endpoint: admin-Bearer-gated, `Idempotency-Key`-required, debiting `house_promo` and crediting the path user via the validated `WalletService.recharge`, money serialized as a JSON string, every recharge audited — plus the SC#5/WAL-09 regulatory firewall (`extra="forbid"`, no destination field, no Entry FK to a second user wallet) proven at the schema, route, and ORM layers.**

## Performance

- **Duration:** ~13 min
- **Started:** 2026-05-27T16:01:06Z
- **Completed:** 2026-05-27T16:13:40Z
- **Tasks:** 3
- **Files modified:** 5 (4 created, 1 modified)

## Accomplishments
- **`POST /admin/wallets/{user_id}/recharge`** (`app/wallet/admin_router.py`) — the FIRST money-moving endpoint:
  - **Admin-only (T-03-13 / AUTH-07):** `Depends(current_active_admin)` (Bearer + `is_superuser`). A player cookie or no auth → 401/403.
  - **Idempotent (SC#3 / T-03-14):** the client supplies `Idempotency-Key` (a missing key is a 400 — A3); `WalletService.recharge` dedups a replayed key (23505 → return existing). A pre-read shapes the `idempotent_replay` flag — same id, no double-credit.
  - **No user-to-user (SC#5 / WAL-09):** debits `house_promo`, credits the path user only; the debit source is chosen server-side, never from the body.
  - **Audited (T-03-17):** every recharge writes a `wallet.recharge` audit row (target user, amount, key, replay flag).
- **`RechargeRequest` / `RechargeResponse`** (`app/wallet/schemas.py`) — `RechargeRequest` is `extra="forbid"` with `amount: Decimal = Field(gt=0)` + required `reason` and **no destination field of any kind** (the SC#5 firewall at the wire surface); `RechargeResponse` returns the transfer id, `amount` as a `MoneyStr` JSON string (SC#4), `currency`, and `idempotent_replay`.
- **`app/main.py`** — `wallet_admin_router` mounted next to the existing includes; all 22 prior routes (`/auth`, `/admin/auth`, `/healthz`, …) intact.
- **SC#5 three-layer firewall guard** (`tests/wallet/test_no_user_to_user.py`) — schema (`extra="forbid"` → 422), route inventory (no destination-user param; recharge names at most one user), and ORM (`Entry.account_id` FK targets `accounts` only) — the unit layer runs without Docker.
- **Behavioral proof:** `tests/wallet/test_recharge.py` (6 tests) + `test_no_user_to_user.py` (5 tests) green; full `tests/wallet` = **29 passed**; project-wide non-integration regression = **63 passed / 2 skipped** (up from 59 in 03-02 — no regressions); `ruff check app/wallet/ app/main.py` clean.

## Task Commits

Each task was committed atomically:

1. **Task 1: RechargeRequest/Response schemas + recharge endpoint + main wiring** — `579a18a` (feat)
2. **Task 2: Recharge integration tests (idempotency, auth gate, money-as-string)** — `b230453` (test; carries the two Rule-1 fixes to the Task 1 endpoint — see Deviations)
3. **Task 3: SC#5 no-user-to-user firewall negative test (API + route + schema)** — `9dc15c6` (test)

**Plan metadata:** _(this SUMMARY + STATE + ROADMAP + REQUIREMENTS — final docs commit)_

_Note: All three tasks carried `tdd="true"`. As in 03-02, the plan splits the feature so Task 1 is the implementation and Tasks 2-3 are the behavioral test suites that exercise it; the genuine RED→GREEN proof lives in Task 2 (it surfaced two real production bugs in the Task 1 endpoint, fixed as deviations before the suite went green). The plan is `type: execute` (not plan-level `type: tdd`), so the per-plan RED/GREEN/REFACTOR gate-commit sequence does not apply; commits are `feat` (Task 1) + `test` (Tasks 2-3)._

## Files Created/Modified
- `backend/app/wallet/schemas.py` — `MoneyStr` (Annotated Decimal + PlainSerializer, SC#4), `RechargeRequest` (`extra="forbid"`, `amount gt=0`, `reason`; NO destination field — SC#5), `RechargeResponse` (`transfer_id`, `amount: MoneyStr`, `currency`, `idempotent_replay`). Includes a `__main__` import smoke for the verify step.
- `backend/app/wallet/admin_router.py` — `wallet_admin_router` (`prefix="/admin/wallets"`) with `POST /{user_id}/recharge`: admin gate, `Idempotency-Key` Header (400 if absent), pre-read replay detection + `rollback()`, `WalletService.recharge(payment_provider="house")`, exception mapping (NoResultFound→404, InsufficientBalance/ValueError→400), `AuditService.record("wallet.recharge")` + commit, `RechargeResponse`.
- `backend/app/main.py` — import + `app.include_router(wallet_admin_router)` (2 lines added; nothing else touched).
- `backend/tests/wallet/test_recharge.py` — 6 integration tests (credits-wallet, idempotent-same-key, different-key, requires-admin, missing-key→400, amount-is-string) over the live app/testcontainer, plus an autouse rate-limit reset.
- `backend/tests/wallet/test_no_user_to_user.py` — 4 unit (schema/inventory/ORM, no Docker) + 1 integration (live 422) SC#5/WAL-09 firewall guards.

## Decisions Made
- **Audit is action-THEN-audit, not same-tx-as-transfer.** The plan's Task 1 action says "call `recharge`, then `AuditService.record` in the SAME session, then `commit`" — which assumes a caller-owned-tx recharge. But the **shipped 03-02 `recharge` is self-committing** (it owns `async with session.begin()`, which commits the transfer atomically with its double-entry). So the realised flow is: `recharge` commits the transfer (the money-correctness invariant — atomic, idempotent, race-safe), then the handler writes the `wallet.recharge` audit row on the request session and commits it. This **mirrors the codebase's own auth surface** (`app/auth/admin_router.py` writes audit in an independent step after the self-committing strategy, Pitfall 9 doctrine). Rewriting `recharge` to caller-owned-tx to make audit literally same-transaction would touch its validated SC#2 concurrency invariants — an architectural change to locked code (Rule 4), explicitly avoided. The transfer + audit are still both durably recorded; only the commit boundary differs from the plan's wording. (See Deviation note below.)
- **`idempotent_replay` via a pre-read.** A `SELECT transfers.id WHERE idempotency_key = ?` before the write distinguishes a fresh apply from a replay (the service returns a `Transfer` either way with no flag). That read autobegins a tx, so the handler `rollback()`s it before `recharge`'s `begin()`.
- **`current_active_admin` from `app.auth.deps`** (the lazy `__getattr__` re-export), the documented consumer path that breaks the `admin_router` ↔ `deps` import cycle.
- **Exception → status mapping:** `NoResultFound` (no wallet for the target user, from `_resolve_user_wallet_id`'s `scalar_one()`) → 404; `InsufficientBalance` / `ValueError` → 400. Most bad input (`amount <= 0`, unknown fields) is a 422 from the schema before the service runs.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Pre-read autobegan a transaction, colliding with `recharge`'s `session.begin()`**
- **Found during:** Task 2 (running `test_recharge_credits_wallet` — the first behavioral test returned 500)
- **Issue:** The handler's `idempotent_replay` pre-read (`session.execute(select(Transfer.id)...)`) runs on the request session and **autobegins an implicit transaction**. `WalletService.recharge` then opens its own `async with session.begin()`, which raised `sqlalchemy.exc.InvalidRequestError: A transaction is already begun on this Session` (service.py:223) — every recharge 500'd before doing any work. This is the identical autobegin nuance the 03-02 SUMMARY documented for resolve-before-begin.
- **Fix:** `await session.rollback()` immediately after the read-only pre-read (it wrote no data) so `recharge` is handed a clean session.
- **Files modified:** backend/app/wallet/admin_router.py
- **Verification:** isolated probe → `recharge: 200`; then `test_recharge_credits_wallet` green.
- **Committed in:** `b230453` (Task 2 commit)

**2. [Rule 1 - Bug] `MissingGreenlet` on `admin.id` / `transfer.id` after the session churn**
- **Found during:** Task 2 (the recharge then 500'd at the audit/response step)
- **Issue:** The `rollback()` (fix #1) plus `recharge`'s own `begin()/commit()` churn the request session's transaction state, which **expires ORM instances loaded earlier on that session** — notably the `admin` object from the `current_active_admin` dependency. Accessing `admin.id` (and later `transfer.id`) then triggered a lazy reload — IO outside the async greenlet → `sqlalchemy.exc.MissingGreenlet` (admin_router.py:127).
- **Fix:** Capture `admin_id = admin.id` at the TOP of the handler (before any rollback/begin) and `transfer_id = transfer.id` immediately after `recharge` returns (before the audit commit); use the plain values in the audit payload and the response.
- **Files modified:** backend/app/wallet/admin_router.py
- **Verification:** probe → `recharge: 200 {"transfer_id":"…","amount":"100.0000",…}`; all 6 recharge tests green.
- **Committed in:** `b230453` (Task 2 commit)

**3. [Rule 3 - Blocking] Missing slowapi rate-limit reset in the wallet test module**
- **Found during:** Task 2 (the 6th test, `test_recharge_amount_is_string_in_json`, hit a 429 on `/auth/register`)
- **Issue:** Each recharge test registers a player (`/auth/register`, 5/min per-IP) and logs an admin in (`/admin/auth/login`, 5/min per-IP) from 127.0.0.1. The shared `memory://` rate-limit counter accumulates across tests, so a later register/login trips a 429. The autouse reset fixture exists in `tests/auth/conftest.py` but is **not inherited** by `tests/wallet`.
- **Fix:** Added an autouse `_reset_rate_limit_storage` fixture to `test_recharge.py` (and an inline reset to the SC#5 integration test) mirroring the auth conftest's reset.
- **Files modified:** backend/tests/wallet/test_recharge.py (+ tests/wallet/test_no_user_to_user.py)
- **Verification:** full `tests/wallet/test_recharge.py` → 6 passed.
- **Committed in:** `b230453` / `9dc15c6` (test commits)

---

**Total deviations:** 3 auto-fixed (2 bugs in the Task 1 endpoint, 1 blocking test-infra). Plus 1 design clarification (audit boundary — see Decisions; not a deviation in behavior, a reconciliation of the plan's wording with the shipped self-committing 03-02 service).
**Impact on plan:** Both bugs were necessary to make the plan's own verification pass on production code (the endpoint 500'd without them) and were caught by running the behavioral suite (the RED→GREEN proof). The audit-boundary clarification preserves the validated 03-02 concurrency invariants rather than rewriting locked code. No schema, migration, or external-contract change; the endpoint surface, request/response shape, and route path are exactly as the plan specified.

## Issues Encountered
- **`recharge` is self-committing, so "audit in the same tx as the transfer" (plan Task 1 action / threat T-03-17) is not literally achievable without rewriting the validated 03-02 service.** Resolved by the action-then-audit pattern (recharge commits the transfer; audit commits immediately after on the request session) — consistent with the codebase's auth surface. The transfer and audit are both durably recorded; the only difference from the plan's wording is the commit boundary. Documented above as a Decision.
- **Surfacing the endpoint 500's root cause needed a probe.** With `raise_app_exceptions=False` (the test transport default) the app swallows handler exceptions into a 500 response, so pytest never showed the `InvalidRequestError`/`MissingGreenlet` traceback. A throwaway probe script with `raise_app_exceptions=True` surfaced both, after which the fixes were obvious. The probe was deleted before committing.
- **`ResourceWarning: unclosed socket`** prints after the integration suite — the known testcontainers Docker-probe teardown artifact (also in 03-01/02 + audit suites), not a failure; every suite reports green.
- **DEF-03-01 honored:** verification used per-file / per-directory runs (`tests/wallet`) plus `-m "not integration"`, never the whole-suite single-process run that cascade-fails on the pre-existing `tests/core/test_audit_immutability.py` session poisoning. Not touched (Phase 1 file, out of scope).

## User Setup Required
None — no external service configuration required. The recharge endpoint funds from the seeded `house_promo` singleton; no Stripe/secret/env addition (Stripe remains the 03-02 v2 stub behind the already-seeded `stripe_recharge_enabled=FALSE` flag).

## Known Stubs
None introduced by this plan. (The pre-existing `WalletService.recharge(payment_provider="stripe")` → `NotImplementedError` is an intentional 03-02 v2 stub, documented there; the v1 `payment_provider="house"` path this endpoint uses is fully implemented.) No empty/mock data flows to any surface — the endpoint returns the real transfer id + amount from the committed ledger.

## Next Phase Readiness
- The first money-moving endpoint is live, idempotent, admin-only, audited, and money-as-string — the SC#3/SC#4/SC#5 surface for the wallet domain.
- **03-05 (wallet reads):** owns `GET` balance/transactions shaping; it can reuse `MoneyStr` from `app/wallet/schemas.py` directly for SC#4 and follow the same admin/player auth-gate + HTTP-integration test patterns established here.
- **Phase 5 (bets/settlement):** the `WalletService.transfer` primitive (03-02) plus this audit-on-money-action pattern are the template for stake debits / payout credits; the SC#5 firewall (no user-to-user) is now a permanent regression guard any new wallet-mutation surface must satisfy.
- **Phase 8 (admin CRM):** the recharge endpoint is the "recargar saldo" CRM action (PROJECT Active requirement) — wired and ready behind admin auth.
- No blockers.

---
*Phase: 03-wallet-double-entry-ledger*
*Completed: 2026-05-27*

## Self-Check: PASSED

All 4 created files verified present on disk (`app/wallet/schemas.py`, `app/wallet/admin_router.py`, `tests/wallet/test_recharge.py`, `tests/wallet/test_no_user_to_user.py`) plus this SUMMARY; the 1 modified file (`app/main.py`) carries the router include. All three task commits (`579a18a`, `b230453`, `9dc15c6`) verified in git history. Plan verification gates all pass: `ruff check app/wallet/ app/main.py` clean; `pytest tests/wallet/test_recharge.py tests/wallet/test_no_user_to_user.py -q` → 11 passed (Docker); `pytest -m "not integration" tests/wallet -q` → 4 passed (SC#5 schema/inventory/ORM, no Docker); full `tests/wallet` → 29 passed; project-wide `-m "not integration"` → 63 passed / 2 skipped (no regressions); route table contains `POST /admin/wallets/{user_id}/recharge` behind `current_active_admin`.
