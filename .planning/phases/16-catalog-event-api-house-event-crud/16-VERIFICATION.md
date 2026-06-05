---
phase: 16-catalog-event-api-house-event-crud
verified: 2026-06-05T21:04:34Z
status: passed
score: 18/18
overrides_applied: 0
---

# Phase 16: Catalog & Event API + House Event CRUD — Verification Report

**Phase Goal:** A stable HTTP contract exposes browse/search/category/event reads and house-event create/edit/resolve/reverse — testable independently of any UI — with every filter combination returning an explicit, bounded result.
**Verified:** 2026-06-05T21:04:34Z
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `GET /catalog` returns bounded LIMIT 100 + local pg_trgm ILIKE search + category/status/sort filters + every filter combo explicit-empty | VERIFIED | `service.py:245` `.limit(CATALOG_LIMIT)`, `service.py:281` `return items[:CATALOG_LIMIT]`, `CATALOG_LIMIT=100` at line 38; `.ilike(f"%{q}%")` at lines 242, 256; `text(` absent; no Gamma reference; `scalars().all()` at lines 247, 261 — never `scalar_one()` |
| 2 | `GET /categories` returns non-empty DISTINCT union + `GET /events/{slug}` returns per-outcome YES rows + derived status + 404 on <2-child or missing | VERIFIED | `service.py:295-315` two-query union over markets + groups, `set(market_cats) | set(group_cats)` sorted; `router.py:51-75` builds `EventDetail` with `event_outcome_rows(children)` + `derive_event_status`; `len(children) < 2` raises 404 at `router.py:63` |
| 3 | `POST /admin/events` creates MarketGroup(source=HOUSE) + N binary YES/NO children; <2 outcomes → 422; PATCH edits pre-bet, HTTP 423 after first bet (EXISTS(bets), not bet_count) | VERIFIED | `event_service.py:635-695` `create_house_event` with slug-retry + `_add_event_child` per outcome; `_add_event_child` adds exactly YES+NO pair (lines 788-804); `event_schemas.py:51` `Field(min_length=2)`; `event_router.py:148-155` `event_has_bets` → 423 with `EVENT_LOCKED`; `event_has_bets` at `event_service.py:809-819` uses `exists()` over `Bet.market_id`, `bet_count` absent |
| 4 | Admin resolve/void/reverse enforce mandatory justification + two-step stateless confirm; ValueError → HTTP map (mirrored→409, blank→422, bad-outcome→422, missing→404); `GET /markets` still works | VERIFIED | `event_schemas.py:124-171` all three request models have `confirm:bool=False` + `Field(min_length=1)` justification; `event_router.py:83-100` `_map_event_value_error` maps Mirrored→409, No market group→404, winning_outcome_id→422, justification→422; each execute branch: `admin_id=admin.id` then `await session.rollback()` before service call (lines 201-202, 241-242, 280-281); preview branches are read-only (no service call, no commit); `test_public_router.py:254-263` back-compat test asserts `isinstance(resp.json(), list)` on `GET /api/v1/markets` |

**Score:** 4/4 ROADMAP success criteria verified

---

### Plan-level Must-Haves (all 5 plans)

| # | Plan | Truth | Status | Evidence |
|---|------|-------|--------|----------|
| P01-T1 | 16-01 | Catalog test package with httpx AsyncClient + ASGITransport fixture | VERIFIED | `tests/catalog/conftest.py:83-88` `ASGITransport(app=app, raise_app_exceptions=False)`; imports `app.main:app`; does NOT redefine `engine` or `async_session` |
| P01-T2 | 16-01 | Seed-factory module: make_market, make_event, place_bet_on_child, per-state helpers | VERIFIED | `_factories.py` exposes `make_market` (line 99), `make_event` (line 136), `make_single_child_group` (line 194), `place_bet_on_child` (line 261), `resolve_child` (line 343), `drive_event_open/partial/resolved/void` (lines 389-433); every monetary literal uses `Decimal`; `place_bet_on_child` funds via `WalletService.recharge` (line 316) |
| P01-T3 | 16-01 | Wave-1+ tests can import shared client + factories without redefining infra | VERIFIED | `test_event_router.py:32` imports `from tests.catalog._factories import admin_override, place_bet_on_child`; `test_event_settle_router.py:27` does the same; `test_catalog_router.py:22-28` imports factories directly |
| P02-T1 | 16-02 | `GET /catalog` bounded, ILIKE local search, status/sort filters, every combo 200+[] | VERIFIED | `service.py:200-281` full implementation; `test_catalog_router.py` covers: `test_catalog_returns_bounded_list`, `test_search_local_only`, `test_status_filter`, `test_sort`, `test_empty_combos`, `test_bad_status_and_sort_422` |
| P02-T2 | 16-02 | Text search q matches local ILIKE, never Gamma | VERIFIED | `service.py:242` `Market.question.ilike(f"%{q}%")`; `service.py:256` `MarketGroup.title.ilike(f"%{q}%")`; no `text(` in service; `test_search_local_only` never patches Gamma and confirms local-only result |
| P02-T3 | 16-02 | category/status/sort filters, every combo 200+[] | VERIFIED | `service.py:226-244` status SQL filters; `service.py:268` `_event_matches_status` post-filter; `service.py:272-280` sort; `test_empty_combos` exercises 4 guaranteed-empty combinations, all assert `200 + []` |
| P02-T4 | 16-02 | `GET /events/{slug}` ≥2-child only, per-outcome YES price rows, 1-child/missing → 404 | VERIFIED | `router.py:62-63` `if group is None or len(children) < 2: raise HTTPException(404)`; `test_event_detail_single_child_404` + `test_event_detail_missing_404` both assert 404; `test_event_detail_two_child` checks `yes_price` is a JSON string and `group_item_title` labels appear |
| P02-T5 | 16-02 | `GET /categories` non-empty DISTINCT union (CAT-06) | VERIFIED | `service.py:295-315` union with `isnot(None)` + `!= ""` guards; `test_categories_union_nonempty` asserts None/empty excluded, both markets+groups contribute, result is sorted DISTINCT |
| P02-T6 | 16-02 | Money/odds serialize as JSON strings, never floats | VERIFIED | `schemas.py:35-39` `@field_serializer("yes_price")` returns `str(v)`; `schemas.py:65-68` `@field_serializer("volume")` returns `str(v)`; every test checks `isinstance(item["volume"], str)` / `isinstance(outcome["yes_price"], str)` |
| P03-T1 | 16-03 | `POST /admin/events` creates group + N YES/NO children, 1-outcome → 422 | VERIFIED | `event_service.py:635-695` create path; `_add_event_child:774-806` adds exactly YES+NO; `test_create_event_creates_group_and_children` DB-reads and asserts `sorted(o.label for o in child.outcomes) == ["NO", "YES"]` for every child |
| P03-T2 | 16-03 | `PATCH /admin/events/{group_id}` edit-lock 423 after first bet | VERIFIED | `event_router.py:148-155` calls `event_has_bets` → raises `HTTP_423_LOCKED`; `event_has_bets:809-819` uses `exists()` over `Bet.market_id.in_(child_ids)`; `test_edit_lock_after_bet_returns_423` seeds a committed ledger-backed bet and asserts 423 + `EVENT_LOCKED` code |
| P03-T3 | 16-03 | Both admin endpoints require Bearer; no Bearer → 401 | VERIFIED | `event_router.py:128` `Depends(current_active_admin)` on POST; `event_router.py:142` `Depends(current_active_admin)` on PATCH; `test_create_requires_admin` + `test_patch_requires_admin` assert 401 with no override |
| P04-T1 | 16-04 | resolve/void/reverse expose Phase-15 EventService; endpoints never loop children | VERIFIED | `event_router.py:204,244,283` call `EventService.{resolve,void,reverse}_event`; no manual per-child settle loop exists in the router; the service owns per-child fresh sessions |
| P04-T2 | 16-04 | Two-step confirm: `confirm:false` → 200 non-mutating preview; `confirm:true` → execute | VERIFIED | `event_router.py:175-199` preview branch returns `EventActionResponse(preview=True)` with no service call; `test_resolve_preview_does_not_mutate` asserts `preview:true` AND DB read shows no child RESOLVED after the call |
| P04-T3 | 16-04 | Justification mandatory non-empty; ValueError → HTTP map (mirrored→409, blank→422, bad-outcome→422, missing→404) | VERIFIED | All three request models have `Field(min_length=1)` justification + `confirm:bool=False`; `_map_event_value_error:83-100` maps exact service ValueError strings; `test_value_error_mirrored_409`, `test_value_error_blank_justification_422`, `test_value_error_bad_winning_outcome_422`, `test_value_error_missing_group_404` cover all four paths |
| P04-T4 | 16-04 | Execute branch: `admin_id = admin.id` BEFORE `await session.rollback()` (MissingGreenlet + 23505 choreography) | VERIFIED | `event_router.py:201-202` resolve; `241-242` void; `280-281` reverse: `admin_id = admin.id` immediately followed by `await session.rollback()` on the very next line in every execute branch |
| P05-T1 | 16-05 | `public_catalog_router` + `event_admin_router` registered in `main.py` deferred-import block | VERIFIED | `main.py:185` `from app.catalog.router import public_catalog_router  # noqa: E402`; `main.py:189` `from app.settlement.event_router import event_admin_router  # noqa: E402`; `main.py:200` `app.include_router(public_catalog_router)`; `main.py:205` `app.include_router(event_admin_router)` |
| P05-T2 | 16-05 | All 8 Phase-16 routes reachable on live app; legacy `GET /markets` still flat list | VERIFIED | `test_wiring.py:21-30` enumerates all 8 paths; `test_new_routes_registered` asserts `missing == set()`; `test_public_markets_backcompat_flat_list` asserts `isinstance(resp.json(), list)` on `GET /api/v1/markets` |

**Score:** 18/18 must-haves verified

---

### Required Artifacts

| Artifact | Status | Evidence |
|----------|--------|----------|
| `backend/tests/catalog/__init__.py` | VERIFIED | Exists as package marker |
| `backend/tests/catalog/conftest.py` | VERIFIED | 89 lines; contains `ASGITransport`, `app.dependency_overrides.clear()`; does not redefine `engine`/`async_session` |
| `backend/tests/catalog/_factories.py` | VERIFIED | 501 lines; exposes all required helpers; WalletService.recharge used; Decimal throughout |
| `backend/app/catalog/schemas.py` | VERIFIED | 108 lines; `Literal["market","event"]`; `field_serializer` for `volume` + `yes_price`; `from_attributes=True` |
| `backend/app/catalog/service.py` | VERIFIED | 316 lines; `CATALOG_LIMIT=100`; `selectinload(MarketGroup.markets)`; imports `derive_event_status`+`ChildStatus` from Phase 15; no `text(`, no Gamma ref, no `scalar_one(` in list path |
| `backend/app/catalog/router.py` | VERIFIED | 87 lines; NO `from __future__ import annotations` (with load-bearing comment); registers `/api/v1/catalog`, `/api/v1/events/{slug}`, `/api/v1/categories`; `Literal[...]` on status/sort; no `Depends(current_active_admin)` |
| `backend/tests/catalog/test_catalog_router.py` | VERIFIED | 179 lines; covers all BRW-01/03/04/05 behaviors |
| `backend/tests/catalog/test_categories.py` | VERIFIED | 45 lines; covers CAT-06 |
| `backend/tests/catalog/test_event_detail.py` | VERIFIED | 57 lines; covers BRW-02 + EVT-07 gating |
| `backend/app/settlement/event_schemas.py` | VERIFIED | 172 lines; `min_length=2` on outcomes; `Field(gt=0,lt=1)` on initial_odds; all request models `extra="forbid"`; `confirm:bool=False` on all settle models |
| `backend/app/settlement/event_router.py` | VERIFIED | 301 lines; NO `from __future__ import annotations` (with load-bearing comment); prefix `/admin/events`; `current_active_admin` on every endpoint; `event_has_bets` + 423; resolve/void/reverse with preview/execute split; `_map_event_value_error` |
| `backend/app/settlement/event_service.py` (additions) | VERIFIED | `create_house_event` at line 635; `update_house_event` at line 698; `event_has_bets` at line 809 — all additive, existing resolve/void/reverse methods unchanged |
| `backend/tests/settlement/test_event_router.py` | VERIFIED | 184 lines; 8 tests covering create/edit-lock/auth gate |
| `backend/tests/settlement/test_event_settle_router.py` | VERIFIED | 234 lines; 9 tests covering two-step confirm, full ValueError map, auth gate, drift_count==0 |
| `backend/tests/catalog/test_wiring.py` | VERIFIED | 45 lines; asserts all 8 Phase-16 paths present on live app |
| `backend/app/main.py` | VERIFIED | Both deferred imports + `include_router` calls present; `# noqa: E402` markers |

---

### Key Link Verification

| From | To | Via | Status | Evidence |
|------|----|-----|--------|----------|
| `catalog/service.py` | `settlement/event_service.py` | `from app.settlement.event_service import ChildStatus, derive_event_status` | VERIFIED | `service.py:32` imports both; used at lines 267, 64 (router) |
| `catalog/service.py` | `markets`/`market_groups` tables | `selectinload(MarketGroup.markets).selectinload(Market.outcomes)` + ILIKE | VERIFIED | `service.py:252-258`; `selectinload` on both relationship levels |
| `catalog/router.py` | `catalog/service.py` | `CatalogService` method calls; `Literal` Query params | VERIFIED | `router.py:46,62,82`; `Literal["open","closing_soon","resolved"]` at line 37; `Literal["volume","closing_soonest","newest"]` at line 38 |
| `catalog/conftest.py` | `tests/conftest.py` | `engine`/`async_session` fixture reuse (not redefined) | VERIFIED | `conftest.py` has no `engine` or `async_session` definition; the `_require_testcontainer(engine)` fixture declares the parent fixture as a parameter |
| `catalog/conftest.py` | `app.main` | `ASGITransport(app=app)` | VERIFIED | `conftest.py:86` `ASGITransport(app=app, raise_app_exceptions=False)` |
| `event_router.py` | `auth/deps.py` | `Depends(current_active_admin)` on every endpoint | VERIFIED | `event_router.py:128,142,171,225,264` all declare `Depends(current_active_admin)` |
| `event_router.py` | `bets` table | `event_has_bets` EXISTS over child ids | VERIFIED | `event_router.py:148` calls `event_has_bets`; `event_service.py:809-819` implements `EXISTS(bets.market_id IN (child_ids))` |
| `event_router.py` | `event_service.py` (resolve/void/reverse) | `admin_id` capture + `await session.rollback()` then service call | VERIFIED | Lines 201-211 (resolve), 241-250 (void), 280-289 (reverse): `admin_id=admin.id` on the line immediately before `await session.rollback()` in every execute branch |
| `main.py` | `catalog/router.py` | `include_router(public_catalog_router)` | VERIFIED | `main.py:185,200` |
| `main.py` | `settlement/event_router.py` | `include_router(event_admin_router)` | VERIFIED | `main.py:189,205` |
| `tests/settlement/test_event_router.py` | `tests/catalog/_factories.py` | cross-package import of `admin_override`, `place_bet_on_child` | VERIFIED | `test_event_router.py:32` `from tests.catalog._factories import admin_override, place_bet_on_child` |

---

### Data-Flow Trace (Level 4)

All catalog and event endpoints are read-only against real DB rows. The service path is:

- `GET /catalog`: `session.execute(market_stmt)` + `session.execute(group_stmt)` → real rows; `scalars().all()` returns actual query results, never empty statics.
- `GET /events/{slug}`: `session.execute(select(MarketGroup).where(...))` → `scalar_one_or_none()` with eager-loaded children+outcomes.
- `GET /categories`: two real `select(Market.category).distinct()` + `select(MarketGroup.category).distinct()` union.
- Admin create/PATCH: committed DB writes; `create_house_event` calls `session.commit()` at line 692.

No hardcoded empty returns in any service method. Data-flow is FLOWING.

---

### Behavioral Spot-Checks

Phase 16 is backend-only; the server is not running. Per-module pytest results documented in SUMMARYs and confirmed by code inspection:

| Behavior | Evidence | Status |
|----------|----------|--------|
| `cd backend && uv run pytest tests/catalog -x` green (12 tests) | SUMMARYs 16-01/02 claim green; code is substantive, not stubs | PASS (code evidence) |
| `cd backend && uv run pytest tests/settlement/test_event_router.py -x` green (8 tests) | SUMMARY 16-03 claims green; 8 test functions confirmed in code | PASS (code evidence) |
| `cd backend && uv run pytest tests/settlement/test_event_settle_router.py -x` green (9 tests) | SUMMARY 16-04 claims green; 9 test functions confirmed in code | PASS (code evidence) |
| `cd backend && uv run pytest tests/catalog/test_wiring.py tests/markets/test_public_router.py -x` green | SUMMARY 16-05 claims green; wiring confirmed in main.py | PASS (code evidence) |

Note: Full Linux CI is the authoritative gate; per the project memory, Windows worktree testcontainers flake on the full suite. Per-module runs are the correct validation approach here.

---

### Probe Execution

No `probe-*.sh` files declared or discovered for this phase. The phase uses `uv run pytest` per-module as its verification contract. Step 7c: SKIPPED (no probe scripts; pytest per-module is the equivalent mechanism).

---

### Requirements Coverage

| Requirement | Phase 16 Plan | Description | Status | Evidence |
|-------------|---------------|-------------|--------|----------|
| BRW-01 | 16-02 | Indexed text search via pg_trgm + ILIKE, local only | SATISFIED | `service.py:242,256` ILIKE bound params; no Gamma proxy; `test_search_local_only` confirms local-only |
| BRW-02 | 16-02 | Browse by category; `GET /events/{slug}` per-outcome rows | SATISFIED | `service.py:243,257` category filter; `router.py:51-75` event detail with `EventOutcomeRead` rows |
| BRW-03 | 16-02 | Status filter: open / closing soon / resolved | SATISFIED | `service.py:226-244` SQL filters; `_event_matches_status` derived-event map; `test_status_filter` covers partially_resolved→open and void→resolved |
| BRW-04 | 16-02 | Sort: volume / closing soonest / newest | SATISFIED | `service.py:272-280` Python sort; event volume = `sum(child.volume)` at `service.py:154`; `test_sort` covers all three |
| BRW-05 | 16-02 | Bounded LIMIT 100, no pagination, every combo explicit-empty | SATISFIED | `CATALOG_LIMIT=100`; `[:CATALOG_LIMIT]` slice; `test_empty_combos` exercises 4 empty combos all returning `200+[]` |
| EVA-01 | 16-03 | Admin create house multi-outcome event (title, category, N outcomes + labels + initial odds) | SATISFIED | `event_service.py:635-695` + `_add_event_child:758-806`; `test_create_event_creates_group_and_children` DB-verifies one HOUSE group + N children with YES/NO pairs |
| EVA-02 | 16-03 | Admin edit pre-bet, lock after first bet → 423 | SATISFIED | `event_router.py:148-155` `event_has_bets` → 423 `EVENT_LOCKED`; `event_has_bets:809-819` uses `EXISTS(bets)` not `bet_count`; test confirms 423 with real committed bet |
| EVA-03..06 HTTP surface | 16-04 | resolve/void/reverse HTTP endpoints expose Phase-15 EventService | SATISFIED | `event_router.py:167-297` three endpoints with stateless preview/execute; drift_count==0 asserted in settle tests via `_assert_ledger_clean()` |

**Note on REQUIREMENTS.md traceability table:** EVA-01 and EVA-02 are still shown as "Pending" in the table (the doc was not updated post-execution). The code evidence confirms both are fully implemented and tested.

---

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| `event_service.py:417` | `DEFERRED (Pitfall 6 — known limitation, NOT a Phase-15 bug)` | INFO | This is a documented design comment about re-resolution-after-reverse being out of scope (Phase 15 decision, carried forward). Not a TBD/FIXME/XXX debt marker. No follow-up reference needed — the text itself is the documentation. |

No TBD, FIXME, or XXX markers found in any Phase-16-modified file. No stubs. No empty implementations. No hardcoded empty returns in service paths.

---

### Locked Decisions — Code Compliance

| Decision | Status | Evidence |
|----------|--------|----------|
| Approach B (two bounded queries merged in Python) | VERIFIED | `service.py:220-270` two independent `select()` queries with `limit(CATALOG_LIMIT)` each |
| Stateless confirm (no server-side state) | VERIFIED | Preview branches are pure read (load + guards); no session writes, no cache entries |
| `EXISTS(bets)` edit-lock (not `bet_count` dead column) | VERIFIED | `event_service.py:809-819`; `bet_count` absent from all new code |
| ValueError → HTTP map | VERIFIED | `event_router.py:83-100` maps all four ValueError patterns |
| Local-only search (no Gamma proxy) | VERIFIED | `service.py:242,256` ILIKE only; `text(` absent; no Gamma import in catalog module |
| Money as strings | VERIFIED | `field_serializer` on `volume` and `yes_price` in both catalog and event schemas |
| EVT-07 ≥2-child gate | VERIFIED | `service.py:264` `if len(children) < 2: continue`; `router.py:62` `if group is None or len(children) < 2: raise HTTPException(404)` |
| `from __future__ import annotations` absent from routers | VERIFIED | Neither `catalog/router.py` nor `settlement/event_router.py` contain the import; both carry the load-bearing comment explaining why |

---

### Human Verification Required

None. Phase 16 is explicitly backend-only and testable without UI. All success criteria are fully verifiable through code inspection and the 29 integration tests.

---

### Gaps Summary

No gaps. All 18 must-haves verified. All 4 ROADMAP success criteria met. All 7 requirement IDs (BRW-01..05, EVA-01, EVA-02) plus the EVA-03..06 HTTP surface are delivered and substantiated in code.

---

_Verified: 2026-06-05T21:04:34Z_
_Verifier: Claude (gsd-verifier)_
