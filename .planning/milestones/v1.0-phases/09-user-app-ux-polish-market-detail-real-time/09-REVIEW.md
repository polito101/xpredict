---
phase: 09-user-app-ux-polish-market-detail-real-time
reviewed: 2026-05-29T00:00:00Z
depth: standard
iteration: 2
files_reviewed: 44
files_reviewed_list:
  - backend/app/integrations/polymarket/adapter.py
  - backend/app/integrations/polymarket/tasks.py
  - backend/app/main.py
  - backend/app/markets/router.py
  - backend/app/markets/schemas.py
  - backend/app/markets/service.py
  - backend/app/realtime/__init__.py
  - backend/app/realtime/manager.py
  - backend/app/realtime/publisher.py
  - backend/app/realtime/router.py
  - backend/app/realtime/subscriber.py
  - backend/pyproject.toml
  - backend/tests/markets/test_activity_feed.py
  - backend/tests/markets/test_price_history.py
  - backend/tests/markets/test_service.py
  - backend/tests/markets/test_update_market_publishes.py
  - backend/tests/polymarket/test_poll_publishes.py
  - backend/tests/polymarket/test_tasks.py
  - backend/tests/realtime/__init__.py
  - backend/tests/realtime/conftest.py
  - backend/tests/realtime/test_connection_cap.py
  - backend/tests/realtime/test_ws_fanout.py
  - backend/tests/realtime/test_ws_isolation.py
  - backend/tests/realtime/test_ws_reconnect.py
  - frontend/package.json
  - frontend/src/app/markets/[slug]/page.tsx
  - frontend/src/app/portfolio/loading.tsx
  - frontend/src/components/bet-confirm-dialog.tsx
  - frontend/src/components/live-indicator.tsx
  - frontend/src/components/market-detail-live-odds.tsx
  - frontend/src/components/market-detail-skeleton.tsx
  - frontend/src/components/order-entry-form.test.tsx
  - frontend/src/components/order-entry-form.tsx
  - frontend/src/components/price-history-chart.test.tsx
  - frontend/src/components/price-history-chart.tsx
  - frontend/src/components/price-history-section.tsx
  - frontend/src/components/recent-activity-feed.tsx
  - frontend/src/components/ui/dialog.tsx
  - frontend/src/components/ui/select.tsx
  - frontend/src/hooks/use-market-socket.test.ts
  - frontend/src/hooks/use-market-socket.ts
  - frontend/src/lib/api.ts
  - frontend/src/lib/bet-actions.ts
  - frontend/src/lib/bet-schemas.ts
findings:
  critical: 0
  warning: 0
  info: 1
  total: 1
status: clean
---

# Phase 9: Code Review Report (Re-review — iteration 2)

**Reviewed:** 2026-05-29
**Depth:** standard
**Files Reviewed:** 44
**Status:** clean

## Summary

This is the iteration-2 re-review after the gsd-code-fixer applied fixes for the 10
prior findings (CR-01, BL-01, WR-01…WR-08). I re-traced each fix against the original
defect and stress-tested the two highest-risk classes of regression: (a) the
correctness-sensitive concurrency fixes — the worker-thread Redis offload (WR-02), the
compare-and-delete Lua lock release (WR-05), the subscriber reconnect loop (WR-03), and
the orphaned-socket guards (BL-01); and (b) whether any fix silently broke a locked
contract (money/odds as strings, server-side activity anonymization, the order form not
bypassing server auth gates, the WS staying publicly readable).

**Verdict: all 10 prior findings are genuinely resolved (not papered over), and no
regression was introduced.** The two flagship findings are solid:

- **CR-01** — the WS is now actually bounded against a connection flood while staying
  public/read-only. The cap check, `ws.accept()`, and registration are all performed
  under a single `asyncio.Lock` (`manager.py:56-69`), so concurrent handshakes cannot
  race past the ceiling (no accept-then-reject window). Over-cap handshakes return
  `False` *without* `accept()` and the router closes with 1013 (`router.py:82-84`). The
  empty-bucket leak on an over-cap first-connect is explicitly prevented
  (`manager.py:61-65`) and unit-tested (`test_connection_cap.py:78-87`). The endpoint
  still handles only `"ping"` and ignores all other inbound text (`router.py:87-90`), so
  it remains read-only — a client cannot inject a price. The reject path closes and
  returns *before* the `try/finally`, so the guarded `disconnect` (`manager.py:71-79`) is
  never run for a socket that was never registered — the counter stays correct. Origin +
  id-shape gates run before any accept/DB work and correctly allow non-browser clients
  (public data, no credential rides the socket).

- **BL-01** — the orphaned-socket race is actually closed. `connect()` detaches all four
  handlers and closes the prior socket *before* creating a new one
  (`use-market-socket.ts:102-113`), and both `onmessage` (`:128`) and `onclose` (`:155`)
  bail when `wsRef.current !== ws`. A late frame from socket A can no longer call
  `setOdds` after socket B is authoritative.

The correctness-sensitive fixes hold under scrutiny:

- **WR-02** — `publish_odds_change_threadsafe` offloads the blocking sync publish via
  `anyio.to_thread.run_sync` (`publisher.py:96`). The sync function builds a fresh
  short-lived client inside the worker thread and closes it in `finally`
  (`publisher.py:75-79`) — no client is shared across the event-loop boundary, and the
  loop stays responsive. The router awaits it post-commit inside try/except so a Redis
  hiccup can never 500 a committed admin edit (`router.py:113-117`). `anyio` is a
  transitive Starlette/FastAPI dependency and is present in `uv.lock`.

- **WR-05** — the lock is released only by its owner. `acquire_poll_lock` returns a
  per-acquire `uuid4().hex` token set via `SET … NX EX` (`tasks.py:65-67`), and release
  is a compare-and-delete Lua script `if get==token then del` (`tasks.py:49-52`). Applied
  to *both* the poll lock (`release_poll_lock`, `:70-79`) and the detect lock (inline
  eval, `:336`). A slow task whose TTL already expired can no longer delete a newer
  owner's lock. The Lua reads the key via `KEYS[1]` and compares to `ARGV[1]` — no string
  interpolation, no injection. Unit-covered at `test_tasks.py:59-71, 88-125`.

- **WR-03** — `redis_subscriber` is an outer `while True` loop that re-raises
  `CancelledError` (clean lifespan shutdown), logs + backs off 1s on any other exception,
  and *also* reconnects on a graceful stream-end instead of silently returning
  (`subscriber.py:86-98`). The inner `finally` best-effort unsubscribes/closes
  (`:63-69`) — `contextlib.suppress(Exception)` correctly lets a `CancelledError`
  (a `BaseException`) propagate so shutdown is not swallowed. The lifespan done-callback
  surfaces any unexpected exit to Sentry (`main.py:88-106`). No tight busy-loop — every
  non-cancel path sleeps before retrying.

- **WR-04** — the detect path now closes its session exactly once in a single `finally`
  guarded by `session is not None and session_override is None` (`tasks.py:331-333`),
  matching the poll/snapshot pattern.

The remaining fixes are all correctly implemented and covered:
- **WR-01** — backoff exponent + attempt ref are clamped to `MAX_RECONNECT_ATTEMPTS_FOR_BACKOFF`
  so the counter can't grow to `2**1024 → Infinity` over a long outage
  (`use-market-socket.ts:78-87`).
- **WR-06** — NO odds render from the explicit NO key when present, falling back to
  `100 - yesPct` only when the key is genuinely absent (`market-detail-live-odds.tsx:53-58`);
  the `noPct` memo correctly lists `yesPct` as a dependency, so no stale closure.
- **WR-07** — the 403 banned/unverified disambiguation matches the full `"is banned"`
  sentinel, not a bare `"ban"` substring (`bet-actions.ts:139-143`).
- **WR-08** — the payout preview returns `"—"` for a sub-min / over-max stake, agreeing
  with the zod submit gate (`order-entry-form.tsx:91-103`).

The locked contracts are intact: odds/money serialize as strings end-to-end
(`schemas.py` `field_serializer`s; `format_odds` quantizes to `Numeric(8,6)` so the socket
string matches the SSR string); activity anonymization lives in the query + schema with no
user-identity field (`service.py:411-423`, `schemas.py:180-197`) and is guarded by
load-bearing negative assertions over raw JSON (`test_activity_feed.py:337-356`); the order
form still routes through the authoritative cookie-forwarded `POST /bets` with no `user_id`
parameter (`bet-actions.ts:73-114`); and the WS endpoint remains publicly readable. A quick
sweep found no debug artifacts, no `eval`/`innerHTML`/`dangerouslySetInnerHTML`, no
`shell=True`/`os.system`, and no disabled TLS in scope.

No Critical or Warning issues remain. One out-of-scope INFO observation is recorded below
so it is not lost; it is **not** a regression and **not** one of the tracked findings, so
it does not affect the `clean` status of this re-review.

## Info

### IN-01: Pre-existing — `price_history` YES-outcome filter is case-sensitive and misses Polymarket markets (out of scope for this re-review)

**File:** `backend/app/markets/service.py:348-350` (label written at `backend/app/integrations/polymarket/adapter.py:245`)
**Issue:** `price_history` selects the YES outcome with `Outcome.label == "YES"` (uppercase).
House markets store `"YES"`/`"NO"` (`service.py:69,75`), so they work. But the Polymarket
adapter stores outcome labels verbatim from Gamma's `outcomes_raw` — which are `"Yes"`/`"No"`
(title-case) — truncated to `label[:50]` (`adapter.py:245,270-276`). For a Polymarket-sourced
market, `Outcome.label == "YES"` matches nothing, so `yes_outcome_id` is `None` and the
endpoint returns an empty `points` payload (`service.py:352-354`) — the chart silently shows
the "not enough history" placeholder even when snapshots exist. (`update_market`'s
`outcome.label == "YES"` branch at `:160` shares the assumption, but admin odds edits only
target house markets, so it is not reached for Polymarket markets.)

This is **pre-existing** code, not introduced by the fix pass, and is outside the two
re-review mandates (verify the 10 findings; catch regressions). The recent-activity feed is
unaffected — it reads the stored label directly with no `== "YES"` filter
(`service.py:413,421`). Recorded here only so it is tracked.

**Fix:** Make the YES match case-insensitive (or normalize labels to a canonical case at
sync time). Minimal change in `price_history`:
```python
from sqlalchemy import func
yes_stmt = select(Outcome.id).where(
    Outcome.market_id == market_id,
    func.upper(Outcome.label) == "YES",
)
```
Apply the same `func.upper(...)` normalization to `update_market` (`service.py:160`) if
Polymarket odds edits are ever enabled. Best handled as its own backlog item, not in this PR.

---

_Reviewed: 2026-05-29_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard (re-review, iteration 2)_
