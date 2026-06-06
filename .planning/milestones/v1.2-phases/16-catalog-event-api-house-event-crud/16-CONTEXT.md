# Phase 16: Catalog & Event API + House Event CRUD - Context

**Gathered:** 2026-06-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 16 delivers the **HTTP contract** over the catalog + event-settlement engine built in Phases 13–15: read endpoints for browse/search/category/event detail, plus admin house-event CRUD and the admin resolve/void/reverse endpoints that **expose** the Phase-15 `EventService`. It is **backend-only and testable without any UI** (success criterion: "testable independently of any UI"), every filter combination returning an explicit, bounded result.

Covers **BRW-01..05, EVA-01, EVA-02** (and the HTTP surface for the already-built EVA-03..06 service). It does **NOT** build any frontend (browse UI, event detail, admin ops UI → Phase 17), the seed/demo multi-outcome harness (Phase 18), pagination/infinite scroll (out of scope — catalog is curated/bounded), per-category counts on chips (P2-03, Phase 17), or any new settlement primitive. It **reuses UNCHANGED**: `EventService.resolve_event/void_event/reverse_event` + `derive_event_status` (Phase 15), `SettlementService`, `current_active_admin` auth, the `pg_trgm` GIN indexes + category/status indexes (Phase 13 migration 0011), the `MarketGroup`/`Market` model, and the per-feature router + `schemas.py` conventions. **Zero new dependencies; no new DB migration expected** (search/category/status indexes already exist; event status is derived). Search is **local pg_trgm only — never proxied to Gamma `/public-search`**.

</domain>

<decisions>
## Implementation Decisions

### Catalog read contract (`GET /catalog`) — BRW-01..05
- **Unified item list**: `/catalog` returns one bounded list of catalog **items**, each discriminated `type: "market"` (standalone binary) or `type: "event"` (multi-outcome `MarketGroup`) — mirrors Polymarket's mixed grid. (Single-outcome groups, EVT-07, surface as a plain `market` item, never as an `event`.)
- **URL prefix `/api/v1/catalog`** — consistent with the public `/api/v1/markets` surface (NOT the bare `/admin/markets` settlement anomaly).
- **Bound = `LIMIT 100` total** after filters + sort. Curated catalog, **no pagination / no infinite scroll** (success criterion 1, BRW-05). Every filter combination yields an explicit empty/zero result, never an error.
- **Indexed text search**: `pg_trgm` GIN + ILIKE on **local rows only** (`markets.question` + `market_groups.title`) — never proxied to Gamma `/public-search`.
- **Filters**: `category` (exact), `status`, and `q` (search). **Status filter vocabulary = `{open, closing_soon, resolved}`** unified across both row types: `closing_soon` = `open` AND `deadline <= now + 48h`; map the stored market enum ({OPEN→open / closing_soon, RESOLVED→resolved}) and the derived event status ({open / partially_resolved / resolved / void}) into this set. (Exact mapping of `void`/`partially_resolved` into the public filter is Claude's discretion — see below.)
- **Sort** = `{volume, closing_soonest, newest}` (default: volume) — `volume` desc, `closing_soonest` = `deadline` asc among open, `newest` = `created_at` desc.

### Event detail & categories (`GET /events/{slug}`, `GET /categories`) — BRW-02
- **`GET /events/{slug}`** looks up by **`market_groups.slug`** (unique). Returns the event with its **per-outcome child rows** (each child's `group_item_title` label + its YES price/`current_odds`) and the **derived** status (`derive_event_status`). Children eager-loaded via `selectinload(MarketGroup.markets).selectinload(Market.outcomes)` (relationship is `lazy="raise"`).
- **Only `≥2`-outcome groups** are served at `/events/{slug}`; a 1-child item (EVT-07) stays on `/markets/{slug}`. (`/events/{slug}` on a single-outcome or non-existent slug → 404.)
- **`GET /categories`** returns the **union** of non-empty categories across standalone `markets` **and** event `market_groups`, only those with **≥1 visible item** (CAT-06 — never surface an empty category). `SELECT DISTINCT category WHERE category IS NOT NULL AND category <> ''` over both tables.
- **Payload = category names only** in Phase 16. Per-category counts are **P2-03 (Phase 17)** — out of scope here.

### House event create & edit (`POST/PATCH /admin/events`) — EVA-01 / EVA-02
- **`POST /admin/events`** body: `{title, category, deadline, outcomes: [{label, initial_odds}, ...]}` with **minimum 2 outcomes** (grouping applies only to ≥2 per EVT-07). The server creates one `MarketGroup` (source=HOUSE) + **N child binary markets**, each a YES/NO market wired to the group via `group_id`, with `group_item_title = label` and the YES `Outcome` seeded at `initial_odds`. Reuse the existing house-market create path (which always makes exactly YES+NO — never violate the binary-only CHECK/trigger). The shared `deadline` is applied to each child.
- **Slug**: auto-slugify from `title` with a uniqueness suffix on collision; allow an optional admin-supplied `slug` override.
- **Edit-lock signal (mirrors ADM-07)**: an event is editable **only while NO child market has any bet**. The lock predicate is `EXISTS(SELECT 1 FROM bets WHERE market_id IN (children))` — **NOT** the dead `markets.bet_count` column (it is never incremented in app code). The check spans all child markets of the group.
- **`PATCH /admin/events/{group_id}` scope**: pre-bet → may edit title, category, deadline, per-outcome label + initial odds, and add/remove outcomes. After the first bet on any child → **HTTP 423** (locked), mirroring the existing market `CRITERIA_LOCKED` 423.

### Admin resolve / void / reverse endpoints + two-step confirm — exposes EVA-03..05
- **Paths**: `POST /admin/events/{group_id}/resolve`, `/void`, `/reverse` — mirror `POST /admin/markets/{id}/resolve|reverse`. Path param = group **UUID**.
- **Two-step confirm = stateless** (no backend precedent exists; designed here): the request body carries `confirm: bool`. With `confirm: true` the action executes; **without it (or `confirm: false`) the endpoint returns a 200 _preview_** of the impact (child count, winner/loser breakdown, derived end status) **without mutating**. `justification` is **mandatory, non-empty** (`Field(min_length=1)`, `extra="forbid"`).
- **`resolve` winning-outcome input** = `winning_outcome_id` (the UUID of the winning child's **YES** `Outcome`) — matches `EventService.resolve_event`'s signature. The endpoint validates the outcome belongs to a child of this group before calling the service.
- **`ValueError` → HTTP mapping** (the service raises `ValueError`, never `HTTPException`): mirrored (`source=POLYMARKET`) group → **409 Conflict**; blank justification → **422**; invalid winning-outcome → **422**; group not found → **404**. Mirrored events stay admin read-only except the existing force-settle (EVA-06).

### Claude's Discretion
- Exact response-schema field names + `type` discriminator key for the unified catalog item (consistent with `MarketListItem`/`OutcomeRead` conventions).
- How `void` / `partially_resolved` event states map into the public `{open, closing_soon, resolved}` catalog filter (e.g. `partially_resolved` shown as `open` or hidden; `void` grouped with `resolved` or hidden). Pick the most "looks-real" mapping.
- The `closing_soon` 48h threshold value (48h recommended; pick a sensible constant).
- Whether catalog query is one UNION query over markets+groups or two queries merged in Python under the LIMIT — discretion, provided the result is bounded to 100 and every filter combo returns an explicit empty set.
- Preview-response shape for the two-step confirm (impact summary fields).
- Whether add/remove-outcome lives in `PATCH` or a sub-route — discretion, provided pre-bet only + 423 after first bet.
- Slugify helper choice (reuse any existing house-market slug logic if present).
- Test layout: endpoint integration tests (httpx `AsyncClient` + `ASGITransport`, testcontainers) per endpoint family + the auth-gate negative tests.

</decisions>

<code_context>
## Existing Code Insights
*(from a backend scout of `backend/app/` on the phase branch)*

### Reusable Assets
- **Routers** live per-feature: `app/<feature>/router.py`, registered via `include_router` in `app/main.py:189-203` with **deferred imports** (`# noqa: E402`, `main.py:180-187`) to avoid circular imports. New catalog/event routers register the same way.
- **Legacy `GET /markets` (MUST preserve, back-compat)**: `public_market_router` prefix `/api/v1/markets`; `GET ""` → `list[MarketListItem]` (flat list, NO pagination), house OPEN `created_at desc` limit 50 + Polymarket OPEN `volume_24hr desc` limit 25 (`MarketService.list_home_markets`, `markets/service.py:244`). A test asserts the body is a list. Do not change its shape.
- **Closest precedent for `/catalog`**: the admin paginated `GET /api/v1/admin/markets` → `PaginatedResponse[MarketListItem]` with `source/status/category` query filters (`markets/router.py:52-77`, `MarketService.list_markets` `service.py:274`). Reuse its query-building approach (but bound to LIMIT 100, no pagination).
- **`MarketListItem`** (`markets/schemas.py:156-191`): `id, question, slug, category, source, status, deadline, bet_count, created_at, volume(str), volume_24hr(str), source_url, outcomes: list[OutcomeRead]`; `OutcomeRead` (`:102-113`): `id, label, initial_odds(str), current_odds(str)`. `ConfigDict(from_attributes=True)`.
- **Admin auth**: `from app.auth.deps import current_active_admin` (Bearer-only, superuser; `auth/admin_router.py:89-92`). Usage `admin: Annotated[User, Depends(current_active_admin)]`.
- **Market resolve/reverse pattern to mirror** (`app/settlement/router.py`): `POST /admin/markets/{id}/resolve` body `ResolveMarketRequest{winning_outcome_id, justification: min_length=1}`; `/reverse` body `{justification}`. Prefix is bare `/admin/markets` (no `/api/v1`) — settlement anomaly; **`/admin/events` should be deliberate** (recommend `/admin/events` bare to mirror settlement, or `/api/v1/admin/events` — pick one consistently; spec text says `/admin/events`).
- **Phase-15 `EventService`** (`app/settlement/event_service.py`): `resolve_event(*, group_id, winning_outcome_id, justification, actor_user_id=None) -> EventSettleResult` (`:210`); `void_event(*, group_id, justification, actor_user_id=None)` (`:320`); `reverse_event(*, group_id, justification, actor_user_id=None)` (`:382`); `derive_event_status(children) -> str ∈ {open,partially_resolved,resolved,void}` (`:98`). `EventSettleResult{group_id, child_count, children_settled, children_failed, status}` (`:82`). Raises **`ValueError`** for mirrored / blank-justification / bad-winning-outcome — endpoint maps to 4xx.
- **`MarketGroup`** (`markets/models.py:200-275`): `id, title, source(HOUSE/POLYMARKET), source_event_id, category(nullable), slug(UNIQUE)`. NO status/winning/money column. `group_item_title` is on **`Market`** (`:182`). Children link via `Market.group_id` (ON DELETE SET NULL). `MarketGroup.markets` is `lazy="raise"` → must `selectinload`.
- **Event outcomes/prices assembly**: each child is a binary; the event's outcome N price = that child's **YES** `Outcome.current_odds`. YES matched **case-insensitively** (`func.upper(label)=="YES"`; house="YES", Polymarket="Yes") — see `_yes_outcome_id` (`event_service.py:146-160`).
- **Indexes (Phase 13, `alembic/versions/0011_phase13_market_groups.py`)**: GIN trgm `ix_markets_question_trgm` (`markets.question`) + `ix_market_groups_title_trgm` (`market_groups.title`); `ix_markets_category` + `ix_market_groups_category`; composite `ix_markets_status_volume_24hr` (status filter + volume sort). All also declared in `models.py __table_args__` (byte-identical — drift convention). **No new index expected; if one is added it must go in BOTH places.**
- **Schema conventions**: `app/<feature>/schemas.py`; read models `ConfigDict(from_attributes=True)`; request bodies `ConfigDict(extra="forbid")`; **money/odds = JSON strings** via `@field_serializer(..., when_used="json")` / `DecimalStr` (`settlement/schemas.py:16-19`) — never floats. `PaginatedResponse[T]` + `paginated_response()` helper exists (use only if a paginated surface is wanted; `/catalog` is bounded, not paginated).
- **Audit**: `AuditService.record(session, *, actor, event_type, payload)` (already invoked inside `EventService` for the event-level rows).

### Established Patterns
- **Endpoint→service session choreography** (`settlement/router.py:71-73`): capture `admin_id = admin.id` as a plain value, then `await session.rollback()` to clear the autobegun read-tx **before** the service opens its own `begin()`. `NoResultFound`/`scalar_one` → 404.
- **Settlement services manage their own sessions internally** — event endpoints must call `EventService` methods (which use a fresh session per child), **not** reuse the request's `get_async_session` for the settle loop (the 23505 dangling-tx landmine; see [[xprediction-financial-services-idempotent-tx-chaining]]).
- **FastAPI 3.13 gotcha**: any router using `Annotated[..., Depends()]` must **omit** `from __future__ import annotations` (settlement & wallet admin routers do — keeps types runtime-evaluable).
- **`bet_count` is dead** (never incremented). Real "has bets" = `EXISTS(SELECT 1 FROM bets WHERE market_id=...)` or the per-market liability account.
- **Binary-only CHECK/trigger** `trg_binary_outcomes_only` (migration 0003) blocks a 3rd outcome per market — a house event = N binary YES/NO children; always create exactly YES+NO per child.
- **Tests**: `httpx.AsyncClient` + `httpx.ASGITransport(app=app, raise_app_exceptions=False)` against `from app.main import app`; markers `[integration, asyncio(loop_scope="session")]`; testcontainers (real Postgres). Auth: `app.dependency_overrides[current_active_admin] = lambda: _Admin(uid)` (override) or omit to hit the real 401. Examples: `tests/markets/test_public_router.py`, `tests/settlement/test_settlement_router.py`.

### Integration Points
- `app/main.py` `include_router` block — register the new catalog + admin-events routers (deferred import).
- `EventService` (Phase 15) — looped per child internally; endpoints call resolve/void/reverse + `derive_event_status`.
- `MarketService` house-create path (`markets/service.py:71-84`) — reuse to make each child YES+NO under the group.
- `markets`/`market_groups` tables + existing GIN/category/status indexes — the catalog query inputs.
- `bets` table — the edit-lock `EXISTS` signal.

</code_context>

<specifics>
## Specific Ideas

- **Back-compat is a success criterion**: `GET /markets` (legacy) must keep working unchanged — add new surfaces, don't refactor the old one.
- **Never proxy player search to Gamma `/public-search`** (explicit anti-feature) — local `pg_trgm` only.
- **No heavy pagination / infinite scroll** (anti-feature) — `/catalog` is bounded `LIMIT 100`.
- **Money/odds on the wire = strings**, never floats (`field_serializer`/`DecimalStr`).
- **Two-step confirm has no backend precedent** — the stateless `confirm` flag + non-mutating preview is the agreed design; keep it stateless (no server-side token store).
- **Windows worktree is unreliable** for the full backend suite (testcontainers contention flake + ruff `check`/`format` flip-flop) — verify **per-module** locally, trust **Linux CI** for the full suite + ruff + mypy. See [[xprediction-backend-fullsuite-testcontainers-flake]].
- **No new dependencies. No new migration expected** — the indexes already exist (Phase 13); event status is derived (Phase 15). If a migration is unavoidable, declare any index in BOTH the Alembic file AND `models.py __table_args__`.

</specifics>

<deferred>
## Deferred Ideas

- Browse UI, event detail page, per-outcome rows, admin event-ops UI, white-label `--brand-*` on catalog surfaces (BRW-06, EVT-02..05) — **Phase 17**.
- Per-category count chips ("Politics 12") + featured "Top events" shelf + live WS odds on rows (P2-01..03) — **Phase 17 stretch**.
- Seed/demo multi-outcome harness across event states (DEMO-01..04) — **Phase 18**.
- True refund-on-cancel (stake refund) — explicitly out of scope (void = all-children-NO).
- Cursor/offset pagination of the catalog — out of scope (curated/bounded).

</deferred>
