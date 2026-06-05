# Phase 16: Catalog & Event API + House Event CRUD - Research

**Researched:** 2026-06-05
**Domain:** HTTP contract over an existing FastAPI + SQLAlchemy 2.0 async + Postgres 16 backend (catalog read endpoints + admin house-event CRUD + admin resolve/void/reverse surface)
**Confidence:** HIGH (every claim grounded in the phase-branch source; zero new deps, zero new migration)

## Summary

Phase 16 is a **pure HTTP-surface phase**. The engine — `MarketGroup`/`Market` model (Phase 13), the curated Gamma sync (Phase 14), the `EventService.resolve_event/void_event/reverse_event` + `derive_event_status` settlement layer (Phase 15), the `pg_trgm` GIN + category + status indexes (Phase 13 migration 0011) — all already exist on the branch and are reused **byte-for-byte**. The work is: (1) a bounded `GET /api/v1/catalog` returning a unified `{type: market|event}` list with search/category/status/sort; (2) `GET /events/{slug}` + `GET /categories`; (3) `POST/PATCH /admin/events` house-event create + edit-lock; (4) the admin `resolve|void|reverse` endpoints that expose the Phase-15 service with a **stateless two-step `confirm` preview**; and (5) keep the legacy `GET /api/v1/markets` unchanged.

The single biggest design decision — catalog query shape — resolves to **two bounded queries merged + sorted + sliced in Python under a final `LIMIT 100`** (Approach B), NOT a SQL `UNION ALL`. Rationale below: an event's derived status and its volume are **not columns** (status is a Python function over child rows; `market_groups` has no volume column), so a SQL-level `UNION` cannot filter/sort by them without materialising the same child-row joins anyway. Approach B keeps the projection readable, reuses the proven `selectinload` eager-load discipline, and is provably bounded because each sub-query is itself `LIMIT 100`.

**Primary recommendation:** Build a new `app/catalog/` feature package (router + service + schemas) for the public reads, and put the admin event endpoints in `app/settlement/event_router.py` (mirroring `settlement/router.py`) since they expose `EventService`. Reuse the `MarketListItem`/`OutcomeRead` schema conventions, the `DecimalStr`/`field_serializer` money-as-string rule, the `selectinload(MarketGroup.markets).selectinload(Market.outcomes)` chain, and the settlement endpoint→service session choreography (`admin_id = admin.id`; `await session.rollback()`; let `EventService` own its per-child sessions). No new dependency. No new migration.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Catalog browse/search/filter/sort (`GET /catalog`) | API / Backend (`app/catalog/service.py`) | Database (GIN trgm + B-tree indexes) | Read projection over `markets` ∪ `market_groups`; UI tier (Phase 17) only renders |
| Event detail assembly (`GET /events/{slug}`) | API / Backend | Database (eager-load) | Per-outcome child rows + derived status; pure read |
| Category list (`GET /categories`) | API / Backend | Database (`ix_*_category`) | `DISTINCT category` union, non-empty only (CAT-06) |
| House-event create (`POST /admin/events`) | API / Backend (transactional) | Database (binary-only trigger) | One `MarketGroup` + N children in one request tx; admin-gated |
| Event edit-lock (`PATCH /admin/events`) | API / Backend | Database (`bets` EXISTS) | Pre-bet mutation; lock derived from `bets`, not a column |
| Event resolve/void/reverse (`POST /admin/events/{id}/...`) | API / Backend (thin) | **Phase-15 `EventService`** (owns money + sessions) | Endpoint validates + maps `ValueError`→HTTP + computes preview; service does the settlement loop |
| Two-step confirm preview | API / Backend (non-mutating read) | — | Stateless `confirm:bool`; preview computed read-only, execute calls the service |

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BRW-01 | Text-search the catalog by event/market title (`pg_trgm` GIN + ILIKE) | §Pattern 1 (catalog query, Approach B) + §Pattern 2; existing GIN indexes `ix_markets_question_trgm` / `ix_market_groups_title_trgm` (migration 0011:146-159) — no new index |
| BRW-02 | Browse by category (chips); empty categories not rendered + event detail | §Pattern 4 (categories union, CAT-06) + §Pattern 3 (event detail assembly) |
| BRW-03 | Filter by status (open / closing soon / resolved) | §Pattern 1 + §Derived event status in a SQL filter; market enum vs derived event status reconciliation |
| BRW-04 | Sort by volume / closing soonest / newest | §Pattern 1 (Python merge-sort under LIMIT; event volume = SUM(children)) |
| BRW-05 | Bounded browse, every filter combo → explicit empty/zero state | §Pattern 1 (`LIMIT 100`, no pagination) + §Common Pitfall 1 |
| EVA-01 | Admin creates a house multi-outcome event (title, category, N outcomes w/ label + odds) | §Pattern 5 (house-event create; mirrors `adapter.py` group-create + `MarketService.create_market` YES/NO body) |
| EVA-02 | Admin edits a house event while zero bets; locks after first bet (mirrors ADM-07) | §Pattern 6 (edit-lock via `bets` EXISTS, HTTP 423) |
| (EVA-03..06 — service exists) | HTTP surface for resolve/void/reverse + mirrored read-only | §Pattern 7 (two-step confirm) + §Pattern 8 (`ValueError`→HTTP mapping) |
</phase_requirements>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **`GET /api/v1/catalog`** returns ONE bounded list of catalog **items**, each discriminated `type: "market"` (standalone binary) or `type: "event"` (multi-outcome `MarketGroup`). Single-outcome groups (EVT-07) surface as a plain `market`, never an `event`.
- **`LIMIT 100` total** after filters + sort. Curated, **no pagination / no infinite scroll**. Every filter combination yields an explicit empty/zero result, never an error.
- **Search = local `pg_trgm` GIN + ILIKE only** over `markets.question` + `market_groups.title`. **NEVER** proxy to Gamma `/public-search`.
- **Filters**: `category` (exact), `status ∈ {open, closing_soon, resolved}`, `q` (search). `closing_soon` = `open` AND `deadline <= now + 48h`. Map the stored market enum and the derived event status into this set.
- **Sort** = `{volume, closing_soonest, newest}` (default: volume).
- **`GET /events/{slug}`** by `market_groups.slug`; **only `≥2`-outcome groups**; per-outcome child rows + derived status; eager-load `selectinload(MarketGroup.markets).selectinload(Market.outcomes)`. 1-child / non-existent slug → 404.
- **`GET /categories`** = union of non-empty categories over `markets` ∪ `market_groups`, only those with ≥1 visible item (CAT-06). Names only in Phase 16 (per-category counts = P2-03, Phase 17).
- **`POST /admin/events`** body `{title, category, deadline, outcomes: [{label, initial_odds}, …]}`, **min 2 outcomes**. Creates one `MarketGroup` (source=HOUSE) + N child binary YES/NO markets, each `group_item_title = label`, YES seeded at `initial_odds`. Slug auto-slugify w/ uniqueness suffix; optional admin override.
- **Edit-lock = `EXISTS(SELECT 1 FROM bets WHERE market_id IN (children))`** — NOT the dead `markets.bet_count` column. `PATCH` editable pre-bet only; after first bet → **HTTP 423** (mirrors market `CRITERIA_LOCKED`).
- **Admin resolve/void/reverse paths**: `POST /admin/events/{group_id}/resolve|void|reverse`, path param = group UUID. **Two-step confirm is stateless**: `confirm: bool` in body; `confirm:false`/absent → 200 non-mutating preview; `confirm:true` → execute. `justification` mandatory non-empty (`Field(min_length=1)`, `extra="forbid"`).
- **`resolve` winning input** = `winning_outcome_id` (the winning child's **YES** `Outcome` UUID). Validate it belongs to a child of this group before calling the service.
- **`ValueError` → HTTP**: mirrored group → 409; blank justification → 422; invalid winning-outcome → 422; group not found → 404.

### Claude's Discretion
- Exact response-schema field names + `type` discriminator key (consistent with `MarketListItem`/`OutcomeRead`).
- How `void` / `partially_resolved` map into the public `{open, closing_soon, resolved}` filter (pick the most "looks-real" mapping).
- The `closing_soon` threshold value (48h recommended).
- Catalog query: one UNION vs two queries merged in Python (provided bounded to 100 + every combo returns explicit empty set).
- Preview-response shape (impact summary fields).
- Whether add/remove-outcome lives in `PATCH` or a sub-route (pre-bet only + 423 after first bet).
- Slugify helper choice (reuse existing house-market slug logic if present).
- Test layout (endpoint integration tests per endpoint family + auth-gate negatives).

### Deferred Ideas (OUT OF SCOPE)
- Browse UI, event detail page, admin event-ops UI, white-label `--brand-*` on catalog surfaces (BRW-06, EVT-02..05) — **Phase 17**.
- Per-category count chips, featured "Top events" shelf, live WS odds on rows (P2-01..03) — **Phase 17 stretch**.
- Seed/demo multi-outcome harness (DEMO-01..04) — **Phase 18**.
- True refund-on-cancel (stake refund) — out of scope (void = all-children-NO).
- Cursor/offset pagination of the catalog — out of scope (curated/bounded).

## Project Constraints (from CLAUDE.md + spike-findings)

- **Branch-per-phase**: work on `gsd/phase-16-catalog-event-api-house-event-crud`, never `main`. 1 PR/phase. Only Pol merges. Commits as `Agustin <predictionmarkets.solutions@gmail.com>`.
- **Product is English** (UI/copy/schemas/docstrings); conversation Spanish.
- **Money = `Decimal` / `Numeric(18,4)`, never float** (`Money` alias, `db/types.py:20`). Odds = `Numeric(8,6)` (`Odds`, `db/types.py:23`). On the wire money/odds = **JSON strings** via `field_serializer(when_used="json")` / `DecimalStr` (`settlement/schemas.py:16-19`).
- **`scripts/lint_money_columns.py`** AST-walks every `*models.py` — but Phase 16 adds **no models** (no new column), so the lint is a no-op here. Keep it that way (no new migration expected).
- **Windows worktree is unreliable** for the full backend suite (testcontainers contention flake + ruff `check`/`format` flip-flop 148↔202). Verify **per-module** locally (`cd backend && uv run pytest tests/catalog -x`); trust **Linux CI** for the full suite + ruff + mypy. [[xprediction-backend-fullsuite-testcontainers-flake]]
- **No `corepack pnpm`** (frontend rule; irrelevant this phase — backend-only).

## Standard Stack

**Zero new dependencies.** Every tool below is already pinned in `backend/pyproject.toml` and in use on the branch.

### Core
| Library | Version (pinned) | Purpose | Why Standard |
|---------|------------------|---------|--------------|
| FastAPI | `>=0.115.7,<0.116.0` | HTTP routers, `Annotated[..., Depends()]`, `Query` validation | Already the app framework; new routers register in `main.py` |
| SQLAlchemy | `>=2.0.43,<2.1` | async ORM, `select()`, `selectinload`, `func.*` | 2.0 async is the data layer; catalog queries are `select()` |
| Pydantic | `>=2.10,<3.0` | request/response schemas, `field_serializer`, `extra="forbid"` | All schemas are pydantic v2; money-as-string via serializers |
| asyncpg | `>=0.30,<0.32` | Postgres async driver | Engine driver (`postgresql+asyncpg`) |
| Postgres + pg_trgm | 16 + bundled `pg_trgm` | GIN trigram substring search (BRW-01) | Extension enabled in migration 0011:75; indexes already built |
| python-slugify | `>=8.0,<9.0` | `generate_slug()` for event slugs (EVA-01) | `markets/models.py:33` `generate_slug()` already wraps it |
| fastapi-users | `>=15.0.5,<16.0.0` | `current_active_admin` Bearer/superuser gate | Reuse `from app.auth.deps import current_active_admin` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| httpx | `>=0.28,<0.29` | `AsyncClient` + `ASGITransport` for endpoint tests | Every integration test (existing pattern) |
| testcontainers | (dev) | real Postgres 16 in tests | `engine` fixture (`conftest.py:137`) |
| pytest / pytest-asyncio | (dev) | `loop_scope="session"` markers | All tests |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Python merge-sort under LIMIT (catalog) | SQL `UNION ALL` over a normalized projection | UNION cannot sort/filter by derived event status (Python fn over children) or event volume (no column) without joining children anyway → no real win, much harder SQL. See §Catalog query decision. |
| New `app/catalog/` package | Add catalog endpoint onto `markets/router.py` | A new package keeps the legacy `markets` surface untouched (back-compat success criterion) and isolates the unified-item schema. Recommended. |

**Installation:** none. (Run `cd backend && uv sync` only if the venv is cold.)

## Package Legitimacy Audit

> Not applicable — Phase 16 installs **zero** new packages. All libraries above are already pinned in `backend/pyproject.toml` and shipped in Phases 1–15. No registry lookups, no slopcheck needed.

## Architecture Patterns

### System Architecture Diagram

```
                         ┌─────────────────────────────────────────────┐
   PUBLIC (no auth)      │                                             │
   GET /api/v1/catalog ──┤─► CatalogService.list_catalog()             │
     ?q&category&status  │     ├─ query A: standalone markets          │
     &sort               │     │   (group_id IS NULL, visible status)  │──► markets
                         │     │   ILIKE question + category + status  │   (GIN trgm,
                         │     │   sort + LIMIT 100                     │    ix_category,
                         │     ├─ query B: market_groups (≥2 children) │    status_volume)
                         │     │   selectinload children+outcomes      │
                         │     │   ILIKE title + category              │──► market_groups
                         │     │   LIMIT 100                            │    (GIN trgm,
                         │     ├─ derive_event_status(children) (P15)   │     ix_category)
                         │     ├─ event status → public filter map      │
                         │     ├─ event volume = SUM(child.volume)      │
                         │     └─ merge A+B → sort → slice[:100]        │
                         │         → list[CatalogItem{type,...}]        │
   GET /events/{slug} ───┤─► by market_groups.slug, ≥2 children only    │──► market_groups
                         │     selectinload(markets).selectinload(      │   + markets
                         │       outcomes) → per-outcome YES price      │   + outcomes
                         │     + derive_event_status → EventDetail      │
   GET /categories ──────┤─► DISTINCT category over markets ∪ groups    │──► (ix_category)
                         │     non-empty + ≥1 visible item (CAT-06)     │
                         └─────────────────────────────────────────────┘

                         ┌─────────────────────────────────────────────┐
   ADMIN (Bearer JWT,    │                                             │
   current_active_admin) │                                             │
   POST /admin/events ───┤─► one tx on request session:               │──► market_groups
     {title,category,    │     create MarketGroup(source=HOUSE,slug)   │   + markets
      deadline,outcomes} │     for each outcome: create child YES/NO   │   + outcomes
                         │       market (group_id, group_item_title)   │   (binary trigger
                         │       seed YES outcome @ initial_odds        │    fires per child)
                         │     commit → 201 EventDetail                 │
   PATCH /admin/events/  │─► EXISTS(bets WHERE market_id IN children)?  │──► bets (EXISTS)
        {group_id}       │     ├─ yes → 423 EVENT_LOCKED               │
                         │     └─ no  → mutate metadata/outcomes, 200  │
   POST .../{id}/resolve │─► confirm flag:                             │
            /void        │     ├─ false/absent → read-only PREVIEW 200 │
            /reverse     │     │    (load group+children, derive end   │
                         │     │     status, winner/loser counts)      │
                         │     └─ true → admin_id=admin.id;            │──► EventService
                         │         session.rollback();                 │   .resolve/void/
                         │         EventService.<op>(...) [P15]         │   reverse_event
                         │         → maps ValueError → 4xx → 200       │   (OWNS per-child
                         │                                             │    fresh sessions)
                         └─────────────────────────────────────────────┘
```

A reader traces the primary use case (browse → filter → sort → bounded list) by following query A + query B into the merge/sort/slice. The admin write path traces create → bet-lock-check → settle-with-confirm.

### Recommended Project Structure
```
backend/app/
├── catalog/                    # NEW — public reads (keeps markets/ untouched)
│   ├── __init__.py
│   ├── router.py               # public_catalog_router (prefix /api/v1) — /catalog, /events/{slug}, /categories
│   ├── service.py              # CatalogService.list_catalog / get_event / list_categories
│   └── schemas.py              # CatalogItem (discriminated), EventDetail, EventOutcomeRead, CategoryList
├── settlement/
│   ├── event_router.py         # NEW — event_admin_router: POST /admin/events, PATCH, resolve/void/reverse
│   ├── event_service.py        # EXISTS (Phase 15) — reused unchanged
│   ├── router.py               # EXISTS — the pattern to mirror
│   └── schemas.py              # EXISTS — DecimalStr lives here; add event request/response schemas here or in catalog
└── main.py                     # register public_catalog_router + event_admin_router (deferred import block :180-203)
```

> The admin event CRUD could equally live in a new `app/events/` package. Recommendation: put **reads** in `app/catalog/` and **admin event ops** in `app/settlement/event_router.py` because they consume `EventService` and must replicate the exact settlement session choreography — co-locating keeps that landmine knowledge in one module. Whichever the planner picks, register both routers in `main.py`.

### Pattern 1: Catalog query — two bounded queries merged in Python (Approach B)

**What:** Return one `LIMIT 100` list of `CatalogItem{type: "market"|"event"}` combining standalone `markets` (`group_id IS NULL`) and `market_groups` with ≥2 children.

**When to use:** This is THE catalog endpoint. Default and recommended shape.

**Why Approach B (Python merge) over Approach A (SQL `UNION ALL`):**
- An **event's status is derived in Python** (`derive_event_status`, `event_service.py:98`) over child `Market.status` + `is_yes_winner` rows — it is **not a column**. A SQL `UNION` that filters/sorts by event status would have to reproduce that whole projection in SQL (a correlated aggregate over children + YES-winner detection per group). Doable but fragile and duplicates the Phase-15 source of truth.
- An **event's volume is not a column** either (`market_groups` has no money column — `models.py:200-275`, deliberate per EVT-06). For the `volume` sort, an event's volume = `SUM(child.volume)`, again a child aggregate.
- Postgres *can* sort + `LIMIT` a `UNION ALL` (wrap it as a subquery and `ORDER BY ... LIMIT 100` the outer) — but only over columns present in the unified projection. Since the two sort-critical signals (event status, event volume) require child joins regardless, the UNION buys nothing and costs a much harder-to-read query + a normalized projection that flattens two very different row shapes.
- Approach B is **provably bounded**: each sub-query is itself `LIMIT 100`, so the merged candidate set is ≤200, sorted in Python, sliced `[:100]`. Memory + CPU are trivially bounded.

**Approach B algorithm (in `CatalogService.list_catalog`):**
```python
# Source: NEW app/catalog/service.py — composes existing patterns
# (markets/service.py:244 list_home_markets + :274 list_markets query-building;
#  event_service.py:98 derive_event_status; :146 _yes_outcome_id case-insensitive YES)
from sqlalchemy import func, select, exists
from sqlalchemy.orm import selectinload

CATALOG_LIMIT = 100
CLOSING_SOON_WINDOW = timedelta(hours=48)   # Claude's discretion — 48h

# --- query A: standalone binary markets (group_id IS NULL) ---
a = (
    select(Market)
    .where(Market.group_id.is_(None))
    .where(Market.status.in_((MarketStatus.OPEN.value, MarketStatus.RESOLVED.value)))
    .options(selectinload(Market.outcomes))   # lazy="raise" → MUST eager-load
)
if q:
    a = a.where(Market.question.ilike(f"%{q}%"))     # GIN trgm index serves this
if category:
    a = a.where(Market.category == category)         # exact (BRW-02)
# status filter mapped to the stored market enum (see §status mapping)
a = _apply_market_status_filter(a, status)
a = a.limit(CATALOG_LIMIT)

# --- query B: multi-outcome events (market_groups with ≥2 children) ---
b = (
    select(MarketGroup)
    .options(selectinload(MarketGroup.markets).selectinload(Market.outcomes))
)
if q:
    b = b.where(MarketGroup.title.ilike(f"%{q}%"))   # GIN trgm on title
if category:
    b = b.where(MarketGroup.category == category)
b = b.limit(CATALOG_LIMIT)

markets = (await session.execute(a)).scalars().all()
groups  = (await session.execute(b)).scalars().all()

items: list[CatalogItem] = []
for m in markets:
    items.append(_market_to_item(m))                 # type="market"
for g in groups:
    children = list(g.markets)
    if len(children) < 2:                            # EVT-07 — 1-child stays a market path; skip here
        continue
    ev_status = derive_event_status(_child_statuses(children))   # Phase-15 fn
    public = _event_status_to_public(ev_status)      # {open|closing_soon|resolved|None-if-hidden}
    if status and public != status:                  # post-derive status filter (bounded by LIMIT)
        continue
    items.append(_group_to_event_item(g, children, ev_status))   # type="event"

items = _sort_catalog(items, sort)                   # volume desc | closing_soonest | newest
return items[:CATALOG_LIMIT]
```

**Notes that matter:**
- The status filter on **events** is a **post-derive Python filter** (you cannot push the derived status into SQL cheaply). It stays bounded because query B already capped at 100. The status filter on **standalone markets** *can* push to SQL via the stored enum (`ix_markets_status_volume_24hr` composite helps).
- `closing_soon` (a *derived* status for markets too) = `status == OPEN` AND `deadline <= now + 48h`. Compute in SQL for markets (`Market.deadline <= now+48h`) and in Python for events (an event is `closing_soon` if its derived status is `open` and the *earliest open child deadline* ≤ now+48h — recommend: min child deadline among unresolved children).
- **Event volume for the `volume` sort** = `sum(child.volume for child in children)` (Decimal). Standalone market volume = `Market.volume`. Both are `Decimal`; sort descending.
- **`newest`** = `created_at desc` (both `Market.created_at` and `MarketGroup.created_at` exist).
- Wrap the assembled item in the discriminated schema (§schema shape).

### Pattern 2: pg_trgm substring search — local rows ONLY

**What:** `ILIKE '%term%'` on `markets.question` and `market_groups.title`, served by the existing GIN trigram indexes.

**Confirmed indexes (no new migration):**
- `ix_markets_question_trgm` GIN `gin_trgm_ops` on `markets.question` (migration 0011:153-159; declared in `models.py:52-57`).
- `ix_market_groups_title_trgm` GIN `gin_trgm_ops` on `market_groups.title` (migration 0011:146-152; declared `models.py:218-223`).
- `pg_trgm` extension enabled FIRST in migration 0011:75.

A `gin_trgm_ops` GIN index accelerates **infix** `ILIKE '%term%'` (3+ char terms). For `q` shorter than 3 chars the planner may seq-scan — acceptable on a curated/bounded catalog. **Never** route `q` to Gamma `/public-search` (explicit anti-feature, REQUIREMENTS.md:87). `ILIKE` (not `LIKE`) gives case-insensitive matching.

**Anti-pattern:** building the `q` filter by string-interpolating into raw SQL. Use the SQLAlchemy `.ilike(f"%{q}%")` bound param (the `%…%` wrapper is data, not SQL) — never `text(f"... ILIKE '%{q}%'")`.

### Pattern 3: Event detail assembly (`GET /events/{slug}`, BRW-02)

**What:** Look up by `market_groups.slug` (UNIQUE, `models.py:248-253`), serve only ≥2-child groups, eager-load children + outcomes, return per-outcome rows (each child's `group_item_title` label + its YES price) and the derived status.

```python
# Source: composes _load_group_with_children (event_service.py:129) +
#         get_market_by_slug (markets/service.py:321) + _yes_outcome_id case-insensitive YES
async def get_event(session, slug: str) -> MarketGroup | None:
    return (
        await session.execute(
            select(MarketGroup)
            .where(MarketGroup.slug == slug)
            .options(selectinload(MarketGroup.markets).selectinload(Market.outcomes))
        )
    ).scalar_one_or_none()

# in the router:
group = await CatalogService.get_event(session, slug)
children = list(group.markets) if group else []
if group is None or len(children) < 2:           # EVT-07: 1-child / missing → 404
    raise HTTPException(404, "Event not found")
```

**Per-outcome YES price (the "current_odds" of each outcome row):** the event's outcome N is child market N; its displayed price = that child's **YES** `Outcome.current_odds`, matched **case-insensitively** (`label.upper() == "YES"` — house="YES", mirrored Polymarket="Yes"; mirrors `_yes_outcome_id`, `event_service.py:146-160` and `markets/service.py:182,374-378`). Per-outcome schema row carries: `label` (= `child.group_item_title`), `yes_outcome_id`, `yes_price` (str), optionally child `market_id`/`slug`/`status` so the UI (Phase 17) can deep-link a bet onto the child.

**Derived status:** call `derive_event_status` over the loaded children — reuse the exact `ChildStatus` construction from `_derive_status` (`event_service.py:598-619`): `is_yes_winner = child.winning_outcome_id is not None and child.winning_outcome_id == <child's YES outcome id>`.

### Pattern 4: Categories union (`GET /categories`, CAT-06)

**What:** `DISTINCT category` across both tables, non-empty, **only categories with ≥1 visible item** (never surface an empty category).

```python
# Source: NEW — two DISTINCT selects unioned in Python (or a SQL UNION of two DISTINCTs)
async def list_categories(session) -> list[str]:
    m_cats = (
        await session.execute(
            select(Market.category)
            .where(Market.category.isnot(None), Market.category != "")
            .where(Market.group_id.is_(None))                 # standalone only (event cats come from groups)
            .where(Market.status.in_((MarketStatus.OPEN.value, MarketStatus.RESOLVED.value)))
            .distinct()
        )
    ).scalars().all()
    g_cats = (
        await session.execute(
            select(MarketGroup.category)
            .where(MarketGroup.category.isnot(None), MarketGroup.category != "")
            .distinct()
        )
    ).scalars().all()
    return sorted(set(m_cats) | set(g_cats))
```

`ix_markets_category` / `ix_market_groups_category` (migration 0011:174-175) serve the `WHERE category` predicate. CAT-06 ("never surface an empty category") is satisfied because the query only returns a category if at least one row carries it — empty categories produce no row. **Names only** in Phase 16 (counts = P2-03, Phase 17). Optionally include "has an event of ≥2 children" filtering for group categories, but the simple form above already meets CAT-06 (a group row exists ⇒ category is non-empty).

### Pattern 5: House-event create (`POST /admin/events`, EVA-01)

**What:** In ONE request-session transaction, create a `MarketGroup(source=HOUSE)` + N child binary YES/NO markets, each wired via `group_id` + `group_item_title=label`, YES outcome seeded at `initial_odds`.

**Canonical precedent — the Polymarket adapter already does exactly this group+children write** (`integrations/polymarket/adapter.py:325-448`): `_upsert_market_group` creates the `MarketGroup`, then each child is stamped with `group_id` + `group_item_title`. Phase 16's house path mirrors it but uses the request session + the `MarketService.create_market` YES/NO body (`markets/service.py:38-111`) instead of the Gamma upsert.

**Reuse strategy (recommended):** Do NOT try to call `MarketService.create_market` unchanged per child — it does **not** accept `group_id`/`group_item_title` (verified: no `group_id` reference anywhere in `markets/service.py`). Instead, in a new `EventService.create_house_event` (or a `MarketService.create_event` sibling), replicate the create_market body per child and add the two group fields:

```python
# Source: composes MarketService.create_market (markets/service.py:38-111, the YES+NO body)
#         + adapter group-create idiom (adapter.py:325-448) + generate_slug (models.py:33)
async def create_house_event(session, admin, body) -> MarketGroup:
    # 1) group with a unique slug (retry on collision via SAVEPOINT, mirror create_market:44-69)
    group = MarketGroup(
        title=body.title,
        source=MarketSourceEnum.HOUSE.value,
        category=body.category,
        slug=body.slug or generate_slug(body.title),   # generate_slug appends a uuid6 suffix already
    )
    session.add(group)
    await session.flush()                                # group.id available
    # 2) one binary YES/NO child per outcome (the binary trigger fires per child — never a 3rd outcome)
    for oc in body.outcomes:                             # len >= 2 enforced in the schema
        child = Market(
            question=oc.label,                           # or f"{body.title}: {oc.label}" — discretion
            slug=generate_slug(oc.label),
            resolution_criteria=body.resolution_criteria or "...",   # Market.resolution_criteria is NOT NULL
            deadline=body.deadline,                      # shared deadline applied to each child
            category=body.category,
            source=MarketSourceEnum.HOUSE.value,
            status=MarketStatus.OPEN.value,
            group_id=group.id,                           # EVT-01 child stamp
            group_item_title=oc.label,                   # per-outcome label
        )
        session.add(child)
        await session.flush()                            # child.id for the outcomes + binary trigger
        odds_no = Decimal("1") - oc.initial_odds
        session.add_all([
            Outcome(market_id=child.id, label="YES", initial_odds=oc.initial_odds, current_odds=oc.initial_odds),
            Outcome(market_id=child.id, label="NO",  initial_odds=odds_no,        current_odds=odds_no),
        ])
        await session.flush()                            # 2nd outcome insert trips the trigger IF a 3rd were added
    await AuditService.record(session, actor=f"user:{admin.id}", event_type="event.created",
                              payload={"group_id": str(group.id), "title": body.title,
                                       "child_count": len(body.outcomes)})
    await session.commit()
    return group
```

**Hard constraints:**
- **Binary-only trigger** `trg_binary_outcomes_only` (`BEFORE INSERT ON outcomes`, raises when `COUNT(*) >= 2` for the `market_id`; migration `0003:170-192`). Each child gets **exactly YES + NO** — never a 3rd outcome. The multi-outcome-ness lives at the `market_groups` level, not in a single market.
- **`Market.resolution_criteria` is NOT NULL** (`models.py:75`). The event body either supplies a shared `resolution_criteria` or the service synthesizes a sane default per child (e.g. the event title + label). Decide in the schema.
- **Slug uniqueness**: `generate_slug` already appends a 6-hex suffix (`models.py:33-36`), so collisions are improbable; still wrap the group insert in the `begin_nested()` + retry idiom from `create_market:44-69` (or the adapter's SAVEPOINT retry, `adapter.py:374-378`) for safety. An admin-supplied `slug` override skips the slugify.
- **Min 2 outcomes** enforced in the request schema (`Field(min_length=2)` on the `outcomes` list) — grouping applies only to ≥2 (EVT-07). Surface a 422 for `<2`.
- Money/odds in the body validate as `Decimal` with `gt=0, lt=1` for `initial_odds` (mirror `MarketCreate.initial_odds_yes`, `markets/schemas.py:71`).

### Pattern 6: Event edit-lock (`PATCH /admin/events/{group_id}`, EVA-02)

**What:** Editable only while **no child market has any bet**. Lock predicate spans all children.

```python
# Source: bets/models.py (Bet.market_id indexed :50 + bets_market_idx :76);
#         edit-lock mirrors markets/service.py:136-143 (CRITERIA_LOCKED 423) but
#         uses EXISTS(bets) NOT the dead bet_count column.
from sqlalchemy import exists, select
child_ids = select(Market.id).where(Market.group_id == group_id)
has_bets = (
    await session.execute(
        select(exists().where(Bet.market_id.in_(child_ids)))
    )
).scalar()
if has_bets:
    raise HTTPException(
        status_code=423,
        detail={"code": "EVENT_LOCKED",
                "reason": "Event outcomes/metadata cannot be changed after a bet has been placed"},
    )
# else: mutate title/category/deadline/per-outcome label+odds/add-remove outcome, commit
```

**Why `EXISTS`, NOT `bet_count`:** `markets.bet_count` is a **dead column** — never incremented in app code (confirmed: `bet_count` only read in `markets/service.py:136`, never written anywhere; CONTEXT.md:35,78). The real "has bets" signal is `EXISTS(SELECT 1 FROM bets WHERE market_id IN (children))`. `bets.market_id` is indexed (`bets/models.py:50,76`) so the `EXISTS` is cheap. Return **HTTP 423** (`status.HTTP_423_LOCKED`) mirroring the market `CRITERIA_LOCKED` 423 (`markets/service.py:138`).

**Editable fields pre-bet:** title, category, deadline (apply to all children), per-outcome label (`group_item_title`) + initial odds, add/remove outcome. Adding an outcome = create a new binary child under the group; removing = delete the child (no bets ⇒ no financial rows ⇒ safe; the FK is `ON DELETE SET NULL` but with no bets you can hard-delete the child + its 2 outcomes). **Discretion:** add/remove can live in `PATCH` (whole-outcome-list replace) or sub-routes `POST/DELETE /admin/events/{id}/outcomes` — either is fine provided pre-bet-only + 423 after first bet.

### Pattern 7: Stateless two-step confirm (resolve/void/reverse)

**What:** NO backend precedent — the market resolve endpoint takes an already-confirmed body (`settlement/router.py:5-10` docstring: "The two-step propose+confirm flow is a client concern"). Phase 16 designs a **stateless** server-side preview: `confirm: bool` in the body; `confirm:false`/absent → 200 non-mutating **preview** of impact; `confirm:true` → execute via `EventService`.

**Preview is a read-only projection** (no token store, no server state):
```python
# Source: NEW settlement/event_router.py — preview reuses _load_group_with_children
#         (event_service.py:129) + derive_event_status (:98) read-only; execute mirrors
#         settlement/router.py:59-96 session choreography.
@event_admin_router.post("/{group_id}/resolve", response_model=EventActionResponse)
async def resolve_event_endpoint(group_id, body: ResolveEventRequest, admin, session, ...):
    # --- PREVIEW branch (confirm false/absent): NON-MUTATING ---
    if not body.confirm:
        group = await _load_group_with_children(session, group_id)
        if group is None:
            raise HTTPException(404, "Event not found")
        if group.source == MarketSourceEnum.POLYMARKET.value:        # mirror service guard
            raise HTTPException(409, "Mirrored events are admin read-only")
        children = list(group.markets)
        # validate winning_outcome_id belongs to a child + is its YES leg (mirror event_service.py:249-282)
        _validate_winning_outcome(children, body.winning_outcome_id)  # → 422 on bad
        return EventActionResponse(
            preview=True,
            group_id=group_id,
            child_count=len(children),
            winners=1, losers=len(children) - 1,                     # resolve: 1 YES winner
            projected_status="resolved",
        )
    # --- EXECUTE branch (confirm true): mutate via Phase-15 service ---
    admin_id = admin.id                       # capture BEFORE rollback (avoid MissingGreenlet)
    await session.rollback()                  # clear autobegun read-tx so the service owns its uow
    try:
        result = await EventService.resolve_event(
            group_id=group_id, winning_outcome_id=body.winning_outcome_id,
            justification=body.justification, actor_user_id=admin_id,
        )
    except ValueError as exc:
        raise _map_event_value_error(exc, group_id)   # §Pattern 8
    return EventActionResponse(preview=False, group_id=group_id,
                               child_count=result.child_count,
                               children_settled=result.children_settled,
                               children_failed=[str(x) for x in result.children_failed],
                               projected_status=result.status)
```

**Preview shapes (discretion — recommended fields):**
- **resolve**: `{preview: true, child_count, winners: 1, losers: child_count-1, projected_status: "resolved", winning_outcome_id}`.
- **void**: `{preview: true, child_count, winners: 0, losers: child_count, projected_status: "void"}` (every child NO; YES bettors lose).
- **reverse**: `{preview: true, child_count, settled_children_to_reverse: <count of children with SETTLED bets>, projected_status: "open"}`.

**Why stateless is correct here:** there is no server-side token store to manage, no expiry, no replay window — the preview is a pure function of current DB state, and `confirm:true` re-derives the same impact at execute time inside the (idempotent) service. The justification (`Field(min_length=1)`, `extra="forbid"`) is required on BOTH branches so a preview also validates the reason early.

**Critical session choreography (mirror `settlement/router.py:71-73`):**
1. Capture `admin_id = admin.id` as a plain value BEFORE any rollback (the service's `begin()/commit()` would expire the dependency-loaded `admin` → `MissingGreenlet`).
2. `await session.rollback()` to clear the autobegun read-tx so the service can open its own unit of work.
3. **Never reuse the request session for the settle loop** — `EventService` opens a **fresh `_get_session_maker()` session per child** (the 23505 dangling-tx landmine; `event_service.py:23-31` docstring, [[xprediction-financial-services-idempotent-tx-chaining]]). The endpoint only calls the service method; it does NOT iterate children itself.
4. For the **preview** branch you may use the request session read-only (`_load_group_with_children`), but do it BEFORE the execute-branch rollback dance — they're mutually exclusive branches, so no conflict.

### Pattern 8: `ValueError` → HTTP mapping

`EventService` raises **`ValueError`** (never `HTTPException`) for mirrored / blank-justification / bad-winning-outcome (`event_service.py:183,194-196,243,264-282`). The endpoint maps:

```python
def _map_event_value_error(exc: ValueError, group_id: UUID) -> HTTPException:
    msg = str(exc)
    if "Mirrored" in msg:                       # _reject_if_mirrored (event_service.py:194)
        return HTTPException(409, detail=msg)    # mirrored group → 409 Conflict
    if "justification" in msg:                   # _require_justification (:183)
        return HTTPException(422, detail=msg)    # blank justification → 422
    if "winning_outcome_id" in msg:              # winner guards (:264-282)
        return HTTPException(422, detail=msg)    # bad winning-outcome → 422
    if "No market group" in msg:                 # missing group (:243)
        return HTTPException(404, detail=msg)    # group not found → 404
    return HTTPException(400, detail=msg)        # defensive fallback
```

> Recommendation: also pre-validate cheap cases (group exists, mirrored, winning-outcome belongs to a child + is its YES leg) in the **endpoint** before calling the service, so the preview branch and the execute branch return identical 4xx for the same bad input. The service's own guards remain the authoritative backstop. The string-matching map above is the fallback for anything that slips through.

### Anti-Patterns to Avoid
- **Iterating children in the endpoint to settle them** — that re-introduces the 23505 dangling-tx bug. Always call `EventService.resolve_event/void_event/reverse_event`, which owns per-child fresh sessions.
- **Reading `markets.bet_count` for the edit-lock** — it's dead/never-incremented. Use `EXISTS(bets)`.
- **Refactoring `GET /api/v1/markets`** — back-compat is a success criterion. The legacy endpoint (`markets/router.py:149-155`, returns a flat `list[MarketListItem]`) must stay shape-identical; a test asserts `isinstance(body, list)` (`test_public_router.py:86`). Add new surfaces, don't touch the old one.
- **Proxying `q` to Gamma `/public-search`** — explicit anti-feature; local rows only.
- **Adding pagination / infinite scroll to `/catalog`** — bounded `LIMIT 100`, no pagination.
- **Floats on the wire** — money/odds serialize as JSON strings via `field_serializer`/`DecimalStr`.
- **`from __future__ import annotations` in the new routers** — breaks FastAPI `Annotated[..., Depends()]` resolution under Python 3.13 (see §Pitfall below). Settlement & wallet-admin routers omit it deliberately.
- **Bare relationship access** on `MarketGroup.markets` / `Market.outcomes` — they're `lazy="raise"`; always `selectinload`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Event status from children | A new status column on `market_groups` | `derive_event_status(children)` (`event_service.py:98`) | EVT-06: status is a derived read-time projection; no stored column exists by design |
| Resolve/void/reverse settlement loop | A per-child settle loop in the endpoint | `EventService.resolve_event/void_event/reverse_event` (`event_service.py:210/320/382`) | Owns idempotency, lock ordering, payouts, per-child audit, 23505-safe fresh sessions |
| YES-outcome matching | `== "YES"` exact compare | `func.upper(label) == "YES"` (`event_service.py:146`, `markets/service.py:182`) | House="YES", mirrored Polymarket="Yes"; case-sensitive silently misses mirrored |
| Slug generation | Custom slugify | `generate_slug(text)` (`markets/models.py:33`) — wraps `python-slugify` + 6-hex suffix | Already collision-resistant; reuse keeps slug format consistent |
| Group + children create | New ad-hoc INSERTs | Mirror `adapter.py:325-448` group-create + `create_market:38-111` YES/NO body | Proven binary-trigger-safe write order |
| Money serialization | `float(decimal)` | `field_serializer(when_used="json")` / `DecimalStr` (`settlement/schemas.py:16`) | Lossless string on the wire (spike requirement; money lint) |
| Pagination scaffold | Cursor/offset logic | Nothing — `/catalog` is `LIMIT 100`, no pagination | Curated/bounded (anti-feature) |
| "Has bets" check | `bet_count` column read | `EXISTS(SELECT 1 FROM bets WHERE market_id IN (...))` | `bet_count` is dead; `bets.market_id` is indexed |

**Key insight:** Phase 16 writes almost no new domain logic — it is glue that *exposes* Phase 13–15 primitives over HTTP. The pitfalls are all about **not re-implementing** the settlement loop, the YES-match, the status derivation, or the money serialization, and about **not breaking** the legacy `/markets` contract.

## Runtime State Inventory

> Phase 16 is **additive HTTP surface** over existing tables — no rename/refactor/migration. This section is included for completeness; most categories are N/A.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — no schema change. `market_groups`/`markets`/`outcomes`/`bets` all pre-exist. House events created via the new endpoint write rows the existing model already supports (`group_id`/`group_item_title` columns exist since migration 0011). | None |
| Live service config | None — no external service config. (Gamma sync is Phase 14, untouched here.) | None |
| OS-registered state | None — no Celery beat / Task Scheduler / cron change. The catalog/event endpoints are request-driven, not scheduled. | None |
| Secrets / env vars | None new. Admin endpoints reuse the existing `current_active_admin` JWT gate (`SECRET_KEY` already set). | None |
| Build artifacts | None — no `pyproject.toml` dependency change ⇒ no `uv` re-lock, no egg-info churn. New `app/catalog/` package is picked up automatically (namespace package). | None |

**Verified by:** reading `markets/models.py` (columns already exist), `config.json` (no migration flag), and confirming zero `pyproject.toml` dependency delta.

## Common Pitfalls

### Pitfall 1: A filter combination returning an error instead of an explicit empty set
**What goes wrong:** `?category=Nonexistent&status=resolved&q=zzz` raises (e.g. `scalar_one()` on no rows) or 500s, violating BRW-05 ("every filter combination has an explicit empty/zero state").
**Why it happens:** using `scalar_one()` where `scalars().all()` is correct, or letting an empty merge raise downstream.
**How to avoid:** The catalog query returns `list[CatalogItem]` — an empty list is the valid empty state (HTTP 200 `[]`). Never `scalar_one()` in the list path. Test every filter axis with a guaranteed-empty input and assert `200 + []`.
**Warning signs:** any `scalar_one()` (not `_or_none`) in `CatalogService.list_catalog`.

### Pitfall 2: `lazy="raise"` relationship access without `selectinload`
**What goes wrong:** `group.markets` or `child.outcomes` raises `InvalidRequestError` at access time (the relationships are `lazy="raise"`, `models.py:184,272-275`).
**Why it happens:** forgetting the eager-load chain when assembling event items or the detail response.
**How to avoid:** Always `selectinload(MarketGroup.markets).selectinload(Market.outcomes)` (the exact chain `_load_group_with_children` uses, `event_service.py:141`). Standalone markets need `selectinload(Market.outcomes)`.
**Warning signs:** a `MissingGreenlet`/`lazy load` error in tests the moment you touch `.markets`/`.outcomes`.

### Pitfall 3: `MissingGreenlet` from an expired `admin` after the service commits
**What goes wrong:** reading `admin.id` AFTER `EventService` has run (its `begin()/commit()` expired the dependency-loaded `admin`) raises `MissingGreenlet`.
**Why it happens:** the settlement services churn the session; `expire_on_commit=False` is set on the maker (`db/session.py:47`) but the request session is a *different* session and the admin row gets expired on rollback/commit boundaries.
**How to avoid:** capture `admin_id = admin.id` as a plain value BEFORE `await session.rollback()` (mirror `settlement/router.py:71-72`). Pass the UUID, never the ORM object, into the service.
**Warning signs:** `MissingGreenlet` only on the execute branch, never the preview branch.

### Pitfall 4: Chaining the settle loop on the request session (23505 dangling-tx)
**What goes wrong:** if the endpoint loops children itself on one session, the idempotent-replay path raises Postgres `23505` whose handler leaves an open implicit tx → the next settle raises `InvalidRequestError: A transaction is already begun`.
**Why it happens:** not delegating to `EventService` (which opens a fresh session per child).
**How to avoid:** the endpoint calls `EventService.resolve_event/void_event/reverse_event` and nothing else for the mutation. The service owns the per-child fresh sessions (`event_service.py:464-544`). [[xprediction-financial-services-idempotent-tx-chaining]]
**Warning signs:** flaky 500s on a second (idempotent) resolve/reverse of the same event.

### Pitfall 5: `from __future__ import annotations` breaking `Annotated[..., Depends()]`
**What goes wrong:** under Python 3.13's stricter deferred annotations, FastAPI can't resolve `Annotated[User, Depends(current_active_admin)]` if the module has `from __future__ import annotations` → the dependency isn't injected / route 500s at startup.
**Why it happens:** the future-import makes annotations strings FastAPI evaluates differently.
**How to avoid:** **omit** `from __future__ import annotations` in the new routers (settlement & wallet-admin routers do — `settlement/router.py:16-18` documents it). Use runtime imports for `User`/`AsyncSession`. (The catalog *service* and *schemas* modules CAN keep the future-import; only the **router** must omit it.)
**Warning signs:** a `Depends` not firing, or `pydantic`/`fastapi` complaining about an unresolved forward ref at app import.

### Pitfall 6: Event volume sort when `market_groups` has no volume column
**What goes wrong:** sorting events by `volume` fails or returns 0 because there's no `MarketGroup.volume`.
**Why it happens:** `market_groups` deliberately stores no money column (EVT-06, `models.py:200-275`).
**How to avoid:** compute event volume = `sum(child.volume for child in children)` in Python during the merge (children already eager-loaded). Standalone market volume = `Market.volume`. Both `Decimal`, sort descending.
**Warning signs:** events always sorting last under `?sort=volume`.

## Code Examples

### Discriminated catalog item schema (discretion — recommended shape)
```python
# Source: NEW app/catalog/schemas.py — consistent with OutcomeRead/MarketListItem
#         (markets/schemas.py:102-191); money/odds as JSON strings.
from __future__ import annotations
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, field_serializer

class CatalogOutcome(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    label: str                       # = child.group_item_title for events; outcome.label for markets
    yes_outcome_id: UUID | None = None
    yes_price: Decimal               # child's YES current_odds
    @field_serializer("yes_price", when_used="json")
    def _ser(self, v: Decimal) -> str: return str(v)

class CatalogItem(BaseModel):
    type: Literal["market", "event"]
    id: UUID                         # market.id OR market_group.id
    slug: str
    title: str                       # market.question OR group.title
    category: str | None
    source: str                      # HOUSE | POLYMARKET
    status: str                      # public status: open | closing_soon | resolved
    deadline: datetime | None        # market.deadline; events → min open-child deadline (or None)
    volume: Decimal                  # market.volume OR sum(child.volume)
    created_at: datetime
    outcomes: list[CatalogOutcome]   # market: [YES,NO]; event: top child rows (Phase 17 truncates to 2-4)
    @field_serializer("volume", when_used="json")
    def _ser_vol(self, v: Decimal) -> str: return str(v)
```

### Event request/response schemas (EVA-01/02 + two-step confirm)
```python
# Source: NEW — mirrors ResolveMarketRequest (settlement/schemas.py:22-28) + MarketCreate (:67-81)
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field

class OutcomeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=100)
    initial_odds: Decimal = Field(gt=0, lt=1)

class CreateEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=500)
    category: str | None = Field(default=None, max_length=100)
    deadline: datetime
    resolution_criteria: str | None = Field(default=None, max_length=2000)
    slug: str | None = Field(default=None, max_length=100)             # optional override
    outcomes: list[OutcomeInput] = Field(min_length=2)                 # ≥2 (EVT-07) → 422 otherwise

class ResolveEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    winning_outcome_id: UUID
    justification: str = Field(min_length=1)
    confirm: bool = False                                              # stateless two-step (default = preview)

class VoidEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    justification: str = Field(min_length=1)
    confirm: bool = False

class ReverseEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    justification: str = Field(min_length=1)
    confirm: bool = False
```

### Router registration (`main.py`, deferred-import block)
```python
# Source: main.py:180-203 — add to the existing deferred-import + include_router block
from app.catalog.router import public_catalog_router            # noqa: E402
from app.settlement.event_router import event_admin_router       # noqa: E402
...
app.include_router(public_catalog_router)
app.include_router(event_admin_router)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Top-25-global `/markets` poll | Curated per-category Gamma `/events` sync | Phase 14 | `markets` now carry `category` (CAT-04) — catalog category filter actually works |
| Multi-outcome deferred (v1.0 MKT-08) | Event-of-binaries (`market_groups` + `group_id`) | Phase 13 | The whole `/catalog` + `/events` surface is now possible |
| Event status stored | Derived at read time (`derive_event_status`) | Phase 15 | Catalog must derive status in Python, not read a column (Pitfall 6 / §status mapping) |

**Deprecated/outdated:**
- **`markets.bet_count`**: dead column, never incremented — do not use it for the edit-lock; use `EXISTS(bets)`.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Comment "FastAPI 3.13 gotcha" in `settlement/router.py:16` refers to **Python** 3.13's annotation evaluation (FastAPI is pinned 0.115.x), so omitting `from __future__ import annotations` in routers is the fix | Pitfall 5 | Low — the empirical rule (settlement/wallet routers omit it and work) holds regardless of the exact cause; follow the rule |
| A2 | `gin_trgm_ops` GIN index accelerates infix `ILIKE '%term%'` for 3+ char terms; <3 chars may seq-scan | Pattern 2 | Low — on a curated/bounded (≤100) catalog a seq-scan is acceptable; only a perf nuance |
| A3 | An event's "deadline" for the `closing_soon`/`closing_soonest` sort = min deadline among its unresolved children | Pattern 1 | Low — discretion item; any consistent definition meets BRW-03/04. Confirm with planner if a different definition is preferred |
| A4 | Removing a pre-bet outcome can hard-delete the child + its 2 outcomes (no bets ⇒ no financial rows) | Pattern 6 | Low — safe because the edit-lock guarantees zero bets; alternatively orphan via `group_id=NULL`. Planner picks |

**All other claims are VERIFIED against the phase-branch source (file:line cited) or CITED from REQUIREMENTS.md / CONTEXT.md.**

## Open Questions

1. **Event "deadline" semantics for sort/closing_soon** (A3)
   - What we know: standalone markets have a single `deadline`; events have N child deadlines (the create endpoint applies one shared deadline to all children, so in practice they're equal at creation).
   - What's unclear: whether to expose a single event deadline (= the shared one) or min-of-open-children (matters only if a future edit diverges child deadlines).
   - Recommendation: expose the shared/min-open-child deadline; since `POST /admin/events` applies one shared deadline, they coincide. Document the choice in the schema.

2. **`void`/`partially_resolved` → public filter mapping** (CONTEXT discretion)
   - What we know: derived event status ∈ `{open, partially_resolved, resolved, void}`; public filter ∈ `{open, closing_soon, resolved}`.
   - Recommendation (most "looks-real"): `partially_resolved` → shown as **open** (it's still partially bettable / live); `void` → grouped with **resolved** (it's done — winners/losers settled, just no YES winner). This keeps the public catalog from ever showing a confusing "void" chip while still surfacing the card as concluded. Confirm with planner — it's a discretion call.

3. **Where the event request/response schemas live**
   - Options: `app/catalog/schemas.py` (with the read schemas) vs `app/settlement/schemas.py` (next to `DecimalStr` + the existing resolve/reverse schemas).
   - Recommendation: put **admin event** request/response schemas in `app/settlement/schemas.py` (co-located with `ResolveMarketRequest` and `DecimalStr`), and **public catalog** schemas in `app/catalog/schemas.py`. Minor; planner decides.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | backend | ✓ | 3.12 (pyproject `requires-python`) | — |
| uv | dependency mgmt / test runner | ✓ (project standard) | — | — |
| Docker | testcontainers Postgres in tests | ✓ (project standard) | — | tests skip Docker-less (importorskip in `conftest.py:124`) |
| Postgres 16 + pg_trgm | catalog search + all queries | ✓ (testcontainer `postgres:16-alpine`; extension enabled migration 0011:75) | 16 | — |
| All Python deps (fastapi/sqlalchemy/pydantic/asyncpg/slugify/fastapi-users/httpx) | every module | ✓ (pinned in `pyproject.toml`) | see Standard Stack | — |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** none (Docker-less runs skip the integration suite via `pytest.importorskip`).

> Note: bare `python` outside the uv venv has no deps installed (verified) — always run tests via `cd backend && uv run pytest`. This is expected, not a blocker.

## Validation Architecture

> `workflow.nyquist_validation: true` in `.planning/config.json` — this section is REQUIRED.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (markers `[integration, asyncio(loop_scope="session")]`) |
| Config file | `backend/pyproject.toml` (`[tool.pytest.ini_options]`) + `backend/tests/conftest.py` (env seeding + `engine`/`async_session` fixtures) |
| Quick run command | `cd backend && uv run pytest tests/catalog -x` (per-module — Windows-worktree-safe) |
| Full suite command | `cd backend && uv run pytest tests/ -x` (Linux CI only; flakes on Windows worktree) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| BRW-01 | `q` ILIKE matches local title/question; never proxied to Gamma | integration | `uv run pytest tests/catalog/test_catalog_router.py::test_search_local_only -x` | ❌ Wave 0 |
| BRW-02 | `/categories` non-empty union, no empty category (CAT-06); `/events/{slug}` per-outcome rows | integration | `uv run pytest tests/catalog/test_categories.py tests/catalog/test_event_detail.py -x` | ❌ Wave 0 |
| BRW-03 | status filter {open, closing_soon, resolved}; event derived status mapped | integration | `uv run pytest tests/catalog/test_catalog_router.py::test_status_filter -x` | ❌ Wave 0 |
| BRW-04 | sort {volume, closing_soonest, newest}; event volume = SUM(children) | integration | `uv run pytest tests/catalog/test_catalog_router.py::test_sort -x` | ❌ Wave 0 |
| BRW-05 | every filter combo → 200 + explicit empty list; LIMIT 100 bound; no pagination | integration | `uv run pytest tests/catalog/test_catalog_router.py::test_empty_combos -x` | ❌ Wave 0 |
| EVA-01 | `POST /admin/events` creates group + N binary children; YES seeded; ≥2 enforced; binary trigger respected | integration | `uv run pytest tests/settlement/test_event_router.py::test_create_event -x` | ❌ Wave 0 |
| EVA-02 | `PATCH` edits pre-bet; 423 after first bet (EXISTS(bets), not bet_count) | integration | `uv run pytest tests/settlement/test_event_router.py::test_edit_lock_after_bet -x` | ❌ Wave 0 |
| (EVA-03/04/05) | resolve/void/reverse: `confirm:false`→preview (non-mutating), `confirm:true`→execute | integration | `uv run pytest tests/settlement/test_event_router.py::test_two_step_confirm -x` | ❌ Wave 0 |
| (mapping) | ValueError→HTTP: mirrored 409, blank justification 422, bad winning-outcome 422, missing 404 | integration | `uv run pytest tests/settlement/test_event_router.py::test_value_error_mapping -x` | ❌ Wave 0 |
| back-compat | legacy `GET /api/v1/markets` still returns flat `list[MarketListItem]` | integration | `uv run pytest tests/markets/test_public_router.py -x` | ✅ exists (`test_public_router.py:86`) |
| auth | admin endpoints 401 without Bearer; public reads no-auth | integration | `uv run pytest tests/settlement/test_event_router.py::test_auth_gate -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `cd backend && uv run pytest tests/catalog tests/settlement/test_event_router.py -x` (the new module + the event router — fast, per-module, Windows-safe).
- **Per wave merge:** `cd backend && uv run pytest tests/catalog tests/settlement tests/markets -x` (catalog + settlement + markets back-compat).
- **Phase gate:** full suite green on **Linux CI** (`pytest tests/ -x` + ruff + mypy) before `/gsd-verify-work`. Do NOT gate on the Windows-worktree full run (it flakes — [[xprediction-backend-fullsuite-testcontainers-flake]]).

### Wave 0 Gaps
- [ ] `tests/catalog/__init__.py` + `tests/catalog/conftest.py` — catalog test package (httpx `AsyncClient` + `ASGITransport`, reuse the `engine` testcontainer fixture; seed admin + a mix of standalone markets, ≥2-child events in open/partial/resolved/void states).
- [ ] `tests/catalog/test_catalog_router.py` — covers BRW-01/03/04/05 (search-local-only, status filter, sort, every-combo-empty-safe, LIMIT 100).
- [ ] `tests/catalog/test_categories.py` — covers BRW-02 categories (union, non-empty, CAT-06).
- [ ] `tests/catalog/test_event_detail.py` — covers BRW-02 event detail (≥2-child only, per-outcome YES price, derived status, 404 on 1-child/missing).
- [ ] `tests/settlement/test_event_router.py` — covers EVA-01 (create), EVA-02 (edit-lock 423), two-step confirm (preview vs execute), ValueError→HTTP mapping, auth gate. Mirror `tests/settlement/test_settlement_router.py` fixtures (`_Admin` override, `_bets_table`, `_seed_wallet`).
- [ ] (No new conftest framework needed — `backend/tests/conftest.py` `engine`/`async_session` + the per-module patterns already cover the infra.)

## Security Domain

> `security_enforcement` not set to `false` in config — included. Phase 16 is admin-gated writes + public reads over money-adjacent data.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (admin endpoints) | `current_active_admin` Bearer/superuser gate (`auth/admin_router.py`); reuse, don't reinvent. Public reads are intentionally unauthenticated. |
| V3 Session Management | no | Stateless JWT (no server session for the two-step confirm — that's the whole point of `confirm:bool`). |
| V4 Access Control | yes | Admin-only on `POST/PATCH /admin/events` + resolve/void/reverse (`Depends(current_active_admin)`). Public catalog/event reads expose NO admin fields, NO per-user payout, NO resolver identity (mirror `MarketRead`'s public-safe projection, `markets/schemas.py:135-138`). |
| V5 Input Validation | yes | `extra="forbid"` + `Field(min_length=…/gt=…/lt=…)` on every request body; `Query` validators for `q`/`category`/`status`/`sort` (use `Literal[...]` for `status`/`sort` so FastAPI 422s bad values BEFORE the service). `q` is a **bound param** in `.ilike(f"%{q}%")` — never interpolated into raw SQL. |
| V6 Cryptography | no | No crypto in this phase (no new secrets; JWT handled by fastapi-users). |

### Known Threat Patterns for FastAPI + SQLAlchemy 2.0 + Postgres

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via `q` search term | Tampering | SQLAlchemy bound param `.ilike(f"%{q}%")` (the `%…%` is data); NEVER `text(f"… ILIKE '%{q}%'")` |
| Injection via `status`/`sort` query values | Tampering | `Literal["open","closing_soon","resolved"]` / `Literal["volume","closing_soonest","newest"]` → 422 on anything else |
| Admin endpoint reachable without auth | Elevation of Privilege | `Depends(current_active_admin)` on every write; negative test asserts 401 without Bearer |
| Mirrored (Polymarket) event mutated by admin | Tampering | `EventService` raises ValueError → endpoint maps to 409 (admin read-only except force-settle, EVA-06) |
| Leaking resolver identity / per-user payout in public reads | Information Disclosure | Public catalog/event schemas expose only outcome label + YES price + derived status (no `resolution_justification` author, no payout, no `actor_user_id`) |
| Resource exhaustion via unbounded catalog | DoS | `LIMIT 100` hard bound; no pagination; each sub-query individually capped |
| Editing an event with live bets (financial integrity) | Tampering | `EXISTS(bets)` edit-lock → 423; the lock spans ALL children |

## Sources

### Primary (HIGH confidence) — phase-branch source, file:line cited inline throughout
- `backend/app/settlement/event_service.py` — `EventService.resolve_event/void_event/reverse_event` (:210/:320/:382), `derive_event_status` (:98), `_load_group_with_children` (:129), `_yes_outcome_id` (:146), the 23505 landmine doctrine (:23-31), `_derive_status` ChildStatus construction (:598-619).
- `backend/app/markets/models.py` — `Market`/`MarketGroup`/`Outcome` columns, `lazy="raise"` relationships (:184/:272), GIN/category/status indexes (:52-59/:218-232), `generate_slug` (:33), no volume/status column on `market_groups`.
- `backend/app/markets/service.py` — `create_market` YES/NO body (:38-111), `list_home_markets` (:244), `list_markets` query-building (:274), case-insensitive YES (:182/:374-378); confirmed NO `group_id` support.
- `backend/app/markets/router.py` — legacy `GET /api/v1/markets` flat list (:149-155), admin paginated precedent (:52-77).
- `backend/app/markets/schemas.py` — `OutcomeRead`/`MarketListItem`/`MarketRead`, `field_serializer` money-as-string, `from_attributes`/`extra="forbid"` conventions (:102-191).
- `backend/app/settlement/router.py` — resolve/reverse endpoint pattern, session choreography (:71-73), `from __future__` omission rationale (:16-18), ValueError-not-raised contract.
- `backend/app/settlement/schemas.py` — `DecimalStr` (:16-19), `ResolveMarketRequest` `extra="forbid"` + `Field(min_length=1)` (:22-28).
- `backend/app/integrations/polymarket/adapter.py` — canonical group-create + child-stamp precedent (`_upsert_market_group` :325-386, child stamping :440-448).
- `backend/alembic/versions/0011_phase13_market_groups.py` — pg_trgm + all six catalog indexes (:75-183) — confirms NO new migration needed.
- `backend/alembic/versions/0003_phase4_markets.py` — `trg_binary_outcomes_only` trigger (:170-192).
- `backend/app/bets/models.py` — `bets.market_id` indexed (:50/:76) for the edit-lock EXISTS.
- `backend/app/db/session.py` (:43-60) — `_get_session_maker`, `expire_on_commit=False`, `get_async_session`; `backend/app/db/types.py` (:20-28) — `Money`/`Odds` aliases.
- `backend/tests/settlement/test_settlement_router.py` + `backend/tests/markets/test_public_router.py` + `backend/tests/conftest.py` — httpx `ASGITransport` + testcontainer `engine` fixture + `_Admin` override patterns.
- `backend/pyproject.toml` — pinned versions (FastAPI 0.115.x, SQLAlchemy 2.0.43+, Pydantic 2.10+, asyncpg, python-slugify 8, fastapi-users 15, httpx 0.28).

### Secondary (MEDIUM confidence)
- `.planning/phases/16-catalog-event-api-house-event-crud/16-CONTEXT.md` — locked decisions + the backend scout (the codebase mapping this research verified against source).
- `.planning/REQUIREMENTS.md` — BRW/EVA/CAT/EVT requirement text + anti-features (no Gamma `/public-search`, no pagination).
- `.claude/skills/spike-findings-xpredict/SKILL.md` — money=Decimal, FOR-UPDATE/ledger invariants (settlement is reused unchanged, so these are inherited).

### Tertiary (LOW confidence)
- None — every claim is grounded in branch source or project planning docs. No external WebSearch was needed (zero new deps, the framework versions are pinned, and the patterns are all in-repo).

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every library pinned in `pyproject.toml`, all already in use; zero new deps.
- Architecture (catalog query shape, session choreography, two-step confirm): HIGH — Approach B rationale is grounded in the concrete fact that event status + volume are not columns; the settlement choreography is copied from a working endpoint; the two-step confirm is a clean stateless design with explicit preview/execute branches.
- Pitfalls: HIGH — each pitfall is observed in the existing code/comments (23505 landmine, `lazy="raise"`, `from __future__` omission, dead `bet_count`) with file:line evidence.
- Discretion items (status mapping, event deadline semantics, schema location): MEDIUM — flagged in Assumptions Log + Open Questions for the planner to lock.

**Research date:** 2026-06-05
**Valid until:** ~2026-07-05 (stable — no fast-moving external deps; only invalidated if Phases 13–15 code is refactored or the branch diverges).
