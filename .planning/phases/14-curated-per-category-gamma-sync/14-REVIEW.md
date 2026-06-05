---
phase: 14-curated-per-category-gamma-sync
reviewed: 2026-06-05T00:00:00Z
depth: standard
files_reviewed: 11
files_reviewed_list:
  - backend/app/integrations/polymarket/schemas.py
  - backend/app/core/config.py
  - backend/app/integrations/polymarket/client.py
  - backend/app/integrations/polymarket/adapter.py
  - backend/app/integrations/polymarket/tasks.py
  - backend/app/celery_app.py
  - backend/tests/polymarket/conftest.py
  - backend/tests/polymarket/test_schemas.py
  - backend/tests/polymarket/test_client.py
  - backend/tests/polymarket/test_adapter.py
  - backend/tests/polymarket/test_tasks.py
findings:
  critical: 2
  warning: 5
  info: 4
  total: 11
resolution:
  status: blockers_resolved
  fixed_in: ce5833b
  tests_in: fc18448
  note: "CR-01 (child SAVEPOINT) + CR-02 (per-category publish reset), both critical, plus WR-04 (slug-retry SAVEPOINT) fixed in ce5833b; bidirectionally-validated regression tests (pass on fix, fail on revert) in fc18448. WR-01 (blank-conditionId dedup edge case) + info items flagged for Pol's review, not blocking."
status: issues_found
---

# Phase 14: Code Review Report

**Reviewed:** 2026-06-05
**Depth:** standard
**Files Reviewed:** 11
**Status:** issues_found

## Summary

Phase 14 adds a curated per-category Gamma `/events` sync: a new `GammaEvent`/`GammaEventMarket`/`GammaTag` parser, a `fetch_events` client method, `sync_events` + `_upsert_market_group` adapter methods, a `_run_poll_events` Celery loop with a distinct Redis lock, and a beat-schedule swap. The Pydantic parsing (float `volume24hr` → Decimal divergence, inherited stringified-JSON validators on children, `_derive_status` reuse) is correct and well-tested. The Redis events lock is genuinely distinct (`EVENTS_LOCK_KEY`), uses an owner-token compare-and-delete release, TTL 280s < 300s, and is released on every path. The beat swap edits the dict in place and keeps `poll_polymarket_top25` importable. The curation order (dedup-by-event-id BEFORE the `volume24hr` floor) is correct, and EVT-07 (`len==1` → standalone, no group row) is implemented and tested.

However, two **BLOCKER** transaction/state-correctness bugs exist in the grouping write path — exactly the "known bug family" the phase context flagged. Both are invisible to the current unit tests (which mock `sync_events`) and to the integration tests (which never exercise a mid-batch child `IntegrityError`, and assert a single category in isolation). They will corrupt the curated catalog under the conditions Phase 14 was built to handle (slug collisions, replays, multi-category cycles).

## Critical Issues

### CR-01: Child `IntegrityError` rolls back the WHOLE transaction, orphaning the just-created group row and prior siblings

**File:** `backend/app/integrations/polymarket/adapter.py:296-302` (the bare rollback) interacting with `adapter.py:424-432` (`sync_events`) and `adapter.py:352-368` (`_upsert_market_group` SAVEPOINT)

**Issue:**
`_upsert_one_market` handles its conflict path with a **full** `await session.rollback()`:

```python
except IntegrityError:
    await session.rollback()        # adapter.py:297 — rolls back the ENTIRE tx
    ...
    return False
```

`AsyncSession.rollback()` rolls back to the **outermost** transaction, discarding every open SAVEPOINT and all uncommitted work in the session — it is NOT a SAVEPOINT-scoped rollback. Now trace `sync_events` for a multi-child event:

1. `_upsert_market_group(session, ev, category)` runs, opens a `begin_nested()` SAVEPOINT, upserts the `market_groups` row, releases the SAVEPOINT, and returns the group UUID. The group row is now **pending in the outer transaction** (not yet committed — `_run_poll_events` commits per category *after* `sync_events` returns, tasks.py:277).
2. The loop calls `_upsert_one_market` for each child with `group_id=<that UUID>`.
3. If **any** child trips the partial-unique `(source, source_market_id)` conflict in a way that raises `IntegrityError` (or any other child-level integrity failure), the bare `session.rollback()` **discards the entire pending transaction** — including the `market_groups` row from step 1 and every sibling child already flushed in this batch.
4. The loop keeps going (`if await self._upsert_one_market(...): synced += 1; continue` — the `False` return is swallowed), and subsequent children are flushed referencing `group_id=<UUID>` whose `market_groups` row **no longer exists in the transaction**. On the per-category `session.commit()` this either inserts children pointing at a group row that was rolled away (FK violation on the `group_id` FK → migration 0011 `markets.group_id → market_groups.id`), or — if the FK check is deferred/absent at flush time — produces children whose `group_id` is dangling. Either way the category commit can fail entirely (CAT-05 keep-last-good defeated: the whole category is lost, not just one bad child) or persist an inconsistent group.

This is the same class of defect as the documented "idempotent replay leaves a dangling tx" family: a coarse `session.rollback()` used where a SAVEPOINT-scoped rollback was required. The existing top-25 path (`sync_top25` → `_upsert_one_market`) tolerated the full rollback because each market was independent and there was no parent row in flight; introducing the parent `market_groups` row in the same uncommitted unit of work makes the coarse rollback destructive.

**Fix:** Scope the child upsert's failure to a SAVEPOINT so one child's conflict cannot discard the group row or its siblings. Wrap the per-child body in `begin_nested()` and roll back only that SAVEPOINT:

```python
# in _upsert_one_market — replace the bare rollback with a SAVEPOINT-scoped one.
# Caller opens the savepoint so the method's contract ("rolls back only my work")
# is explicit:
async def _upsert_one_market(self, session, parsed, *, group_id, category) -> bool:
    sp = await session.begin_nested()
    try:
        ...  # existing upsert body, ending in await session.flush()
        await sp.commit()
    except IntegrityError:
        await sp.rollback()        # ONLY this child's work is discarded
        log.warning("gamma.upsert_conflict", source_market_id=parsed.id)
        return False
    ...
    return True
```

Note this also matters for `sync_top25`: a SAVEPOINT-scoped rollback there is harmless and removes the existing reliance on full-tx rollback. Whatever form is chosen, the group row and already-synced siblings MUST survive a single child's `IntegrityError`. Add a regression test: a 2-child event where the second child raises `IntegrityError`, asserting the `market_groups` row and the first child both persist after commit.

---

### CR-02: `adapter.changed_markets` is never reset between categories — re-publishes earlier categories' odds N times per cycle

**File:** `backend/app/integrations/polymarket/tasks.py:233` (single adapter instance) + `tasks.py:287-295` (publish loop inside the per-category loop) + `backend/app/integrations/polymarket/adapter.py:75` (init-once) and `adapter.py:290` (append-only)

**Issue:**
`self.changed_markets` is initialized once in `PolymarketAdapter.__init__` (adapter.py:75) and is **only ever appended to** (adapter.py:290) — there is no code path that clears it. In `_run_poll_events`, a **single** adapter instance is created before the category loop (tasks.py:233) and reused for all 7 categories. The real-time publish runs **inside** the per-category loop (tasks.py:287):

```python
for entry in settings.POLYMARKET_CATEGORIES:   # 7 categories
    ...
    synced = await adapter.sync_events(session, curated, category=entry.name)
    await session.commit()
    for market_id, deltas in adapter.changed_markets:   # ← never reset
        await publish_odds_change_async(redis, market_id, deltas)
```

After Politics commits and publishes its deltas, the list still holds them. When Sports commits, `adapter.changed_markets` now holds Politics' deltas **plus** Sports' deltas — so Politics' odds changes are published **again**. By the 7th category, categories 1-6 have been re-published (Politics up to 6 extra times). Consumers receive duplicate `price_update` events for markets whose odds did not change on this tick, directly violating the "POST-COMMIT, on-change only" contract the code comments claim to honor (Pitfall 4). It also misattributes a market's publish to a later category's commit boundary.

This bug does not exist in `_run_poll_sync` because that path creates a fresh adapter per poll and publishes exactly once after the single commit; the append-only list is harmless there. Moving the publish inside a multi-iteration loop with a shared, never-cleared accumulator is what introduces the defect. The unit tests miss it because both events tests set `mock_adapter.changed_markets = []` on a mock and never exercise real accumulation across categories.

**Fix:** Reset the accumulator at the start of each category iteration (or publish-then-clear after each category's publish loop). Simplest correct fix — clear before each `sync_events`:

```python
for entry in settings.POLYMARKET_CATEGORIES:
    try:
        ...
        adapter.changed_markets = []          # ← reset per category
        synced = await adapter.sync_events(session, curated, category=entry.name)
        await session.commit()
        for market_id, deltas in adapter.changed_markets:
            ...publish...
```

Alternatively, drain it: iterate `adapter.changed_markets` then set it to `[]` immediately after the publish loop. Add a test with two categories that each change one market, asserting `publish_odds_change_async` is called exactly twice total (once per market), not three times.

## Warnings

### WR-01: Group children deduped by `condition_id`, but the docstring + tests claim dedup is by event/market id — and a falsy `condition_id` silently drops a real child

**File:** `backend/app/integrations/polymarket/adapter.py:402-409`

**Issue:** `sync_events` dedups children by `m.condition_id` (`if not m.condition_id or m.condition_id in seen`). Two problems:
1. The integration test docstring (test_adapter.py:184-187) and the inline comment (adapter.py:402, "Dedup children within the event by condition_id (CAT-02)") are consistent with each other, but the dedup also doubles as the EVT-07 `len==1` gate. A Gamma child with an **empty** `conditionId` (Gamma returns `""` for not-yet-deployed markets) is silently skipped. If an event has 2 children and one has a blank `conditionId`, the surviving count is 1 → it is routed through the EVT-07 standalone path with `group_id=None`, **suppressing the group** for what is genuinely a multi-outcome event. The grouping decision should not hinge on a field that Gamma legitimately leaves blank.
2. `_upsert_one_market` keys its ON CONFLICT on `source_market_id` (= `parsed.id`), not `condition_id`. So dedup-by-`condition_id` and upsert-by-`id` use different keys; two distinct Gamma markets that happen to share a `condition_id` (multi-market conditions exist on Polymarket) would have the second dropped here even though they are separate rows in the DB grain.

**Fix:** Confirm the intended grain. If children are upserted by `id`, dedup by `id` (or by `id` with a `condition_id` tiebreak) so the dedup key matches the persistence key, and gate EVT-07 on the post-dedup child *count* using a field that is always present (`id`), not `condition_id`. At minimum, do not let a blank `conditionId` collapse a multi-child event into the standalone path.

### WR-02: `_safe_decimal(float)` goes through `str(float)` — lossy/locale-fragile for the floor comparison

**File:** `backend/app/integrations/polymarket/schemas.py:57-64, 239` and `core/config.py:117`

**Issue:** Event-level `volume_24hr` is a `float`; `volume_24hr_decimal` calls `_safe_decimal(self.volume_24hr)` which does `Decimal(str(value))`. For a float, `str()` yields the repr (e.g. `12345.67`), so `Decimal("12345.67")` carries the float's rounding already baked in. This is the value compared against `POLYMARKET_VOLUME_FLOOR = Decimal("10000")` (tasks.py:266). The phase's own "Money/Decimal discipline" rule says string→Decimal, never float, for any volume used in the floor comparison — but here the source is unavoidably a float (Gamma `/events` returns it as a JSON number). The conversion is *safe* (NaN is caught → 0), but it is float-derived, so a borderline event whose true 24h volume is exactly at the floor can land on either side due to float representation. Acceptable for a soft curation threshold, but it contradicts the stated invariant and is worth an explicit decision/comment.

**Fix:** Either (a) document that event-level volume is inherently float from Gamma and the floor is a soft threshold (so float-derived Decimal is acceptable here, unlike the stringified market-level `volume`), or (b) parse the event-level `volume24hr` from the raw JSON as a string before Pydantic coerces it to float (custom `mode="before"` validator capturing the raw token), preserving full precision. Given it is a curation floor, (a) is likely fine — but make the deviation explicit so a future reader does not "fix" it into a regression.

### WR-03: `_run_poll_events` lock is NOT released if session creation raises

**File:** `backend/app/integrations/polymarket/tasks.py:221-315`

**Issue:** The lock is acquired (tasks.py:214), then `client = GammaClient()` and the `try` block opens. The session is created **inside** the `try` (tasks.py:225-231). The `finally` (tasks.py:307) calls `release_events_lock`, so the lock IS released even if session creation fails — good. BUT `_get_session_maker()` / `session_maker()` is called inside the `try`, and if `from app.db.session import _get_session_maker` or the maker call raises, the `finally` runs `release_events_lock(redis, lock_token)` correctly. Re-reading: this path is actually covered. The real gap is narrower: between `acquire_events_lock` returning a token (tasks.py:214) and entering the `try` (tasks.py:221), `client = GammaClient()` (tasks.py:221) is *outside* the try. `GammaClient()` only sets `self._client = None` (cannot raise), so in practice the lock is safe. This is defensible but fragile: any future statement added between the lock acquire and the `try:` would leak the lock on exception.

**Fix:** Move `client = GammaClient()` inside the `try` (or acquire the lock as the first statement inside the `try` with the release in `finally`) so there is provably no window where the lock is held but the `finally` cannot run. Low severity because the current statements between acquire and `try` cannot raise, but the structure invites a future leak.

### WR-04: `_upsert_market_group` retry re-binds `nested` but a failure in the RETRY's `_do_upsert` is unhandled — and the SAVEPOINT may already be inactive

**File:** `backend/app/integrations/polymarket/adapter.py:351-368`

**Issue:** The slug-collision retry path:
```python
try:
    nested = await session.begin_nested()
    await _do_upsert(slug)
    await nested.commit()
except IntegrityError:
    await nested.rollback()
    ...
    nested = await session.begin_nested()   # retry
    await _do_upsert(slug)                   # ← NOT wrapped — a second IntegrityError propagates raw
    await nested.commit()
```
Two concerns:
1. If the uuid-suffixed retry *also* raises `IntegrityError` (vanishingly unlikely but possible if `(source, source_event_id)` somehow conflicts concurrently, or another constraint trips), it propagates uncaught out of `_upsert_market_group`, up through `sync_events`, into the `_run_poll_events` per-category `except` — which then calls `session.rollback()` (full tx). The new `nested` SAVEPOINT is left un-rolled-back at the point of the raise; the outer full rollback cleans it up, so it is not a leak, but the error message attributes a slug collision to the whole category failing. Acceptable (keep-last-good catches it), but the retry should not assume success.
2. More subtly: after `await _do_upsert(slug)` raises inside the first SAVEPOINT, the SAVEPOINT/connection may be in an aborted state; `await nested.rollback()` is correct, but issuing a brand-new `begin_nested()` immediately after on a connection whose last statement errored is the exact pattern that historically produced "a transaction is already begun"/aborted-tx errors in this codebase (the `begin()`-on-open-tx family). The compare against `markets/service.py:62` shows the same `begin_nested()`/`IntegrityError`/`rollback` shape, but there the retry loops with a fresh `begin_nested()` after `expunge` — here there is no `expunge` and the ORM `pg_insert` is a Core statement, so state should be clean, but this is worth a runtime QA pass (the phase context explicitly notes only runtime QA catches this family).

**Fix:** Wrap the retry `_do_upsert` in its own try and surface a clean error if it also fails; consider a small loop instead of a single hand-unrolled retry to keep the SAVEPOINT lifecycle uniform. Verify under real Postgres (not the mocked unit tests) that the collision→retry path commits the suffixed slug without an aborted-tx error.

### WR-05: `detect_polymarket_resolutions` constructs and closes a fresh `GammaClient` per candidate market inside the loop

**File:** `backend/app/integrations/polymarket/tasks.py:419-423`

**Issue:** Inside the candidate loop, `client = GammaClient()` is created and `await client.close()` is called for **every** market (tasks.py:419-423). This defeats the lazy-singleton connection pooling the client was designed for (each iteration spins up and tears down a fresh `httpx.AsyncClient` with its own pool). Not a correctness bug, and this code predates Phase 14, but it is in a reviewed file and contradicts the client's documented "lazy singleton" intent. (Out-of-scope perf is excluded, but this is also a resource-lifecycle/quality issue: N client open/close cycles per detect tick.)

**Fix:** Hoist a single `GammaClient()` outside the candidate loop and `await client.close()` once in a `finally`, mirroring how `_run_poll_sync`/`_run_poll_events` use one client per cycle. Out of strict Phase 14 scope (unchanged code) but flagged since it lives in the reviewed file and the diff touches this module.

## Info

### IN-01: `detect_polymarket_resolutions` lock acquire/release is hand-inlined instead of using the `acquire_*`/`release_*` helpers

**File:** `backend/app/integrations/polymarket/tasks.py:386-393, 505`

**Issue:** The detect task inlines `redis.set(DETECT_LOCK_KEY, token, nx=True, ex=...)` and `redis.eval(_RELEASE_LOCK_LUA, 1, DETECT_LOCK_KEY, token)` rather than using helper functions parallel to `acquire_poll_lock`/`acquire_events_lock`. Three near-identical lock idioms now exist; the inlined one is the odd one out and easier to drift (e.g. the TTL is `POLYMARKET_LOCK_TTL_SECONDS + 35`, a magic offset).

**Fix:** Extract `acquire_detect_lock`/`release_detect_lock` to match the other two, and name the `+ 35` offset (e.g. a `DETECT_LOCK_TTL_SECONDS` setting). Cosmetic; predates this phase.

### IN-02: Magic numbers in slug truncation (`[:93]`, `[:6]`, `[:80]`, `[:100]`)

**File:** `backend/app/integrations/polymarket/adapter.py:327-328, 365`

**Issue:** `base_slug[:93]` + `-` + `uuid4().hex[:6]` is hand-arithmetic to stay under `MarketGroup.slug = String(100)` (93 + 1 + 6 = 100). If the column width changes, these constants silently desync and can overflow the `String(100)` → `IntegrityError`/`DataError`. The `max_length=80` in `_slugify` and the `[:100]` cap are similarly bare.

**Fix:** Derive the budget from the column (e.g. `_SLUG_MAX = 100`, `_SUFFIX = 6`, slice to `_SLUG_MAX - _SUFFIX - 1`) or add a comment tying `93` to `String(100)`. Low risk today; brittle under schema change.

### IN-03: `_gamma_model_config()` swallows ALL exceptions to default `is_dev = True`

**File:** `backend/app/integrations/polymarket/schemas.py:44-53`

**Issue:** `except Exception:` around `get_settings().is_dev` defaults to `is_dev = True` (→ `extra="ignore"`). A genuine settings/config error (not just "env not set during collection") is silently masked and the parser silently picks the dev extra-policy in what might be prod. The docstring justifies it for test collection, which is reasonable, but a blanket `except Exception` is broader than needed.

**Fix:** Narrow to the expected failure (e.g. `except (ValidationError, ImportError)`), or log at debug when the fallback fires so a misconfigured prod surfaces rather than silently running dev parsing semantics. Minor — `extra="ignore"` vs `"allow"` is not security-sensitive (both satisfy T-06-01).

### IN-04: Comment/docstring drift — `celery_app.py` header says "Empty beat_schedule = {}" while the dict is populated

**File:** `backend/app/celery_app.py:14` (module docstring) vs `:48-68` (populated schedule)

**Issue:** The module docstring still reads "Empty beat_schedule = {} — Phases 2-9 append their periodic tasks here," but the schedule is now seeded with three entries (events poll, snapshot, detect). Similarly the inline "Phases 7-9 append tasks here" (line 62) is stale. Harmless but misleading to a future reader scanning the header for the schedule's shape.

**Fix:** Update the docstring to describe the actual seeded schedule (or note that Phase 14 swapped top-25 → events). Documentation-only.

---

_Reviewed: 2026-06-05_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
