---
phase: 16-catalog-event-api-house-event-crud
reviewed: 2026-06-05T00:00:00Z
depth: deep
files_reviewed: 8
files_reviewed_list:
  - backend/app/catalog/schemas.py
  - backend/app/catalog/service.py
  - backend/app/catalog/router.py
  - backend/app/settlement/event_schemas.py
  - backend/app/settlement/event_router.py
  - backend/app/settlement/event_service.py
  - backend/app/main.py
findings:
  blocker: 0
  warning: 4
  info: 5
  total: 9
status: resolved
---

## Resolution (2026-06-05, Cuco)

- **WR-01 (update_house_event outcome-replace — untested + fragile delete)** — FIXED. The Core
  `delete(Market)` now sets `synchronize_session=False`; after commit the session is `expunge_all()`-ed
  before the reload so the group's stale (cached) `markets` collection is re-read from the committed DB
  rows (the bug surfaced as the PATCH response returning the OLD outcomes). The docstring now correctly
  attributes the child→outcome cleanup to the DB-level `ON DELETE CASCADE` FK (not an ORM cascade). Added
  `test_edit_replace_outcomes_pre_bet` (replace 3→2, each child still exactly YES+NO) — fix commit `9c7c268`.
- **WR-04 (title-only PATCH left children with the stale title)** — FIXED. The metadata branch now
  re-derives each child's `question` from the new title. Added `test_edit_title_updates_child_question`.
- **WR-02 (child-slug collision → uncaught IntegrityError 500)** — ACCEPTED. `generate_slug` appends a
  6-hex random suffix (~16M space) per child; an intra-event collision is astronomically unlikely. A
  per-child retry would add complexity disproportionate to the risk; left as-is.
- **WR-03 (create slug-retry retries an admin slug 3× / masks non-slug IntegrityErrors)** — ACCEPTED.
  This mirrors the existing `MarketService.create_market` slug-retry precedent byte-for-byte; diverging
  here would make the two house-create paths inconsistent.
- **5 INFO findings** — noted (audit-count provenance, the duplicated `event_deadline` helper, the
  unbounded `closing_soon` constant, a theoretical `None`-deadline edge, the reverse-preview status-proxy
  count). No code change — all are cosmetic or already correct for the curated/bounded catalog.

# Phase 16: Catalog & Event API + House Event CRUD — Code Review Report

**Reviewed:** 2026-06-05
**Depth:** deep (cross-file, financial/API correctness)
**Files Reviewed:** 8 production files (vs `origin/main`)
**Status:** findings (no BLOCKERs — 4 WARNINGs + 5 INFOs)

## Summary

Phase 16 is a well-built HTTP-surface phase that faithfully follows its own RESEARCH/PATTERNS
guidance. I traced every flagged risk area and confirmed the load-bearing invariants hold:

- **Catalog is provably bounded** — both sub-queries are `LIMIT 100`, the merged set is sliced
  `[:100]`; every filter combo returns `list[CatalogItem]` (200 `[]`, never an error); search is a
  parameterised `.ilike(f"%{q}%")` bound param (no `text(`, no injection, local-only).
- **Two-step confirm is correct** — the preview branch is genuinely non-mutating (a single SELECT
  via `_load_group_with_children`, no service call, no commit; the request session's read-tx is
  rolled back by the `get_async_session` context manager on exit). The execute branch captures
  `admin_id = admin.id` BEFORE `await session.rollback()` and delegates to the Phase-15
  `EventService` (which owns per-child fresh sessions → 23505-safe), never looping children itself.
- **`_map_event_value_error` substring order is robust** — Mirrored / No market group /
  winning_outcome_id / justification are mutually non-colliding against the actual messages raised
  in `event_service.py`; I checked each message against every earlier branch.
- **House-event create** does the `begin_nested()`+IntegrityError slug-retry, exactly YES+NO per
  child, one `event.created` audit row, one commit, pre-commit id capture + eager reload.
- **Money/odds are strings everywhere** (`DecimalStr` / `field_serializer`), never floats; the
  public catalog schema deliberately omits resolver/payout/justification (public-safe projection).
- **Auth** — every `/admin/events*` route is gated by `current_active_admin`; public catalog reads
  are intentionally open. Confirmed against the tests (real-401 negatives present).
- **`event_service.py` is purely additive** — the diff shows the Phase-15
  `resolve_event`/`void_event`/`reverse_event` + helpers are byte-for-byte unchanged; only imports
  (`Decimal`, `HTTPException`, `delete`, `exists`, `IntegrityError`, `generate_slug`) and the new
  create/update/`_add_event_child`/`event_has_bets` block were appended.

The findings below are concentrated in **one under-tested, fragile mutation** (`update_house_event`
whole-list outcome REPLACE) and a few **robustness / consistency gaps**. None are data-loss or
security defects, hence no BLOCKER — but WR-01 should be fixed (or at minimum tested) before this
ships, because it is the only write path in the phase with zero coverage and the riskiest semantics.

## Warnings

### WR-01: `update_house_event` outcome-REPLACE path is untested and relies on undocumented Core-delete/ORM-identity-map interaction

**File:** `backend/app/settlement/event_service.py:729-743`

**Issue:** When `PATCH /admin/events/{id}` supplies `body.outcomes`, the service does a bulk Core
delete of the children then re-adds new ones:

```python
if body.outcomes is not None:
    await session.execute(delete(Market).where(Market.group_id == group_id))
    await session.flush()
    ...
    for outcome in body.outcomes:
        await _add_event_child(session, group=group, ...)
```

Two concrete concerns:

1. **Stale identity map.** `group` and its `children` were eager-loaded via
   `selectinload(MarketGroup.markets)` at line 712, so the deleted `Market` rows remain in the
   session as persistent objects (a Core `delete()` does **not** synchronize the ORM session — no
   `synchronize_session` is passed, and there is **no precedent for `delete(Market)` anywhere else
   in the codebase**). The function works in the happy path only because it reloads with a fresh
   query after `commit()` (line 746) and `commit()` expires everything. This is fragile: any future
   touch of `group.markets` between the delete and the commit, or a SQLAlchemy version bump that
   tightens stale-object handling, breaks it.

2. **ORM cascade vs DB FK cascade.** The docstring says "children cascade their outcomes on delete",
   but `MarketGroup.markets` has **no** ORM cascade (`models.py:272-275`, deliberately
   `ON DELETE SET NULL`). The child `outcomes`/`odds_snapshots` are only cleaned up because their FKs
   to `markets.id` are `ON DELETE CASCADE` (`models.py:299,341`) — i.e. the cleanup happens in
   Postgres, not in the ORM. That is correct **today**, but the comment misattributes the mechanism,
   and a Core `delete()` issued through SQLAlchemy still emits a single `DELETE FROM markets` that
   the DB cascades — fine, but entirely dependent on the FK definitions staying `CASCADE`.

**The decisive gap: this path has zero test coverage.** `tests/settlement/test_event_router.py`
only exercises PATCH with a title-only rename (`test_edit_lock_pre_bet_succeeds`, line 141) and the
423/404 gates. No test supplies `outcomes` to replace children. The single riskiest mutation in the
phase is unverified.

**Fix:** Add an integration test that PATCHes a 3-outcome event down to 2 (and 2→4), asserting the
old children + their outcomes are gone and the new ones exist with correct YES/NO odds. Then either
(a) make the delete ORM-aware to drop the fragile reliance:

```python
# Iterate the already-loaded children and delete via the session so the
# identity map + relationship collection stay consistent, OR pass
# synchronize_session and re-expire the group's markets collection.
for child in children:
    await session.delete(child)        # ORM delete: cascades child.outcomes in-session
await session.flush()
```

or (b) keep the Core delete but fix the docstring to say "the child `outcomes`/`odds_snapshots`
rows are removed by their `ON DELETE CASCADE` FKs (DB-level), not an ORM cascade" and add
`synchronize_session="fetch"` so the session evicts the deleted rows.

### WR-02: `_add_event_child` child-slug insert is not collision-protected (uncaught `IntegrityError` → 500 with a poisoned transaction)

**File:** `backend/app/settlement/event_service.py:758-806` (called from `create_house_event`
:668-677 and `update_house_event` :734-743)

**Issue:** The group insert is wrapped in the `begin_nested()` + `IntegrityError` slug-retry
(`create_house_event:650-666`), mirroring `MarketService.create_market`. But each **child** slug
(`generate_slug(f"{group.title} {label}")`, line 776) is inserted with a bare `await
session.flush()` (line 786) and **no** savepoint/retry. `generate_slug` appends a 6-hex random
suffix, so a collision is ~1-in-16M per child — improbable but not impossible, and it compounds with
the number of children created across the app's lifetime. On collision the `flush()` raises
`IntegrityError`, which propagates **uncaught** out of `create_house_event` / `update_house_event`;
the outer request transaction is left in an aborted state and the endpoint 500s (rather than the
graceful 409 the group path returns). The original `create_market` only had to protect one slug
(the market itself); the event path multiplies the surface by N children but protects none of them.

**Fix:** Wrap the child insert in the same `begin_nested()` retry as the group, regenerating the
child slug each attempt:

```python
for _attempt in range(3):
    child = Market(..., slug=generate_slug(f"{group.title} {label}"), ...)
    session.add(child)
    try:
        nested = await session.begin_nested()
        await session.flush()
        break
    except IntegrityError:
        await nested.rollback()
        session.expunge(child)
else:
    raise HTTPException(status_code=409, detail="Slug collision — try again")
```

### WR-03: `create_house_event` slug-retry loop swallows a non-slug `IntegrityError` and then retries it pointlessly, masking the real cause

**File:** `backend/app/settlement/event_service.py:650-666`

**Issue:** The retry catches **all** `IntegrityError`s, not just slug-uniqueness violations:

```python
except IntegrityError:
    await nested.rollback()
    session.expunge(group)
```

`MarketGroup` carries other constraints (e.g. `ck_market_groups_source`, and — relevant to an
admin-supplied slug — a deterministic uniqueness violation). If an admin supplies an explicit
`body.slug` that collides (line 655 uses `body.slug or generate_slug(...)`), the loop retries the
**identical** slug three times (the override is constant across attempts), burns all retries on
guaranteed-failing inserts, and only then returns 409 — wasteful, and it conflates "your slug is
taken" with "transient collision, try again". Worse, any **non-slug** integrity violation is also
caught, retried 3×, and surfaced as the misleading "Slug collision — try again" 409. This mirrors a
latent issue in `create_market`, but the event path newly exposes the admin-supplied-slug case.

**Fix:** Short-circuit the admin-supplied-slug case (no point retrying a constant value), and narrow
the except to the slug constraint so other integrity errors surface honestly:

```python
attempts = 1 if body.slug else 3
for _attempt in range(attempts):
    group = MarketGroup(..., slug=body.slug or generate_slug(body.title))
    ...
    except IntegrityError as exc:
        if "slug" not in str(exc.orig).lower():
            raise            # not a slug collision — don't mask it as 409
        await nested.rollback()
        session.expunge(group)
else:
    raise HTTPException(status_code=409, detail="Slug already exists — choose another")
```

(At minimum, special-case `body.slug` so a colliding override returns 409 on the first attempt
instead of after three identical failures.)

### WR-04: `update_house_event` rename leaves child slugs / questions stale after a title change

**File:** `backend/app/settlement/event_service.py:719-743`

**Issue:** On a title rename (`body.title is not None`), only `group.title` is updated. The child
markets' `question` (`f"{group.title} — {label}?"`) and `slug`
(`generate_slug(f"{group.title} {label}")`) were derived from the **old** title at create time and
are not refreshed — UNLESS `body.outcomes` is also supplied (which recreates the children from the
new title). So `PATCH {title: "New"}` renames the event but leaves every child question/slug bearing
the old title. This surfaces in the event-detail and child-deep-link paths (the child `slug` is
exposed in `EventOutcomeRead.child_slug` and `EventChildRead.slug`), producing a stale,
inconsistent label/URL. Not financially dangerous (pre-bet only), but a real correctness/consistency
defect in the edit contract.

**Fix:** When the title changes without an `outcomes` replace, refresh each child's derived
`question` (and decide explicitly whether `slug` should change — slugs are usually immutable for
URL stability, in which case document that the child slug intentionally retains the original title).
Minimally:

```python
if body.title is not None:
    group.title = body.title
    for child in children:
        child.question = f"{body.title} — {child.group_item_title}?"
        # child.slug left intentionally stable (URL permalink) — or regenerate if desired
```

If stale child slugs are acceptable by design, capture that decision in a comment so it is a
deliberate choice rather than an oversight.

## Info

### IN-01: `create_house_event` audit row uses pre-`flush` `len(body.outcomes)` rather than the actually-created child count

**File:** `backend/app/settlement/event_service.py:688-690`

**Issue:** The `event.created` audit payload records `"child_count": len(body.outcomes)`. Since each
outcome maps 1:1 to a child and all are created before the audit write, this is correct today. But
it is derived from the request body rather than the persisted children, so if `_add_event_child`
ever became conditional, the audit count would silently drift from reality. Low risk; flagged for
defensiveness in a financial-audit path.

**Fix:** Prefer counting created children (`len(group.markets)` after the loop, or a returned count
from the loop) so the audit reflects what was persisted, not what was requested.

### IN-02: `_event_deadline` helper in `event_router.py` diverges from the catalog `event_deadline` (first-child vs min-open-child)

**File:** `backend/app/settlement/event_router.py:66-68` vs `backend/app/catalog/service.py:73-80`

**Issue:** The admin response builder returns `children[0].deadline` (the first child in
relationship order), while the catalog computes the min open-child deadline. For house events all
children share one deadline, so the two agree in practice. The divergence is harmless now but is a
latent inconsistency if children ever carry per-outcome deadlines.

**Fix:** Reuse `app.catalog.service.event_deadline` (or a shared helper) in both places so the
"event deadline" definition lives in exactly one spot.

### IN-03: Catalog `closing_soon` market SQL filter has no lower bound — an OPEN market past its deadline is reported as "closing_soon"

**File:** `backend/app/catalog/service.py:108-111` and `:228-232`

**Issue:** `_market_matches_status(..., "closing_soon")` and the query-A SQL branch both test only
`deadline <= now + 48h` with no `deadline >= now` floor. An OPEN market whose deadline is already in
the past (not yet swept to CLOSED) matches `closing_soon`. Arguably defensible ("it should have
closed"), but it conflates "closing within 48h" with "overdue". Same applies to `_event_*` via
`event_deadline`. Cosmetic for a curated catalog.

**Fix:** If "closing soon" should mean strictly the upcoming window, add `now <= deadline`:
`Market.deadline >= now, Market.deadline <= now + CLOSING_SOON_WINDOW` (and mirror in the Python
predicate).

### IN-04: `update_house_event` can produce a `None` child deadline in a theoretical no-children edge case

**File:** `backend/app/settlement/event_service.py:717,732`

**Issue:** `existing_deadline = children[0].deadline if children else None`, then on an outcome
replace `new_deadline = body.deadline or existing_deadline`. If `body.deadline` is omitted AND the
group somehow has no children, `new_deadline` is `None`, which `_add_event_child` would pass to a
`NOT NULL` `markets.deadline` column → 500. Events are always created with ≥2 children so this is
currently unreachable, but the guard is implicit.

**Fix:** Validate `new_deadline is not None` before recreating children (raise a 422 "deadline
required" if it would be None), making the invariant explicit rather than relying on "events always
have children".

### IN-05: Reverse preview "settled children to reverse" counts only `RESOLVED` children, but a child can hold SETTLED bets while not in `RESOLVED` status

**File:** `backend/app/settlement/event_router.py:271`

**Issue:** The reverse preview computes
`settled = sum(1 for c in children if c.status == MarketStatus.RESOLVED.value)`. The real reverse
(`reverse_settlement`) finds work by **SETTLED bet status**, not by market status. The preview's
count is a market-status proxy that can disagree with what the execute branch actually reverses
(e.g. a child reopened to `CLOSED` by a prior partial reverse may still carry residual state, or a
child resolved-then-its-status-mutated). The preview is advisory and non-binding, so this is not a
correctness bug, but the displayed impact count can mislead the operator vs the actual execute
result.

**Fix:** If the preview number must match the execute effect, derive it from a SETTLED-bet EXISTS
per child (read-only) rather than `status == RESOLVED`; otherwise label the field as an estimate.

---

_Reviewed: 2026-06-05_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
