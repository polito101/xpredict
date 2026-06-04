# Architecture Research

**Domain:** Multi-outcome prediction-market events (event-of-binaries) + per-category curated catalog — DELTA for XPredict v1.2 "Credible Catalog"
**Researched:** 2026-06-04
**Confidence:** HIGH (grounded in the real backend at `backend/app/**` + live Polymarket Gamma `/events` & `/tags` responses; LOW only where flagged on category-derivation heuristics)

> This is a **subsequent-milestone** integration study, NOT a greenfield design. Every claim below is anchored to a named module/class that already ships in `main`. The binary YES/NO model, `MarketSource` Protocol, `PolymarketAdapter`, `GammaClient`, `SettlementService`, double-entry ledger, and real-time WS are **given** and reused unchanged except where explicitly marked MODIFIED.

---

## The One Insight That Drives Everything

`SettlementService.resolve_market()` (`backend/app/settlement/service.py:83`) already takes a **single** `market_id` + `winning_outcome_id`. It is `(market_id, winning_outcome_id) → one ACID settle`. A multi-outcome "event" is therefore **N independent binary markets settled N times** — the winner market resolves on its `YES` outcome, every loser market resolves on its `NO` outcome. No native categorical engine, no new settlement math, no change to the ledger.

Equally important: **there is no DB CHECK constraint limiting a market to two outcomes.** Binary-ness is a *convention enforced by the write path* — `MarketService.create_market` (`markets/service.py:38`) always inserts exactly a `YES` + `NO` `Outcome`, and `PolymarketAdapter.sync_top25` (`adapter.py:163`) iterates `outcomes_raw[:2]`. The only outcome-level CHECKs are odds-range `[0,1]` (`markets/models.py:174`). So "event-of-binaries" needs **zero constraint changes** — we are grouping existing binary `Market` rows, never widening one.

These two facts collapse the entire milestone risk: the event layer is **additive metadata + an orchestration loop**, sitting on top of the proven binary core.

---

## Standard Architecture

### System Overview (v1.2 delta in ░░░ shading)

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          FRONTEND  (Next.js 15)                            │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐  ┌─────────────┐ │
│  │ Home / Browse│  │ ░Event Detail│  │ ░Category Nav  │  │ Market Detail│ │
│  │ ░search+filter  │ ░(N outcomes)│  │ ░+ search box  │  │  (binary)    │ │
│  └──────┬───────┘  └──────┬───────┘  └───────┬────────┘  └──────┬──────┘ │
├─────────┴─────────────────┴──────────────────┴──────────────────┴────────┤
│                          BACKEND API  (FastAPI)                            │
│  public_market_router          ░catalog_router        settlement_admin    │
│  /api/v1/markets               ░/api/v1/catalog       /admin/markets/...  │
│  /api/v1/markets/{slug}        ░/api/v1/events/{slug} ░+ /events/{id}/     │
│                                ░/api/v1/categories      resolve            │
├──────────────────────────────────┬───────────────────────────────────────┤
│                          SERVICE LAYER                                     │
│  MarketService   ░CatalogService  ░EventService   SettlementService       │
│  (binary CRUD)   ░(search/filter) ░(group + loop) (per-market, REUSED)    │
├──────────────────────────────────┼───────────────────────────────────────┤
│            INTEGRATION            │            CELERY BEAT (redbeat)        │
│  PolymarketAdapter                │  poll_polymarket_top25 ──► ░poll_events │
│  ░+ sync_events()                 │  snapshot_odds  (UNCHANGED, all OPEN)   │
│  GammaClient                      │  detect_polymarket_resolutions          │
│  ░+ fetch_events(tag,page)        │     (UNCHANGED — per child market)      │
├──────────────────────────────────┴───────────────────────────────────────┤
│                          POSTGRES 16                                       │
│  markets ░(+ group_id FK, + new indexes)   outcomes   odds_snapshots      │
│  ░market_groups (NEW: the "event")   ░categories(opt)  bets  ledger        │
└──────────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | New / Modified / Reused |
|-----------|----------------|-------------------------|
| `market_groups` table (the "event") | Group N binary `Market` rows; hold event-level title/slug/category/source/`source_event_id`/winner | **NEW** (`backend/app/markets/models.py`) |
| `Market.group_id` FK (+ `group_item_title`) | Link a binary market to its event; per-outcome display label ("Spain") | **MODIFIED** (`markets/models.py` — nullable column + index) |
| `EventService` | Create/update house events; **resolution loop** delegating to `SettlementService` per child | **NEW** (`markets/event_service.py`) |
| `CatalogService` | Browse query model: text search + category filter + status filter + sort | **NEW** (`markets/catalog_service.py`) — supersedes `MarketService.list_home_markets` |
| `GammaClient.fetch_events()` | Hit `/events` with `tag_id`/`order=volume24hr`/`limit`/`offset` | **MODIFIED** (`integrations/polymarket/client.py`) — add method, keep `fetch_top_markets` |
| `PolymarketAdapter.sync_events()` | Map one Gamma event → 1 `market_group` + N binary markets (upsert) | **MODIFIED** (`integrations/polymarket/adapter.py`) — add method, reuse upsert |
| `GammaEvent` schema | Pydantic parse of event JSON (`markets[]`, `tags[]`, `groupItemTitle`) | **NEW** (`integrations/polymarket/schemas.py`) — sibling of `GammaMarket` |
| `poll_polymarket_events` task | Beat task: per-category top-N sync with volume floor | **NEW** (`integrations/polymarket/tasks.py`) — replaces `poll_polymarket_top25` in beat schedule |
| `SettlementService` | Per-market ACID settle | **REUSED UNCHANGED** (`settlement/service.py`) |
| `detect_polymarket_resolutions` | Per child-market UMA detect → settle | **REUSED UNCHANGED** (`tasks.py:198`) — already iterates POLYMARKET markets |
| `snapshot_odds` | OddsSnapshot for every OPEN market's outcomes | **REUSED UNCHANGED** (`tasks.py:149`) — automatically covers event children |
| Next.js Event Detail / Catalog | N-outcome event page, category nav, search/filter UI | **NEW** pages + **MODIFIED** `market-list`/`market-card` |

---

## Part 1 — Modeling an "Event" as a Grouping over Binary Markets

### Schema Seam: `market_groups` (NEW) + `Market.group_id` (MODIFIED)

The Gamma reality (confirmed live) is a perfect 1:1 with this seam. An event JSON is:

```
event { id, slug, title, description, volume, volume24hr, liquidity,
        endDate, active, closed, negRisk, tags:[{id,label,slug}],
        markets: [ { id, conditionId, question, groupItemTitle:"Spain",
                     outcomes:["Yes","No"], outcomePrices:["0.21","0.79"],
                     clobTokenIds:[…] }, … ] }
```

Each `markets[]` entry is **already a self-contained binary market** with its own `conditionId` and Yes/No outcomes — exactly what `sync_top25` parses today. The event is pure grouping metadata. `groupItemTitle` is the per-outcome catalog label ("Will Spain win?" → chip "Spain").

```python
# backend/app/markets/models.py  — NEW table (sibling of Market)
class MarketGroup(Base):
    __tablename__ = "market_groups"
    __table_args__ = (
        CheckConstraint(f"source IN ({...MarketSourceEnum...})", name="ck_market_groups_source"),
        # NO outcome-count check — children are binary Market rows, each already constrained.
    )
    id:               Mapped[PyUUID]   = mapped_column(UUID, primary_key=True, default=uuid4, ...)
    title:            Mapped[str]      = mapped_column(Text, nullable=False)
    slug:             Mapped[str]      = mapped_column(String(120), unique=True, index=True)
    description:      Mapped[str]      = mapped_column(Text, nullable=False)
    category:         Mapped[str|None] = mapped_column(String(100), index=True)   # mirrors Market.category
    source:           Mapped[str]      = mapped_column(String(20), server_default="HOUSE")
    source_event_id:  Mapped[str|None] = mapped_column(String(200))               # Gamma event.id
    polymarket_slug:  Mapped[str|None] = mapped_column(String(300))               # event.slug for source_url
    status:           Mapped[str]      = mapped_column(String(20), server_default="OPEN")
    volume:           Mapped[Money]    = mapped_column(server_default="0")         # SUM/own of children
    volume_24hr:      Mapped[Money]    = mapped_column(server_default="0")
    deadline:         Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # House resolution projection (mirrors Market STL-06 fields):
    winning_market_id: Mapped[PyUUID|None] = mapped_column(UUID)                   # which child won ("none"=NULL+flag)
    resolution_source: Mapped[str|None]    = mapped_column(String(40))
    resolution_justification: Mapped[str|None] = mapped_column(Text)
    resolved_at:      Mapped[datetime|None]= mapped_column(DateTime(timezone=True))
    tenant_id:        Mapped[PyUUID|None]  = mapped_column(UUID, default=lambda: get_settings().TENANT_ID_DEFAULT)

    markets: Mapped[list["Market"]] = relationship(back_populates="group", lazy="raise")

# backend/app/markets/models.py  — MODIFIED Market (two additive nullable columns)
class Market(Base):
    ...
    group_id:          Mapped[PyUUID|None] = mapped_column(
        UUID, ForeignKey("market_groups.id", ondelete="SET NULL"), nullable=True, index=True)
    group_item_title:  Mapped[str|None]    = mapped_column(String(120), nullable=True)  # Gamma groupItemTitle
    group: Mapped["MarketGroup|None"] = relationship(back_populates="markets")
```

**Why a separate table, not a self-referential `Market.parent_id`?**
- An event is **not a bettable market** — it has no outcomes, no liability account, no odds. Reusing the `Market` table for events would force every binary query (`MarketService`, `BetService`, `snapshot_odds`, settlement) to filter out "container" rows, inviting the exact "a row that is sometimes a market" bug class. A distinct table keeps the binary core's queries unchanged.
- `group_id` nullable means **a standalone binary market (group_id IS NULL) is unaffected** — the top-25 single markets and existing house markets keep working with zero migration of data.

**Migration:** one new Alembic revision off head `0010_phase12_resolution_and_stake_limits` (next id `0011_phase13_market_groups`). Creates `market_groups`, adds `markets.group_id` + `markets.group_item_title`, and the catalog indexes (Part 4). All columns nullable / server-defaulted ⇒ **no backfill, no downtime**.

### Mirrored vs House Events

| Aspect | Mirrored (Polymarket) | House (admin-created) |
|--------|----------------------|----------------------|
| `market_groups.source` | `POLYMARKET` | `HOUSE` |
| `source_event_id` | Gamma `event.id` | `NULL` |
| Children created by | `PolymarketAdapter.sync_events` | `EventService.create_event` (loops `MarketService.create_market`) |
| `group_item_title` | Gamma `market.groupItemTitle` | Admin-supplied per-outcome label |
| Child `condition_id` | Gamma `market.conditionId` | `NULL` (as house markets today) |
| Resolution | Per-child UMA (Part 3) | Admin picks winning child (Part 3) |
| Child outcomes | `YES`/`NO` from Gamma (title-case "Yes"/"No" preserved, as today) | `YES`/`NO` via `create_market` |

### How a Gamma Event Maps to N Child Binary Markets

```
GammaEvent
  ├── group_upsert: market_groups ON CONFLICT (source, source_event_id)   ← mirror of sync_top25's market upsert
  │     index_where=source_event_id IS NOT NULL                            (new partial unique index 0011)
  └── for child in event.markets:                                          ← each child is ALREADY binary
        market_upsert: markets ON CONFLICT (source, source_market_id)      ← REUSE existing partial unique idx (0004)
          set group_id = <group.id>, group_item_title = child.groupItemTitle
        upsert YES/NO outcomes  (child.outcomes_raw[:2], child.outcomePrices_raw)  ← REUSE adapter logic verbatim
```

The child-market upsert is **literally the body of `sync_top25` today**, refactored to `_upsert_one_market(session, parsed_child, group_id)` and called in a loop. The only new write is the parent `market_groups` row and stamping `group_id` on each child. The existing `(source, source_market_id)` partial unique index (migration `0004`, `adapter.py:215`) already guarantees idempotent child upsert across re-syncs.

**Edge — a Gamma event with a single market** (many Polymarket "events" wrap one binary, e.g. "Will X happen by date?"): still create a `market_group` with one child, OR (simpler, MEDIUM-confidence recommendation) skip the group when `len(event.markets) == 1` and store the lone market standalone (`group_id NULL`) exactly as the top-25 path does today. Roadmapper should pick one; defaulting to "always group" keeps the UI uniform but adds container rows for singletons. **Recommendation: group only when `len(markets) >= 2`** — keeps singletons on the proven standalone path and reserves the event UI for true multi-outcome.

---

## Part 2 — Extending Gamma Sync: top-25-global → top-N-per-category

### Confirmed Gamma `/events` Contract (live, 2026-06-04)

| Capability | Confirmation | Source |
|------------|--------------|--------|
| Nested `markets[]` per event | Yes — each child has own `id`, `conditionId`, `outcomes`, `outcomePrices`, `groupItemTitle`, `clobTokenIds` | live `gamma-api.polymarket.com/events` |
| `tags[]` on event | Yes — array of `{id, label, slug, forceShow, …}` (present when filtered by `tag_id`) | live `/events?tag_id=…` |
| Filter by category | `tag_id` (+ `related_tags`, `exclude_tag_id`) | docs `get-events` |
| Sort | `order=volume24hr|volume|liquidity|end_date` + `ascending` | docs `get-events` |
| Pagination | `limit` + `offset` ("all list endpoints return paginated responses") | docs `get-events` |
| Volume floor | client-side filter on `event.volume24hr`/`volume` (no `volume_num_min` confirmed on `/events`; filter in adapter) | live + docs |
| Tags catalog | `/tags` → `{id, label, slug}` | live `/tags` |

> **MEDIUM-confidence caveat — tags are noisy.** Live `/tags` returns hyper-specific labels ("caitlin clark", "Viktoria Plzen", "redbull"), NOT a clean taxonomy. A naive "one category per tag" would explode the nav into hundreds of micro-tags. **Decision required (Part 6 build step):** maintain a small **curated category map** in config — a fixed list of top-level categories (Politics, Sports, Crypto, Pop Culture, Economy, Tech, World) each pinned to a known Gamma `tag_id` (or a slug allow-list). Sync iterates *that* list, not the firehose of tags. This honors PROJECT.md's "categorías derivadas de tags de la Gamma API" while keeping the nav credible and bounded.

### New Sync Shape

```python
# config (NEW): the curated taxonomy — slug/label → Gamma tag_id, top_n, volume_floor
POLYMARKET_CATEGORIES = [
    {"slug": "politics", "label": "Politics", "tag_id": "<id>", "top_n": 20, "vol_floor": "50000"},
    {"slug": "sports",   "label": "Sports",   "tag_id": "<id>", "top_n": 20, "vol_floor": "50000"},
    {"slug": "crypto",   "label": "Crypto",   "tag_id": "<id>", "top_n": 15, "vol_floor": "50000"},
    ...  # ~7 categories
]

# GammaClient (MODIFIED): add fetch_events; keep fetch_top_markets for back-compat/tests
async def fetch_events(self, *, tag_id: str, limit: int, offset: int = 0) -> list[dict]:
    resp = await client.get("/events", params={
        "active": "true", "closed": "false",
        "tag_id": tag_id, "order": "volume24hr", "ascending": "false",
        "limit": str(limit), "offset": str(offset)})
    ...  # same tenacity retry + bounded pool as fetch_top_markets (client.py:47)

# tasks.py (NEW task): poll_polymarket_events — runs per category, applies volume floor
async def _run_poll_events():
    for cat in get_settings().POLYMARKET_CATEGORIES:
        raw_events = await client.fetch_events(tag_id=cat["tag_id"], limit=cat["top_n"])
        floored = [e for e in raw_events if Decimal(str(e.get("volume24hr") or 0)) >= Decimal(cat["vol_floor"])]
        await adapter.sync_events(session, floored, category=cat["slug"])
```

### Dedup, Pagination, Load Growth

- **Dedup across categories** (a market tagged both "Politics" and "World"): the existing `(source, source_market_id)` partial unique index makes the child-market upsert idempotent regardless of how many category passes touch it. For the **group**, the new `(source, source_event_id)` partial unique index does the same. Last-writer-wins on `category` is acceptable; if strict category ownership matters, stamp the *first* category that imports an event and skip on conflict (MEDIUM — roadmapper choice).
- **Pagination:** top-N per category is small (≤20), so a **single `/events` call per category** (no offset paging needed) keeps the request count at ~`len(categories)` per cycle (~7 req), well under Gamma's 300 req/10s budget noted in `client.py:8`. `offset` is wired for completeness but unused at N≤20.
- **Odds-snapshot load growth — the real scaling concern.** `snapshot_odds` (`tasks.py:149`) writes one `OddsSnapshot` per outcome of every OPEN market every 5 min. Today: ~25 markets × 2 = 50 rows / 5 min. After v1.2: ~7 categories × 20 events × (avg ~4 child markets) × 2 outcomes ≈ **1,120 rows / 5 min ≈ 322k rows/day** vs ~14k today (≈23× growth). This is still trivial for Postgres 16 (sub-second insert), but **two consequences must be roadmapped:**
  1. The 30-day price-history downsample query (`MarketService.price_history`, `service.py:393`, `DISTINCT ON (date_trunc('hour'))`) now scans far more rows per market — keep it; add a composite index `(outcome_id, snapshot_at)` on `odds_snapshots` (today only single-column indexes exist, `models.py:230`). **NEW index in 0011.**
  2. Snapshot retention: add a prune task (delete snapshots older than 30 d for markets past the largest window) to cap unbounded growth. **NEW task, LOW urgency** (table stays small for months) — flag for a later phase, not v1.2-blocking.

### Beat-Schedule Change

`poll_polymarket_top25` is **replaced in the redbeat schedule** by `poll_polymarket_events` (PROJECT.md: "reemplaza el top-25 global"). Keep the old task function importable (tests reference it) but drop it from the beat schedule. The Redis SETNX lock pattern (`tasks.py:55`, `LOCK_KEY`, owner-token release) is reused verbatim — only the task body changes. `detect_polymarket_resolutions` and `snapshot_odds` schedules are **unchanged**.

---

## Part 3 — Multi-Outcome Resolution (reuse per-binary `SettlementService`)

### Mirrored Events — Per-Outcome UMA (ZERO new code)

`detect_polymarket_resolutions` (`tasks.py:198`) already selects **every** `source=POLYMARKET` market past deadline, checks its UMA status via `GammaClient.fetch_market_by_id`, and calls `SettlementService.resolve_market` per market with grace-period gating. Because event children are ordinary `source=POLYMARKET` `Market` rows, **they are auto-resolved individually with no change.** Polymarket resolves each child's UMA independently (in a neg-risk event, exactly one child resolves YES, the rest NO), and our loop settles each as it confirms. The event's apparent "winner" emerges from the children's individual settlements.

The only **optional** addition: after a child settles, recompute and stamp `market_groups.status`/`winning_market_id` for display (a child resolving YES ⇒ that's the event winner). This is a **read-model projection**, not part of the money path — can be a post-settle hook or a derived query. **Recommendation: derive at read time** (`EventService.get_event` computes winner from children) to avoid a second write inside the settlement tx.

### House Events — Admin Picks Winning Outcome → Settle Constituents

This is the one genuinely new orchestration. The admin picks ONE winning child market (the winning outcome); `EventService` then loops `SettlementService.resolve_market` over **all** children:

```python
# EventService.resolve_event (NEW) — orchestration only; money path is the REUSED service
async def resolve_event(session, *, group_id, winning_market_id, justification, actor_user_id):
    children = await _load_group_children(session, group_id)          # all binary Market rows in the event
    yes_by_market = {m.id: _yes_outcome_id(m) for m in children}      # case-insensitive YES (mirror service.py:182)
    no_by_market  = {m.id: _no_outcome_id(m)  for m in children}
    for child in children:
        winning_outcome = (yes_by_market[child.id] if child.id == winning_market_id
                                                    else no_by_market[child.id])
        await SettlementService.resolve_market(                        # ← REUSED UNCHANGED, once per child
            session, market_id=child.id, winning_outcome_id=winning_outcome,
            market_resolver=HouseMarketResolveAdapter(),
            justification=justification, actor_user_id=actor_user_id)
    # stamp the group projection (status=RESOLVED, winning_market_id, justification)
```

**Transaction boundary — CRITICAL.** `SettlementService.resolve_market` opens its **own** `async with session.begin()` (`service.py:110`) and is idempotent per market. Two correct options:

| Option | Behavior | Recommendation |
|--------|----------|----------------|
| **A — per-child tx (loop of begins)** | Each child settles & commits independently. A failure on child 4 leaves children 1–3 settled. | **RECOMMENDED for v1.2.** Matches the existing service contract exactly (no signature change), and `resolve_event` can be **retried** — already-settled children are no-ops (PENDING filter, `service.py:113`), so re-running finishes the rest. Idempotent end-to-end. |
| B — single outer tx | Wrap all children in one `session.begin()`; requires refactoring `resolve_market` to accept an already-open tx (a `begin_nested`/savepoint variant). | Defer — changes the proven service signature; not worth the risk for a play-money house event. |

Option A leans on the **exact property Spike 004 validated** (idempotent replay, `004-settlement-acid-transaction/README.md`): re-resolving settles nothing. The admin endpoint can safely retry on partial failure.

### "None / Void" Handling

Two distinct void semantics — both expressible **without new settlement logic**:

1. **Event voided / "none of the above" wins** (e.g. tournament cancelled, no listed outcome occurs): resolve **every** child on its **`NO`** outcome. Every bettor who bet YES on any outcome loses; NO bettors win. This is just `resolve_event` with `winning_market_id=None` ⇒ all children get NO. Represent on the group as `winning_market_id NULL` + a `resolution_source="VOID"` token + justification. **Zero new code** beyond letting `winning_market_id` be `None` in the loop.
   - *Caveat (HIGH-confidence, must document):* this is **not a stake refund** — NO bettors are paid, YES bettors lose, per the existing fixed-odds ledger. If the operator wants a **true cancel-and-refund** (everyone gets their stake back), that is `SettlementService.reverse_settlement` semantics applied at placement, which does **not** exist as a "refund unsettled bet" path today. **Recommendation: scope v1.2 void = "NO wins for all" only**; flag full refund-on-cancel as a separate future requirement (it needs a new ledger flow: `market_liability → user_wallet` for the original stake on PENDING bets).
2. **A child market individually has no clear winner** (mirrored, Gamma `closed` but UMA only `proposed`): the existing `_derive_status` (`schemas.py:58`) already returns `CLOSED` not `RESOLVED`, so `detect_polymarket_resolutions` **skips it** — no settle on an unconfirmed outcome (Spike 002 Pitfall #2). Admin `force-settle` (`settlement/router.py:133`) remains the manual escape hatch per child. **Unchanged.**

### Admin Surface

- **NEW endpoint:** `POST /api/v1/admin/events/{group_id}/resolve` (body: `winning_market_id` | `null` for void + `justification`) → `EventService.resolve_event`. Mirrors the two-step-confirm + mandatory-justification contract of `POST /admin/markets/{id}/resolve` (`settlement/router.py:59`).
- **NEW endpoint:** `POST /api/v1/admin/events/{group_id}/reverse` → loop `SettlementService.reverse_settlement` per child (idempotent, `service.py:252`).
- Per-child `force-settle` / single-market `resolve` stay available for surgical fixes.

---

## Part 4 — Browse/Search Backend + Catalog UI

### Backend Query Model (`CatalogService`, NEW)

PROJECT.md: text search + category filters + status/sort, **no heavy pagination**. The existing `MarketService.list_markets` (`service.py:274`) already filters by `source`/`status`/`category` and `list_home_markets` already does the house-then-Polymarket-by-volume ordering — `CatalogService` generalizes these into one event-aware query.

```python
# CatalogService.browse (NEW)
async def browse(session, *, q: str|None, category: str|None,
                 status: str = "OPEN", sort: str = "volume_24hr", limit: int = 100):
    # Catalog unit = the EVENT (market_group) for grouped markets + STANDALONE markets (group_id IS NULL).
    # Two unions OR a view; simplest: query market_groups + standalone markets, merge, sort, cap.
    stmt = select(MarketGroup).where(MarketGroup.status == status)
    if category: stmt = stmt.where(MarketGroup.category == category)
    if q:        stmt = stmt.where(MarketGroup.title.ilike(f"%{q}%"))      # see search note
    stmt = stmt.order_by(_SORTS[sort]).limit(limit)                        # sort ∈ {volume_24hr, deadline(closing), created_at(new)}
    # ... mirror for standalone markets (group_id IS NULL), merge, re-sort, cap at `limit`
```

**Search choice (MEDIUM):**
- **Phase-1 (ship this):** Postgres `ILIKE '%q%'` on `title`/`question` + `category`. With a few hundred catalog rows this is sub-millisecond and needs **zero extra infra** — fits "no heavy pagination / credible-not-firehose" scope. Add a `pg_trgm` GIN index on `market_groups.title` + `markets.question` (NEW in 0011) so `ILIKE` stays index-backed as the catalog grows.
- **Defer:** Postgres full-text (`tsvector`/`websearch_to_tsquery`) or external search. Overkill for a curated catalog of hundreds of rows; revisit only if the catalog ever broadens (explicitly out-of-scope per PROJECT.md).

**Sort options** (PROJECT.md "volumen, cierre, novedad"):
- `volume_24hr` → `MarketGroup.volume_24hr.desc()` (default — credibility signal)
- `closing` → `MarketGroup.deadline.asc()` filtered to future
- `new` → `MarketGroup.created_at.desc()`

**Status filter:** `OPEN` (default) / `RESOLVED` / `CLOSED` — same `MarketStatus` enum values.

**Indexes to add (NEW, migration 0011):**
- `market_groups`: `(category)`, `(status, volume_24hr)`, GIN `pg_trgm(title)`
- `markets`: `(group_id)`, GIN `pg_trgm(question)`, and the `odds_snapshots (outcome_id, snapshot_at)` composite from Part 2.

### New / Modified API Endpoints

| Endpoint | Purpose | New/Mod |
|----------|---------|---------|
| `GET /api/v1/catalog?q=&category=&status=&sort=` | Browse list (events + standalone markets) | **NEW** (`catalog_router`) |
| `GET /api/v1/categories` | Category nav list (curated taxonomy + counts) | **NEW** |
| `GET /api/v1/events/{slug}` | One event: title, description, children with `group_item_title` + current odds + winner | **NEW** |
| `GET /api/v1/markets` (home) | Keep for back-compat OR redirect to `/catalog` | **MODIFIED/keep** |
| `GET /api/v1/markets/{slug}` | Binary market detail — **unchanged**, reused for standalone + drill-in from an event child | **REUSED** |

### Catalog UI (Next.js — NEW pages + MODIFIED components)

| File | Change |
|------|--------|
| `frontend/src/app/page.tsx` | **MODIFIED** — render `CatalogBrowse` (category nav + search box + filtered grid) instead of bare `MarketList` |
| `frontend/src/components/catalog-browse.tsx` | **NEW** — client island: search input (debounced) + category tabs + sort/status `Select` (reuse `components/ui/select.tsx`), calls `/api/v1/catalog` |
| `frontend/src/components/category-nav.tsx` | **NEW** — horizontal category chips from `/api/v1/categories` |
| `frontend/src/components/market-card.tsx` | **MODIFIED** — when item is an event, show N-outcome summary (top 2–3 `group_item_title` + odds, "+K more"); when standalone, current binary card |
| `frontend/src/components/event-card.tsx` | **NEW** (or the modified card branch) — event tile |
| `frontend/src/app/events/[slug]/page.tsx` | **NEW** — event detail: list each child outcome with `group_item_title`, per-outcome odds + a "Bet" affordance that drills into the existing `/markets/[slug]` binary flow (or inlines the order form per child) |
| `frontend/src/components/event-outcome-row.tsx` | **NEW** — one outcome row (label, probability bar, current odds, bet button) |
| `frontend/src/lib/api.ts` | **MODIFIED** — add `CatalogItem`/`EventDetail`/`Category` types + `fetchCatalog`/`fetchEvent`/`fetchCategories` (mirror existing `fetchMarkets`/`fetchMarket`) |
| Price chart per outcome | **REUSED** — `PriceHistorySection` + `/markets/{slug}/price-history` already work per child market; the event page renders one chart per outcome by reusing the child's slug |

**Key UI reuse:** an event page is **a list of child binary markets**; betting on an outcome = betting YES on that child via the *unchanged* `OrderEntryForm` + `POST /bets` flow. Real-time per-outcome odds reuse `use-market-socket` per child (each child publishes on its own market_id channel, `publisher.py`). No new WS plumbing.

---

## Data Flow

### Sync Flow (MODIFIED)

```
Celery Beat (redbeat) every 30s
   └─ poll_polymarket_events  [NEW task, replaces poll_polymarket_top25 in schedule]
        └─ Redis SETNX lock (REUSED pattern, tasks.py:55)
        └─ for category in POLYMARKET_CATEGORIES:                    [NEW config]
             GammaClient.fetch_events(tag_id, order=volume24hr, limit=top_n)  [MODIFIED client]
             filter volume24hr >= vol_floor                          [NEW]
             PolymarketAdapter.sync_events(session, events, category)[MODIFIED adapter]
               ├─ upsert market_groups  ON CONFLICT(source, source_event_id)   [NEW idx 0011]
               └─ for child in event.markets:
                    upsert markets ON CONFLICT(source, source_market_id)        [REUSED idx 0004]
                    stamp group_id + group_item_title
                    upsert YES/NO outcomes                                      [REUSED adapter loop]
        └─ commit; publish per-child odds deltas (REUSED publisher.py)
```

### House Event Resolution Flow (NEW orchestration over REUSED settlement)

```
Admin UI "Resolve event, winner = Spain"  (two-step confirm + justification)
   └─ POST /api/v1/admin/events/{group_id}/resolve            [NEW endpoint]
        └─ EventService.resolve_event                          [NEW]
             for child in children:
               winning = YES(child) if child==winner else NO(child)
               SettlementService.resolve_market(child, winning, …)  [REUSED, one ACID tx each]
             stamp market_groups winner/status/justification
```

### Browse Flow (NEW)

```
Player types "election" + picks Politics + sort=volume
   └─ GET /api/v1/catalog?q=election&category=politics&sort=volume_24hr  [NEW]
        └─ CatalogService.browse: ILIKE + category + status + ORDER BY + LIMIT 100  [NEW, no pagination]
   └─ click event → GET /api/v1/events/{slug} → event-detail page        [NEW]
        └─ click outcome → existing /markets/{slug} binary bet flow       [REUSED]
```

---

## Integration Points

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `EventService` ↔ `SettlementService` | Direct call, per child, in a loop | The whole multi-outcome payoff — **no new money code**; idempotent per `service.py:113` |
| `EventService` ↔ `MarketService.create_market` | Direct call, per child (house create) | Reuses binary create incl. slug-collision retry (`service.py:44`) |
| `PolymarketAdapter.sync_events` ↔ `_upsert_one_market` | Extract today's `sync_top25` body into a reusable helper | Same upsert, same `(source, source_market_id)` idempotency |
| `detect_polymarket_resolutions` ↔ event children | None (children are plain POLYMARKET markets) | **Auto-works unchanged** — the key reuse win |
| `snapshot_odds` ↔ event children | None (children are OPEN markets) | **Auto-works unchanged**; only volume of rows grows (Part 2) |
| `CatalogService` ↔ `MarketGroup` + standalone `Market` | Two queries merged + capped | Catalog unit = event OR ungrouped market |
| Bets ↔ event | None | Bets always target a **child** market+outcome via the unchanged `BetService` |

### External Services

| Service | Integration Pattern | Notes / Gotchas |
|---------|---------------------|-----------------|
| Gamma `/events` | `GammaClient.fetch_events` (new), tenacity retry, bounded pool | `tags[]` inline only when `tag_id` filter present; `markets[]` children carry `groupItemTitle` (per-outcome label) — preserve case ("Yes"/"No") as the binary path does (`adapter.py:245`) |
| Gamma `/tags` | One-time / rare fetch to seed the curated `tag_id` map | Tags are noisy/micro — **do not** mirror 1:1; pin a curated set (Part 2) |
| UMA (via Gamma per child) | `detect_polymarket_resolutions` per child | **Unchanged**; `_derive_status` already guards `closed≠resolved` (Spike 002) |

---

## Architectural Patterns

### Pattern 1: Container/Leaf Split (event vs market)

**What:** The "event" is a metadata container (`market_groups`); the bettable unit stays the binary `Market` leaf. Money, odds, liability, settlement live **only** on leaves.
**When to use:** Whenever a "grouping" concept would otherwise tempt you to overload an existing bettable entity.
**Trade-offs:** + Binary core queries untouched, zero constraint changes, mirrored & house unified. − Catalog queries must union groups + standalone markets (mild) and the group's volume/winner are projections, not authoritative.

### Pattern 2: Settlement-as-a-Loop (orchestration over the proven primitive)

**What:** Multi-outcome resolution = loop `SettlementService.resolve_market` per child; idempotent replay makes partial failure safely retryable (Spike 004).
**When to use:** A "composite" operation whose parts are already individually transactional and idempotent.
**Trade-offs:** + No change to the validated ACID money path; retryable. − Not one global atomic tx (a crash mid-loop leaves some children settled) — acceptable because each is consistent and re-run completes the rest.

### Pattern 3: Reuse-the-Upsert (sync_events over sync_top25)

**What:** Extract today's per-market upsert body into `_upsert_one_market(parsed, group_id)`; `sync_events` adds only the parent-group upsert + `group_id` stamping.
**When to use:** Extending an ingestion path to a richer source shape that *contains* the existing shape.
**Trade-offs:** + One idempotency story, one parser style (`GammaEvent` mirrors `GammaMarket`). − A small refactor of `sync_top25` (keep the function for tests; have it delegate to the helper).

---

## Anti-Patterns

### Anti-Pattern 1: Native categorical market (widening `outcomes`)

**What people do:** Add a `market_type` and let one `Market` carry 3+ outcomes with a single liability pool.
**Why it's wrong:** Breaks the binary odds model, the per-outcome `current_odds ∈ [0,1]` CHECK, the settlement math (Spike 004 assumes binary win/lose), and forces every query to branch. Directly violates the LOCKED decision.
**Do this instead:** Event-of-binaries — N binary markets grouped by `market_groups`. (This whole document.)

### Anti-Pattern 2: Mirroring the Gamma tag firehose as categories

**What people do:** Create one category per Gamma tag.
**Why it's wrong:** Tags are hyper-specific ("caitlin clark", "redbull") → hundreds of junk categories, an incredible nav, exactly the noise PROJECT.md excludes.
**Do this instead:** A small curated taxonomy (~7 categories) each pinned to a known `tag_id`; sync iterates the curated list.

### Anti-Pattern 3: Settling the event in one giant hand-rolled transaction

**What people do:** Refactor `resolve_market` to take an open session and wrap all children in one `begin()` for "atomicity."
**Why it's wrong:** Mutates the Spike-004-validated service signature, risking the one piece that must stay correct (money), for a benefit (all-or-nothing across children) that idempotent retry already approximates.
**Do this instead:** Loop the unchanged service; rely on PENDING-filter idempotency for retry (Option A, Part 3).

### Anti-Pattern 4: Heavy pagination / external search engine for the catalog

**What people do:** Add cursor pagination + Elasticsearch for a few hundred curated rows.
**Why it's wrong:** Out-of-scope (PROJECT.md "sin paginación pesada"), infra cost, demo complexity.
**Do this instead:** `ILIKE` + `pg_trgm` GIN index + `LIMIT 100`. Revisit only if the catalog ever broadens (explicitly deferred).

---

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Demo / 0–1k users | Current design is complete. ~7 categories × ~20 events; `ILIKE` browse; per-child settle. Nothing to add. |
| 1k–100k users | First pressure is **odds_snapshots growth** (~23× rows). Add `(outcome_id, snapshot_at)` composite index (already specced) + a snapshot-prune task. Catalog browse still trivial. |
| 100k+ users / broad catalog | Out of v1.2 scope. Would revisit: full-text search, snapshot table partitioning by month, materialized catalog view, group-volume denormalization refresh job. |

### Scaling Priorities

1. **First bottleneck:** `odds_snapshots` insert/scan volume from many more OPEN markets. Fix: composite index (ship in 0011) + retention prune (later phase). Postgres handles the absolute volume easily; the index is for the 30-day downsample read path (`service.py:393`).
2. **Second bottleneck:** Catalog `ILIKE` once rows climb. Fix: `pg_trgm` GIN (ship in 0011). Already mitigated.

---

## Dependency-Ordered Build Sequence (for the roadmapper)

Strict model → sync → settlement → API → UI, each step shippable and testable on the layer below.

1. **MODEL — `market_groups` + `Market.group_id`/`group_item_title` + indexes**
   - Migration `0011_phase13_market_groups` (new table, two nullable cols on `markets`, partial unique idx `(source, source_event_id)`, catalog indexes, `pg_trgm`, `odds_snapshots` composite).
   - `MarketGroup` ORM model + relationship; `Market` relationship.
   - *No behavior change yet — pure schema seam. Verifiable by migration up/down + model import.*

2. **SYNC — Gamma events ingestion (mirrored events appear)**
   - `GammaEvent` Pydantic schema (sibling of `GammaMarket`; parse `markets[]`, `tags[]`, `groupItemTitle`).
   - `GammaClient.fetch_events` (+ keep `fetch_top_markets`).
   - Refactor `sync_top25` body → `_upsert_one_market`; add `PolymarketAdapter.sync_events`.
   - `POLYMARKET_CATEGORIES` config + curated `tag_id` seeding (one-off `/tags` lookup).
   - `poll_polymarket_events` task; swap it into the redbeat schedule (drop `poll_polymarket_top25` from schedule).
   - *Verifiable: a sync cycle creates groups + grouped children; `snapshot_odds`/`detect_resolutions` keep working untouched.*

3. **SETTLEMENT — house event resolve/void + (mirrored auto already works)**
   - `EventService.resolve_event` / `reverse_event` (loop the **unchanged** `SettlementService`).
   - Void path = all-children-NO when `winning_market_id is None`.
   - Mirrored resolution: **no code** — confirm `detect_polymarket_resolutions` settles children; add the group winner/status read-projection.
   - *Verifiable: house event with bets on each outcome settles correctly; replay is a no-op (Spike 004 property).*

4. **API — house event CRUD + catalog/search + event detail**
   - `EventService.create_event`/`update_event` (loop `MarketService.create_market`).
   - `catalog_router`: `GET /catalog`, `GET /categories`, `GET /events/{slug}`.
   - `event` admin endpoints: `POST /admin/events`, `PATCH /admin/events/{id}`, `POST /admin/events/{id}/resolve`, `/reverse`.
   - `CatalogService.browse` (ILIKE + filters + sort + limit).
   - *Verifiable: API returns events + standalone markets, filtered/sorted; house event lifecycle end-to-end.*

5. **UI — catalog browse + category nav + event detail + admin event ops**
   - `lib/api.ts` types + fetchers.
   - `catalog-browse` + `category-nav`; modify `page.tsx` + `market-card`.
   - `app/events/[slug]/page.tsx` + `event-outcome-row` (reuse `OrderEntryForm`, `PriceHistorySection`, `use-market-socket` per child).
   - Admin event create/edit/resolve forms (mirror existing market admin forms + two-step confirm).
   - *Verifiable: player browses categories, searches, opens an event, bets per outcome; admin creates/resolves a house event.*

6. **SEED/DEMO — update `bin/seed_demo.py`**
   - Seed a few house **events** (multi-outcome) + assign categories to seeded markets so the demo browse/nav is populated. Reuse `EventService` create + the existing bet/settle seeding so money discipline holds.
   - *Verifiable: `uv run python bin/seed_demo.py` yields a populated category catalog with at least one multi-outcome event.*

**Critical-path dependencies:** 1 gates everything (schema). 2 needs 1 (writes group rows). 3 needs 1 (reads children) but **not** 2 for house events. 4 needs 1–3. 5 needs 4. 6 needs 3+4. Mirrored auto-resolution (in 3) is "free" — verify, don't build.

---

## Sources

- **Real backend code (HIGH):** `backend/app/markets/{models,service,router,schemas,enums}.py`, `backend/app/settlement/{service,adapters,router}.py`, `backend/app/integrations/polymarket/{client,adapter,tasks,schemas}.py`, `backend/app/integrations/market_source.py`, `backend/app/bets/{models,service,adapters}.py`, `backend/app/main.py`, `backend/alembic/versions/0004_phase6_polymarket_sync.py`, `backend/bin/seed_demo.py`, `frontend/src/app/page.tsx`, `frontend/src/app/markets/[slug]/page.tsx`, `frontend/src/lib/api.ts`, `frontend/src/components/market-list.tsx`.
- **Spikes (HIGH):** `.planning/spikes/002-polymarket-gamma-parser/` (gamma parser, state machine, `groupItemTitle`/stringified-JSON quirks), `.planning/spikes/004-settlement-acid-transaction/` (idempotent per-market ACID settle).
- **Polymarket Gamma API (HIGH for shape, live 2026-06-04):** `gamma-api.polymarket.com/events` (nested `markets[]` with `conditionId`/`outcomes`/`groupItemTitle`/`clobTokenIds`; event `volume24hr`/`negRisk`/`tags[]`), `gamma-api.polymarket.com/tags` (`{id,label,slug}`, noisy taxonomy), `docs.polymarket.com/developers/gamma-markets-api/get-events` (`tag_id`/`related_tags`/`order`/`ascending`/`limit`/`offset`).
- **Project context (HIGH):** `.planning/PROJECT.md` (locked v1.2 decisions, out-of-scope boundaries), `xpredict/CLAUDE.md` (stack, phase workflow).

---
*Architecture research for: XPredict v1.2 Credible Catalog — multi-outcome events + curated category catalog (DELTA)*
*Researched: 2026-06-04*
