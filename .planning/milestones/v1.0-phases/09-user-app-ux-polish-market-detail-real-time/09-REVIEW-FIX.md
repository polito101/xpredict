---
phase: 09-user-app-ux-polish-market-detail-real-time
fixed_at: 2026-05-29T00:00:00Z
review_path: .planning/phases/09-user-app-ux-polish-market-detail-real-time/09-REVIEW.md
iteration: 1
findings_in_scope: 10
fixed: 10
skipped: 0
status: all_fixed
---

# Phase 9: Code Review Fix Report

**Fixed at:** 2026-05-29
**Source review:** `.planning/phases/09-user-app-ux-polish-market-detail-real-time/09-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 10 (CR-01, BL-01, WR-01..WR-08 — Critical + Warning tiers)
- Fixed: 10
- Skipped: 0
- Info findings (IN-01..IN-06): out of scope, not addressed.

All fixes preserve the locked Phase 9 contracts: money/odds stay strings on the
wire, the WS endpoint stays publicly readable (now bounded), activity stays
server-anonymized, and the order form never bypasses the server auth gate.

## Verification environment

- **Backend:** `uv run pytest -m "not integration"` → **141 passed, 2 skipped**.
  Targeted integration suites (realtime fan-out/isolation/reconnect,
  admin-publish, poll-publish) run against the live Redis container + a
  testcontainers Postgres → **13 passed**. Full lint trio clean:
  `ruff` (app/scripts/tests/alembic) all-pass, `mypy --strict` (78 files) clean,
  `lint_money_columns.py` → 0 warnings.
- **Frontend:** `corepack pnpm test` → **52 passed** across 12 suites (incl. the
  touched `use-market-socket.test.ts` and `order-entry-form.test.tsx`).
  `corepack pnpm build` → compiled successfully, Next's build-time TypeScript
  pass clean, all 14 routes (incl. `/markets/[slug]`) generated. `tsc --noEmit`
  reports zero errors in every file changed.
- **Known out-of-scope failure (NOT introduced here):** `pnpm test` reports one
  failed *suite* — `src/__tests__/middleware.test.ts` (DEF-FE-01 orphan: imports
  `../middleware`, renamed to `../proxy` in Phase 02-05). It is a suite-load
  failure (0 tests), tracked separately, and was explicitly out of scope. The
  repo-wide `tsc --noEmit` likewise fails only on this one orphan file; `next
  build`'s typecheck excludes test files and passes.
- **ESLint via CLI:** invoking the `eslint` binary directly outside the `next
  lint` wrapper hits a known `@eslint/eslintrc` circular-structure error in this
  worktree (a config-bridge/invocation limitation, exit code 0, not a lint error
  in the changed code). Frontend correctness is instead evidenced by the passing
  `next build` TypeScript pass, the 52 passing tests, and clean per-file `tsc`.

## Fixed Issues

### CR-01: Public WebSocket has no connection cap, no Origin check, accepts any market_id

**Files modified:** `backend/app/realtime/manager.py`, `backend/app/realtime/router.py`, `backend/tests/realtime/test_connection_cap.py`
**Commit:** `788c049`
**Status:** fixed
**Applied fix:** Added bounded abuse controls WITHOUT adding auth (the endpoint
stays public/read-only by design). `ConnectionManager.connect` now returns a
bool and enforces a per-process ceiling (`MAX_TOTAL_CONNECTIONS = 5000`) and a
per-market ceiling (`MAX_PER_MARKET = 1000`) under the lock — the cap check,
`ws.accept()` and registration are atomic so concurrent handshakes can't race
past the ceiling; over-cap handshakes are rejected *without* being accepted, and
a rejected first-connect for a new market does not leak an empty bucket. A
running `_total` is maintained and decremented only for sockets actually removed
(including the broadcast prune path). The router gates the handshake before
registration with three cheap, no-DB checks: connection cap (close 1013),
`Origin` allow-list against `settings.FRONTEND_BASE_URL` (close 1008; non-browser
clients that omit Origin are allowed since odds are public), and a `market_id`
length/empty shape gate (close 1008). Deliberately does NOT hit the DB on the
handshake (a per-connect query is its own DoS lever). Added 6 fast unit tests
(`test_connection_cap.py`) covering accept+count, per-market reject, global
reject, no empty-bucket leak, single-decrement disconnect, and prune
consistency. The `websockets` integration client sends no Origin by default, so
the 3 existing realtime integration tests still pass.

### BL-01: WS hook `onclose` can spawn parallel sockets / stale frame mutates odds

**Files modified:** `frontend/src/hooks/use-market-socket.ts`
**Commit:** `d4c622d`
**Status:** fixed: requires human verification
**Applied fix:** At the top of `connect()`, the previous `wsRef.current` (if any)
has its handlers nulled (`onopen/onmessage/onclose/onerror = null`) and is closed
BEFORE the new socket is constructed — so a late frame on the old socket finds
detached handlers and cannot mutate state, and the old socket cannot schedule
another reconnect. Added belt-and-suspenders stale-socket guards: `onmessage`
and `onclose` early-return when `wsRef.current !== ws`, so a handler that somehow
still fires for a non-authoritative socket is a no-op. The existing 4 hook tests
pass (the stub drives the current socket, so the guards pass through).
*Human-verification note:* this is a change to the reconnect state machine;
the existing tests assert live/stale/odds behavior but do not directly exercise
the rapid open→error→close→reconnect race, so the developer should confirm the
no-parallel-socket / no-stale-write behavior under a genuinely flaky connection.

### WR-01: Reconnect backoff counter grows unbounded → `2 ** attempt` overflows

**Files modified:** `frontend/src/hooks/use-market-socket.ts`
**Commit:** `48c2c58`
**Status:** fixed
**Applied fix:** Introduced `MAX_RECONNECT_ATTEMPTS_FOR_BACKOFF = 5` (2**5 * 1000ms
= 32s already exceeds the 30s delay cap). `scheduleReconnect` clamps the exponent
with `Math.min(reconnectAttemptRef.current, MAX_…)` for the delay, and clamps the
ref itself on increment so the attempt counter can never grow without bound (and
`2 ** 1024 = Infinity` can never arise). Delay/jitter math unchanged for normal
attempt counts; the 4 hook tests pass.

### WR-02: `publish_odds_change` blocking sync Redis publish on the request event loop

**Files modified:** `backend/app/realtime/publisher.py`, `backend/app/markets/router.py`, `backend/tests/markets/test_update_market_publishes.py`
**Commit:** `0a97040`
**Status:** fixed
**Applied fix:** Added `async def publish_odds_change_threadsafe(...)` that runs
the existing blocking sync `publish_odds_change` via `anyio.to_thread.run_sync`,
so the admin-edit handler (`update_market`) no longer stalls the worker's event
loop on the Redis round-trip. The route now `await`s the threadsafe wrapper
(still post-commit, still log-and-swallow on Redis hiccup). The sync function is
retained for non-async/test contexts; the fully-async poll path is unchanged
(it already reuses its `AioRedis`). Updated `test_update_market_publishes.py` to
patch the new async name and assert via `assert_awaited_once` /
`assert_not_awaited` (patching an `async def` yields an `AsyncMock`). Both
integration tests pass; the post-commit publish-once contract (T-09-03) holds.
*Scope note:* this implements the threadpool variant the review explicitly
sanctioned; it does not introduce a shared async pool (a larger refactor) since
the request handler holds no async Redis client.

### WR-03: `redis_subscriber` has no reconnect — a transient Redis drop freezes updates

**Files modified:** `backend/app/realtime/subscriber.py`, `backend/app/main.py`
**Commit:** `b387f39`
**Status:** fixed
**Applied fix:** Extracted the psubscribe+fan-out body into
`_subscribe_and_fan_out` (best-effort teardown suppressed so a broken connection
still reaches the reconnect path) and wrapped it in an outer `while True`
reconnect loop in `redis_subscriber`: `CancelledError` re-raises for clean
shutdown; any other exception logs `realtime.subscriber_reconnect` and retries
after a 1s backoff; a gracefully-ended stream logs and reconnects rather than
silently returning. Added `_subscriber_done_callback` wired via
`task.add_done_callback` in the lifespan to surface an unexpected (non-cancelled)
exit to logs + Sentry (added `import sentry_sdk`). The 3 realtime integration
tests pass (fan-out behavior unchanged).

### WR-04: `_run_detect_resolutions` closes the session twice on the success path

**Files modified:** `backend/app/integrations/polymarket/tasks.py`
**Commit:** `f06d937`
**Status:** fixed: requires human verification
**Applied fix:** Removed the in-`try` success-path close and the in-`except`
close; the session is now closed exactly once in a single `finally:` block
(guarded by `session is not None and session_override is None`), matching
`_run_poll_sync` / `_run_snapshot_odds`. Control flow is now symmetric and a
single-close is provable on every path. AST/ruff/mypy clean; the 4 runnable
detect tests pass. *Human-verification note:* the 2 integration tests that would
fully exercise the settle/rollback paths (`test_integration_proposed_not_settled`,
`test_reversal_after_auto_settlement`) could NOT run on this host — they fail with
a `ConnectionRefusedError` from asyncpg to their testcontainers Postgres. This is
a pre-existing environmental/Docker flake, CONFIRMED by stashing this fix and
re-running: the same two tests fail identically on the unmodified baseline. The
developer should confirm these two pass in CI where Docker networking is stable.

### WR-05: Poll/detect lock release is not owner-checked (delete-not-owned race)

**Files modified:** `backend/app/integrations/polymarket/tasks.py`, `backend/tests/polymarket/test_tasks.py`
**Commit:** `6439814`
**Status:** fixed
**Applied fix:** `acquire_poll_lock` now sets the lock value to a unique
`uuid4().hex` token and returns that token (`str | None`) instead of a bool;
`release_poll_lock(redis, token)` releases via a compare-and-delete Lua script
(`_RELEASE_LOCK_LUA`) so a task whose lock already expired (and was re-acquired
by another) cannot delete the new owner's lock. The same token +
compare-and-delete pattern is applied inline to the detect lock
(`DETECT_LOCK_KEY`). `_run_poll_sync` threads the token through acquire→release.
A scoped `# type: ignore[misc]` documents the redis-py async `eval` stub union
(`Awaitable[str] | str`). Updated the 3 affected unit tests + added 1 (acquire
returns token / returns None when held / release does owner-checked eval); 6
unit tests pass; ruff + mypy strict clean.

### WR-06: `MarketDetailLiveOdds` falls back to complement when NO odds round to 0

**Files modified:** `frontend/src/components/market-detail-live-odds.tsx`
**Commit:** `c821079`
**Status:** fixed: requires human verification
**Applied fix:** Replaced the `noPctRaw > 0 ? noPctRaw : 100 - yesPct` guard with
key-presence detection: `odds[noOutcomeId] !== undefined ? toPct(odds[noOutcomeId])
: 100 - yesPct` (wrapped in `useMemo`). This renders the explicit NO odds whenever
the backend supplies the NO key — even a legitimately tiny NO probability that
rounds to 0% — and only falls back to the binary complement when the NO key is
genuinely absent. `tsc` clean on the file. *Human-verification note:* this is a
display-logic change with no dedicated component test exercising the
absent-key-vs-rounds-to-0 distinction; the developer should eyeball the live-odds
block for a near-certain market to confirm the intended rendering.

### WR-07: 403 banned-vs-unverified relies on fragile `detail.includes("ban")`

**Files modified:** `frontend/src/lib/bet-actions.ts`
**Commit:** `dd07753`
**Status:** fixed
**Applied fix:** Tightened the substring match from the broad `"ban"` to the full
sentinel `"is banned"`, eliminating false positives from any future 403 detail
containing the letters "ban" (e.g. "bandwidth", "abandoned"). Verified against
the confirmed backend message `"Account is banned from placing bets."`
(`bets/router.py::current_betting_player`), whose lowercase form contains
`"is banned"`. `tsc` clean. *Scope note:* applied the minimal substring fix the
review sanctioned rather than the larger backend machine-readable-`code` change,
to avoid altering the 403 detail contract other consumers may depend on.

### WR-08: `expectedPayout` renders misleading payouts for sub-`BET_MIN_STAKE` amounts

**Files modified:** `frontend/src/components/order-entry-form.tsx`
**Commit:** `3b0de5d`
**Status:** fixed: requires human verification
**Applied fix:** Imported `BET_MIN_STAKE` / `BET_MAX_STAKE` and gated
`expectedPayout` on the same bounds the zod submit schema enforces — it now
returns `"—"` for a stake below min or above max, so the preview and the submit
gate agree (no plausible payout shown for a stake the form will reject).
Display-only; never feeds storage math (SP-1). The 7 order-entry-form tests pass
(the test stake `"50"` is in-bounds). *Human-verification note:* no test asserts
the new out-of-range `"—"` behavior directly; the developer should confirm the
boundary display (e.g. stake `"0.5"`).

## Skipped Issues

None — all 10 in-scope findings were fixed.

---

_Fixed: 2026-05-29_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
