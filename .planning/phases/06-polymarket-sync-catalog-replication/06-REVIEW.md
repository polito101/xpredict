---
phase: 06-polymarket-sync-catalog-replication
reviewed: 2026-05-28T18:45:00Z
depth: standard
files_reviewed: 26
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
  - frontend/src/lib/api.ts
findings:
  critical: 2
  warning: 5
  info: 2
  total: 9
status: issues_found
---

# Phase 6: Code Review Report

**Reviewed:** 2026-05-28T18:45:00Z
**Depth:** standard
**Files Reviewed:** 26
**Status:** issues_found

## Summary

Phase 6 implements Polymarket catalog sync via the Gamma API, a Celery beat polling/snapshotting pipeline, Pydantic v2 parsing with a state-machine for market status, PostgreSQL upsert via partial unique index, and a frontend market grid with odds display and source badges.

The implementation is structurally sound -- the state machine for `closed`/`uma` status mapping is correct and well-tested (the critical PITFALLS.md case is covered), the Redis lock prevents overlapping polls, the INSERT ON CONFLICT upsert is idempotent, and the frontend handles loading/error/empty states.

However, there are two critical bugs: (1) `source_url` produces broken Polymarket links by using the Gamma API numeric `id` instead of the Polymarket `slug`, and (2) the frontend `MarketCard` silently shows 50/50 odds for any market whose outcomes are not labeled "YES"/"NO" (which is common for Polymarket sports and multi-outcome markets). Five warnings address missing error handling, schema omissions, and defensive fallback issues.

## Critical Issues

### CR-01: source_url produces broken Polymarket links

**File:** `backend/app/markets/schemas.py:133-136`
**Issue:** The `compute_source_url` model validator builds `source_url` as `https://polymarket.com/event/{self.source_market_id}`. The `source_market_id` field stores the Gamma API numeric `id` (e.g., `"1919425"` -- visible in `backend/tests/fixtures/gamma/active_market.json:2`). Polymarket's actual frontend URLs use their slug (e.g., `https://polymarket.com/event/us-x-iran-permanent-peace-deal-by-may-31-2026`). The resulting URLs like `https://polymarket.com/event/1919425` will 404 on Polymarket's frontend, producing dead links for every Polymarket badge in the UI.

The Gamma API returns a `slug` field (parsed by `GammaMarket.slug` in `schemas.py:103`) but the adapter discards it -- it is never stored in the database. The UI spec (06-UI-SPEC.md:202) explicitly states the link should use `{slug}`.
**Fix:** Store the Polymarket slug in a database field (either repurpose the existing `slug` column for Polymarket markets, or add a dedicated field), and use it to build the source URL. Minimal approach -- store the Gamma slug in `source_market_id` instead of the numeric `id`, since the slug is the user-facing identifier. Or better:

In `adapter.py` line ~102, add the Gamma slug to the upsert values:
```python
# In sync_top25, after parsing:
market_values = {
    ...
    "source_market_id": parsed.id,
    # Store polymarket slug for URL construction
}
```
And in `schemas.py`, change the URL construction to use the Gamma slug. This requires either storing the slug separately or changing `source_market_id` to store the slug. The cleanest fix is to store the Gamma slug alongside the id.

### CR-02: MarketCard shows 50/50 odds for non-YES/NO Polymarket markets

**File:** `frontend/src/components/market-card.tsx:32-36`
**Issue:** The card finds the YES outcome with `market.outcomes.find((o) => o.label === "YES")`. If no outcome has `label === "YES"`, it defaults to `50` percent. Many Polymarket markets have custom outcome labels (e.g., `"Spurs"` / `"Thunder"` in fixture `resolved_market.json:10`, or `"Yes"` vs `"YES"` case mismatch). The adapter stores outcome labels verbatim from the Gamma API (truncated to 50 chars), so labels like `"Yes"` (capitalized) or `"Spurs"` will miss the exact-match check and display misleading 50/50 odds.

The Gamma API fixtures show `"Yes"` (title-case, see `active_market.json:13`) while the frontend checks for `"YES"` (uppercase). Every Polymarket market with Gamma-standard `"Yes"`/`"No"` labels will show 50/50 instead of actual odds.
**Fix:** Use case-insensitive matching, and fall back to the first outcome when no YES/NO labels are found:
```tsx
const yesOutcome = market.outcomes.find(
  (o) => o.label.toUpperCase() === "YES"
);
// If no YES/NO labels, use the first outcome as the "primary" side
const primaryOutcome = yesOutcome ?? market.outcomes[0];
const primaryPercent = primaryOutcome
  ? Math.round(parseFloat(primaryOutcome.current_odds) * 100)
  : 50;
const secondaryPercent = 100 - primaryPercent;
```

## Warnings

### WR-01: Adapter generates random slug on every upsert, risking unique constraint violations

**File:** `backend/app/integrations/polymarket/adapter.py:95`
**Issue:** Every call to `sync_top25` calls `generate_slug(parsed.question)` which appends a random 6-char hex suffix. On the INSERT path (new market), this slug is stored. On the ON CONFLICT UPDATE path, the `set_` dict does not include `slug`, so the existing slug is preserved. However, the INSERT `values` always includes the new random slug. If a slug collision occurs (a different market already has that slug), the INSERT will fail with an IntegrityError on the `slug` unique constraint, and the exception is caught by the bare `except Exception` on line 83, silently skipping the market. This is a silent data loss path -- the market is logged as `gamma.parse_failed` (misleading log key) and never synced.

The probability per market per poll is ~1/16M (6 hex chars = 16^6) but across 25 markets polled every 30 seconds, it compounds.
**Fix:** Either use the Polymarket slug from `parsed.slug` directly (eliminating the randomness and making the slug deterministic and human-readable), or handle `IntegrityError` for slug collisions with a retry loop similar to `MarketService.create_market` (lines 26-46 in `service.py`).

### WR-02: snapshot_odds swallows exceptions without rolling back the session

**File:** `backend/app/integrations/polymarket/tasks.py:141-143`
**Issue:** In `_run_snapshot_odds`, if `session.commit()` (line 138) or any earlier line raises an exception, the `except` block logs and captures to Sentry, but never calls `await session.rollback()`. When `session_override` is `None`, `session.close()` in the `finally` block will auto-rollback the implicit transaction. But when `session_override` is provided (test mode or future callers), the session is left in a dirty/failed state -- the caller's transaction is poisoned.
**Fix:** Add explicit rollback in the except block:
```python
except Exception as exc:
    log.error("snapshot_failed", error=str(exc))
    sentry_sdk.capture_exception(exc)
    await session.rollback()
```

### WR-03: SourceBadge opens blank tab when sourceUrl is null

**File:** `frontend/src/components/source-badge.tsx:23`
**Issue:** The fallback `href={sourceUrl ?? "#"}` means if a Polymarket market somehow has a null `sourceUrl`, clicking the badge opens a new blank tab (due to `target="_blank"`). While the model_validator in `schemas.py` should always produce a non-null URL for POLYMARKET sources, this is a poor defensive fallback. A `#` link with `target="_blank"` is confusing UX.
**Fix:** Don't render the anchor when `sourceUrl` is falsy:
```tsx
if (source === "POLYMARKET" && sourceUrl) {
  return <a href={sourceUrl} ...>...</a>;
}
if (source === "POLYMARKET") {
  // No link available -- render badge without anchor
  return <Badge ...>Polymarket</Badge>;
}
```

### WR-04: MarketRead schema omits volume and volume_24hr fields

**File:** `backend/app/markets/schemas.py:87-105`
**Issue:** The `MarketRead` response schema (used by admin detail and public slug endpoints) does not include `volume` or `volume_24hr` fields. These were added to the model and to `MarketListItem`, but the detail schema omits them. Admin users querying a single market via `GET /api/v1/admin/markets/{id}` get no volume data, even though it exists in the database.
**Fix:** Add the fields to `MarketRead`:
```python
class MarketRead(BaseModel):
    ...
    volume: Decimal = Decimal("0")
    volume_24hr: Decimal = Decimal("0")
    ...

    @field_serializer("volume", "volume_24hr")
    @classmethod
    def serialize_decimal(cls, v: Decimal) -> str:
        return str(v)
```

### WR-05: Adapter silently swallows all parse exceptions with broad except

**File:** `backend/app/integrations/polymarket/adapter.py:83-85`
**Issue:** The `except Exception` block on line 83 catches ALL exceptions during `GammaMarket.model_validate(raw)`, not just `ValidationError`. This means unexpected exceptions (e.g., `AttributeError`, `TypeError` from bugs in validators, or even `KeyboardInterrupt` if not BaseException) are silently logged as `gamma.parse_failed` and the market is skipped. The log message `raw_id=raw.get("id")` suggests this is meant for validation failures only, but the broad catch masks real bugs.
**Fix:** Narrow the exception type to `pydantic.ValidationError`:
```python
from pydantic import ValidationError

try:
    parsed = GammaMarket.model_validate(raw)
except ValidationError:
    log.warning("gamma.parse_failed", raw_id=raw.get("id"))
    continue
```

## Info

### IN-01: list_home_markets has no limit on house markets query

**File:** `backend/app/markets/service.py:192-200`
**Issue:** The house markets query in `list_home_markets` has no `.limit()`. If the platform accumulates many OPEN house markets, this endpoint will return all of them in a single response. The Polymarket query correctly limits to 25. This is acceptable for current scale (early platform) but should be bounded as the platform grows.
**Fix:** Add `.limit(50)` or a configurable cap to the house markets query.

### IN-02: _gamma_model_config evaluated at class definition time with side effects

**File:** `backend/app/integrations/polymarket/schemas.py:35-43`
**Issue:** `_gamma_model_config()` is called at class-body time (line 99: `model_config = _gamma_model_config()`), which means it runs `get_settings()` during import. The `try/except Exception` fallback handles missing env vars, but this couples module import to settings availability. The broad `except Exception` also masks real configuration bugs (e.g., invalid `DATABASE_URL` format will be silently swallowed, defaulting to `extra="allow"` regardless of actual environment).
**Fix:** Narrow the except clause to the specific exceptions that indicate missing settings (e.g., `pydantic.ValidationError`), or document the import-time side effect explicitly.

---

_Reviewed: 2026-05-28T18:45:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
