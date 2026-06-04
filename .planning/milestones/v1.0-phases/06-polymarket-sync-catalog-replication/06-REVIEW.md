---
phase: 06-polymarket-sync-catalog-replication
reviewed: 2026-05-28T19:15:00Z
depth: standard
files_reviewed: 35
files_reviewed_list:
  - backend/alembic/versions/0004_phase6_polymarket_sync.py
  - backend/app/celery_app.py
  - backend/app/core/config.py
  - backend/app/integrations/polymarket/__init__.py
  - backend/app/integrations/polymarket/adapter.py
  - backend/app/integrations/polymarket/client.py
  - backend/app/integrations/polymarket/schemas.py
  - backend/app/integrations/polymarket/tasks.py
  - backend/app/markets/models.py
  - backend/app/markets/router.py
  - backend/app/markets/schemas.py
  - backend/app/markets/service.py
  - backend/pyproject.toml
  - backend/tests/fixtures/gamma/active_market.json
  - backend/tests/fixtures/gamma/closed_not_resolved.json
  - backend/tests/fixtures/gamma/disputed_market.json
  - backend/tests/fixtures/gamma/resolved_market.json
  - backend/tests/markets/test_public_router.py
  - backend/tests/polymarket/__init__.py
  - backend/tests/polymarket/conftest.py
  - backend/tests/polymarket/test_adapter.py
  - backend/tests/polymarket/test_client.py
  - backend/tests/polymarket/test_home_list.py
  - backend/tests/polymarket/test_schemas.py
  - backend/tests/polymarket/test_tasks.py
  - frontend/src/__tests__/market-card.test.tsx
  - frontend/src/app/page.tsx
  - frontend/src/components/market-card.tsx
  - frontend/src/components/market-list-skeleton.tsx
  - frontend/src/components/market-list.tsx
  - frontend/src/components/odds-display.tsx
  - frontend/src/components/source-badge.tsx
  - frontend/src/components/ui/badge.tsx
  - frontend/src/components/ui/skeleton.tsx
  - frontend/src/lib/api.ts
findings:
  critical: 3
  warning: 6
  info: 2
  total: 11
status: issues_found
---

# Phase 06: Code Review Report

**Reviewed:** 2026-05-28T19:15:00Z
**Depth:** standard
**Files Reviewed:** 35
**Status:** issues_found

## Summary

Phase 06 implements Polymarket Gamma API integration: Celery beat tasks poll the Gamma API every 30s, upsert markets into Postgres via a well-designed ON CONFLICT clause on a partial unique index, snapshot odds every 5min, and expose a mixed house+polymarket public market list. The frontend adds a responsive card grid with odds bars, volume formatting, and source badges.

The closed-vs-resolved state machine is the critical correctness gate and is implemented correctly with thorough test coverage (the dangerous closed+proposed case is validated). Decimal discipline is solid throughout. The code is generally well-structured.

However, three critical issues must be fixed before shipping: (1) the MarketCard renders 50/50 odds for every real Polymarket market due to a case-sensitivity mismatch between Gamma API labels and the frontend lookup; (2) the `source_url` produces broken links to Polymarket using the Gamma numeric ID rather than the slug; and (3) the broad `except Exception` in `sync_top25` conflates parsing failures with database IntegrityErrors, masking slug collisions and leaving the session in a poisoned state. Six warnings address missing rollback logic, unbounded queries, and defensive fallbacks.

## Critical Issues

### CR-01: MarketCard shows 50/50 odds for all real Polymarket markets (case-sensitivity bug)

**File:** `frontend/src/components/market-card.tsx:32-35`
**Issue:** The card locates the YES outcome via `market.outcomes.find((o) => o.label === "YES")`. This is a case-sensitive exact match. The Gamma API returns outcome labels in title case -- `"Yes"` and `"No"` -- as confirmed by the fixture at `backend/tests/fixtures/gamma/active_market.json:13`. The adapter stores these labels verbatim (truncated to 50 chars at `adapter.py:155`). The find never matches `"Yes" === "YES"`, so `yesOutcome` is `undefined`, and the fallback on line 34 displays `50%` / `50%` for every Polymarket-sourced market.

This means 100% of synced Polymarket markets display incorrect odds on the home page. The test at `frontend/src/__tests__/market-card.test.tsx:47` passes because the test fixture hardcodes `label: "YES"` (uppercase), masking the real data mismatch.

Additionally, many Polymarket markets have non-binary labels entirely (e.g., `"Spurs"` / `"Thunder"` in fixture `resolved_market.json:10`), which also fall through to the 50% default.

**Fix:** Use case-insensitive matching and fall back to the first outcome for non-YES/NO markets:
```tsx
const yesOutcome = market.outcomes.find(
  (o) => o.label.toUpperCase() === "YES"
);
const primaryOutcome = yesOutcome ?? market.outcomes[0];
const primaryPercent = primaryOutcome
  ? Math.round(parseFloat(primaryOutcome.current_odds) * 100)
  : 50;
const secondaryPercent = 100 - primaryPercent;
```

### CR-02: source_url produces broken Polymarket links (numeric ID instead of slug)

**File:** `backend/app/markets/schemas.py:133-136`
**Issue:** `compute_source_url` builds `https://polymarket.com/event/{self.source_market_id}`, where `source_market_id` is the Gamma API numeric ID (e.g., `"1919425"` from `active_market.json:2`). Polymarket's actual event URLs use the slug format (e.g., `https://polymarket.com/event/us-x-iran-permanent-peace-deal-by-may-31-2026`). URLs like `https://polymarket.com/event/1919425` return 404 on polymarket.com, making every source badge link dead.

The Gamma API returns a `slug` field (parsed as `GammaMarket.slug` at `schemas.py:103`) but the adapter never stores it in the database. The UI spec (`06-UI-SPEC.md:202`) states the link target should use `{slug}`.

**Fix:** Persist the Polymarket slug and use it for URL construction. Options:
- Store the Gamma slug in a new column or repurpose an existing one. In `adapter.py`, add it to the upsert values.
- In `schemas.py`, build the URL from the stored slug:
```python
self.source_url = f"https://polymarket.com/event/{self.polymarket_slug}"
```

### CR-03: Broad `except Exception` in sync_top25 conflates parse failures with DB errors, poisoning the session

**File:** `backend/app/integrations/polymarket/adapter.py:81-85`
**Issue:** The `try` block at line 81 wraps `GammaMarket.model_validate(raw)` but the `except Exception` on line 83 is the only exception handler for the entire loop body -- the `try` block implicitly extends to cover all subsequent database operations through `await session.flush()` on line 169. This means:

1. An `IntegrityError` from the `pg_insert` (e.g., slug collision on the `ix_markets_slug` unique constraint) is caught and logged as `"gamma.parse_failed"` -- a misleading error label.
2. After an `IntegrityError`, the SQLAlchemy session is in an invalid state (the transaction is aborted). All subsequent loop iterations will fail because the session cannot execute new statements without a rollback.
3. The `session.flush()` at line 169 will raise `PendingRollbackError` for every remaining market after the first DB error, effectively dropping all remaining markets in that batch.

This creates a scenario where a single slug collision (see WR-01) cascades to skip all remaining markets in the batch, and the error is misattributed to parsing.

**Fix:** Separate the parse error handling from database error handling:
```python
try:
    parsed = GammaMarket.model_validate(raw)
except ValidationError:
    log.warning("gamma.parse_failed", raw_id=raw.get("id"))
    continue

try:
    # ... upsert + outcome logic ...
    await session.flush()
    synced += 1
except IntegrityError:
    await session.rollback()
    log.warning("gamma.upsert_conflict", source_market_id=parsed.id)
    continue
```

## Warnings

### WR-01: Slug regeneration on every upsert risks IntegrityError on unique constraint

**File:** `backend/app/integrations/polymarket/adapter.py:95`
**Issue:** `generate_slug(parsed.question)` appends a random 6-char hex suffix and is called every sync cycle. On the INSERT path for a new market, this random slug is persisted. On the ON CONFLICT UPDATE path, `slug` is excluded from `set_`, preserving the existing value. However, the INSERT still includes the random slug, and if it collides with another market's slug (any source), PostgreSQL raises an `IntegrityError` on the `ix_markets_slug` unique constraint. This error is distinct from the ON CONFLICT target, so it is NOT handled by the upsert -- it propagates as an exception.

The house market path (`MarketService.create_market`) handles this with a 3-attempt retry loop (lines 26-46 in `service.py`). The Polymarket adapter has no such retry, and per CR-03, the exception cascades to poison the entire batch.

**Fix:** Use a deterministic slug derived from the Polymarket slug (e.g., `parsed.slug` from Gamma API), or implement a retry loop with rollback for slug collisions.

### WR-02: _run_poll_sync does not rollback session on exception

**File:** `backend/app/integrations/polymarket/tasks.py:92-94`
**Issue:** When `adapter.sync_top25()` or `session.commit()` raises an exception, the `except` block logs and captures to Sentry but never calls `await session.rollback()`. While `session.close()` in the `finally` block auto-rollbacks when `session_override is None`, when `session_override` is provided (test mode or future callers), the caller's session is left in a failed transaction state. The `session.commit()` on line 87 will have partially applied, leaving an inconsistent state.

**Fix:**
```python
except Exception as exc:
    log.error("poll_failed", error=str(exc))
    sentry_sdk.capture_exception(exc)
    with contextlib.suppress(Exception):
        await session.rollback()
```

### WR-03: _run_snapshot_odds swallows exceptions without session rollback

**File:** `backend/app/integrations/polymarket/tasks.py:141-143`
**Issue:** Same pattern as WR-02. The snapshot task catches all exceptions and logs them, but never rolls back the session. When `session_override` is provided, the session is left in a dirty state.

**Fix:** Add `await session.rollback()` in the except block.

### WR-04: SourceBadge opens blank tab when sourceUrl is null

**File:** `frontend/src/components/source-badge.tsx:23`
**Issue:** The fallback `href={sourceUrl ?? "#"}` combined with `target="_blank"` means clicking a POLYMARKET badge with a null `sourceUrl` opens a blank new tab. The `compute_source_url` validator should always populate `source_url` for POLYMARKET sources, but defensive code should not produce a confusing UX when the backend contract is violated.

**Fix:** Guard the anchor on `sourceUrl` truthiness:
```tsx
if (source === "POLYMARKET" && sourceUrl) {
  return <a href={sourceUrl} target="_blank" ...><Badge>Polymarket</Badge></a>;
}
if (source === "POLYMARKET") {
  return <Badge>Polymarket</Badge>;
}
```

### WR-05: MarketRead schema omits volume and volume_24hr fields

**File:** `backend/app/markets/schemas.py:87-105`
**Issue:** `MarketRead` (used by `GET /api/v1/admin/markets/{id}` and `GET /api/v1/markets/{slug}`) does not include `volume` or `volume_24hr` fields. These were added to the model and to `MarketListItem`, but the detail schema omits them. Admin users inspecting a single market see no volume data.

**Fix:** Add the fields to `MarketRead` with serializers matching `MarketListItem`.

### WR-06: list_home_markets has no limit on house markets query

**File:** `backend/app/markets/service.py:192-200`
**Issue:** The house markets query has no `.limit()`. The Polymarket query correctly limits to 25. If many OPEN house markets exist, the response payload grows unbounded. At current scale this is acceptable but should be bounded.

**Fix:** Add `.limit(50)` to the house markets query.

## Info

### IN-01: Odds Numeric(8,6) accepts values > 1.0 without CHECK constraint

**File:** `backend/app/markets/models.py:129-130`
**Issue:** `Numeric(8, 6)` allows values up to `99.999999`. Odds/probabilities should be in `[0, 1]` range but no CHECK constraint enforces this. If a calculation error produces `1.000001` or a negative value, it is silently stored. This is a design observation -- current code always writes valid values.

**Fix:** Consider `CHECK (current_odds >= 0 AND current_odds <= 1)` on the outcomes table.

### IN-02: _gamma_model_config fallback defaults to extra="allow" in dev environments

**File:** `backend/app/integrations/polymarket/schemas.py:35-43`
**Issue:** `_gamma_model_config()` runs at class definition time. When `get_settings()` fails (test collection, missing env vars), the except block defaults `is_dev = False`, selecting `extra="allow"`. This means dev/test environments get the more permissive prod config. The comment on line 39 acknowledges this, but the fallback direction is backwards -- dev should be stricter, not more permissive.

**Fix:** Default to `is_dev = True` in the except block so unknown environments get the stricter `extra="ignore"` mode.

---

_Reviewed: 2026-05-28T19:15:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
