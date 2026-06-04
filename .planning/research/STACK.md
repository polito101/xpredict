# Stack Research

**Domain:** v1.2 "Credible Catalog" delta — multi-outcome events (event-of-binaries), curated per-category catalog from Polymarket Gamma tags, browse (text search + category filters + status/sort). Subsequent milestone on a shipped FastAPI/Next.js prediction market.
**Researched:** 2026-06-04
**Confidence:** HIGH

> **Headline: this milestone needs essentially ZERO new dependencies.** One Postgres
> extension (`pg_trgm`, enabled via an Alembic migration), two additional Gamma API
> endpoints (`GET /events`, `GET /tags`) wired into the **existing** `GammaClient`, and
> new tables/columns. **No new Python package, no new Node package, no search engine.**
> SQLAlchemy 2.0 + httpx + the existing Pydantic-v2 Gamma parser already cover events,
> tags, and search natively. The rest of this file is the WHY, the exact Gamma
> endpoints/params/limits, and the explicit "do NOT add" list.

---

## Recommended Stack (the v1.2 delta only)

### Core Technologies (already in the project — reused, version-locked)

| Technology | Version (in repo) | Purpose for v1.2 | Why it already covers the delta |
|------------|-------------------|------------------|---------------------------------|
| PostgreSQL | 16 | `events` table + grouping FK; search index | Native FTS (`tsvector`) **and** `pg_trgm` ship in core PG 16 — no third-party search needed. |
| `pg_trgm` (PG extension) | bundled w/ PG 16 (`CREATE EXTENSION`) | GIN-index-accelerated substring search on market/event title | **Only "new" infra in the milestone.** Indexes infix `ILIKE '%term%'` (which B-tree/tsvector cannot), adds typo tolerance, no generated column or trigger needed. Enabled in a migration, not a dependency. |
| SQLAlchemy 2.0 async | `>=2.0.43,<2.1` | Event model, grouping query, search expression | Expresses everything natively: `.ilike()`, `func.similarity()`, `column.op("%")()` for trigram, and `func.to_tsvector/websearch_to_tsquery` **if** FTS is ever chosen. No ORM search plugin. |
| httpx (async) | `>=0.28,<0.29` | Call `GET /events` + `GET /tags` | The existing `GammaClient` (lazy singleton + tenacity retry + bounded pool) just needs 2 new methods. No new HTTP lib. |
| Pydantic v2 | `>=2.10,<3.0` | Parse `GammaEvent` + `GammaTag` | The spike-002 `GammaMarket` parser (stringified-JSON validator, `extra` policy, `Decimal` discipline) is the exact template for `GammaEvent`/`GammaTag`. Reuse it. |
| `python-slugify` | `>=8.0,<9.0` | Normalize tag label → category slug; event slug | **Already a dependency** (`app.markets.models.generate_slug`). Covers all tag/category normalization. No new normalization lib. |
| Celery + redbeat | `>=5.5` / `>=2.2` | Per-category sync task (extends the top-25 poll) | The existing `poll_polymarket_top25` Beat task + RedBeat lock pattern is reused for `sync_curated_catalog`. No new scheduler. |
| Next.js 15 / React 19 / Tailwind 4 / shadcn/ui | locked | Browse UI (search box, category chips, sort/status), event detail | shadcn primitives (`Tabs`, `Select`, `Input`, `Badge`, `ToggleGroup`) cover the entire browse + multi-outcome UI. No new component lib. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| — | — | — | **None required.** Every capability the milestone needs is already a dependency (see table above). The "addition" is a Postgres extension + new application code, not a package. |

Optional, only-if-FTS-path-chosen (NOT recommended — see decision below):

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `sqlalchemy-utils` `TSVectorType` *(optional)* | `>=0.41` | Declarative `tsvector` column + GIN | Only if you adopt FTS **and** want a generated-column abstraction. Plain SQLAlchemy `func.to_tsvector` + a raw-SQL GIN index in the migration does the same with zero new dep — **prefer that.** |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| Alembic | `pg_trgm` extension + GIN index + new tables/columns | Follow the existing raw-SQL pattern: `op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")` then `op.create_index(..., postgresql_using="gin", postgresql_ops={"question": "gin_trgm_ops"})`. Same file style as `0004_phase6_polymarket_sync.py`. |
| testcontainers Postgres | Integration-test the GIN search + event grouping | Already wired (`tests/integration`). The `pg_trgm` extension must be created by the migration so the test DB has it — testcontainers runs migrations. |
| VCR-style JSON fixtures | Capture **`/events`** + **`/tags`** responses | **GAP:** spike-002 fixtures are single-`/markets` payloads — they do **not** contain the nested `events[]`/`tags[]`. Capture fresh `/events` (with embedded `markets[]` + `tags[]`) and `/tags` fixtures for offline parser tests. |

## Installation

```bash
# Python: NOTHING to add. (Optional FTS-only abstraction, NOT recommended:)
#   uv add "sqlalchemy-utils>=0.41"   # skip — use plain func.to_tsvector instead

# Node: NOTHING to add.

# The only "install" is a Postgres extension, done inside an Alembic migration:
#   op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
```

---

## The two decisions this research resolves

### Decision 1 — Search at curated-catalog scale: **pg_trgm GIN over ILIKE; tsvector is over-engineering**

**Scale reality:** the catalog is *curated/bounded* by design (top-N per category with a
volume floor; firehose explicitly out of scope per PROJECT.md). Local searchable rows are
realistically **a few hundred to low-thousands** of markets/events — not the 8,815+ events
Gamma exposes globally (verified live via `/events/pagination` → `totalResults: 8815`).

| Option | Verdict for v1.2 | Reasoning |
|--------|------------------|-----------|
| **`pg_trgm` + GIN (`gin_trgm_ops`) on `question`/event `title`** | **RECOMMENDED** | Accelerates infix `ILIKE '%term%'` (PG 9.1+) — the one pattern plain B-tree **and** `tsvector` cannot do for substrings. Adds typo tolerance (`similarity()`) for free. One migration line + one index. No generated column, no trigger, no stop-word/stemming config. Index cost is trivial at this row count. |
| Plain `ILIKE '%term%'` (no index) | Acceptable fallback | Perfectly fine functionally at a few-thousand rows (seq scan is sub-ms). The **only** reason to prefer trigram is the GIN index + fuzzy matching; if you want the simplest possible first cut, ship `ILIKE` and add the `pg_trgm` GIN later — it's a pure migration, no code change to the query shape. |
| Full-text `tsvector` + `websearch_to_tsquery` + GIN | **NOT recommended here** | Built for linguistic/relevance ranking over large documents. Market questions are short titles; stemming/ranking adds storage (generated column) + complexity (trigger or `GENERATED ALWAYS AS`) for little benefit at this scale, and **tsvector does not match arbitrary substrings/typos** (it matches lexemes). Reach for it only if requirements grow to relevance-ranked multi-field search. |

**Bottom line:** `WHERE question ILIKE '%' || :q || '%'` backed by a `pg_trgm` GIN index is
the right, non-over-engineered choice. SQLAlchemy 2.0 expresses it with `Market.question.ilike(f"%{q}%")`
(parameterized) — and the optional fuzzy path with `func.similarity(Market.question, q)` /
`Market.question.op("%")(q)`. **No search library, no Elasticsearch, no Meilisearch.**

> Polymarket also exposes its **own** search (`GET /public-search?q=...`, 350 req/10s). Do
> **not** proxy user search to it: (a) it returns the *full* Polymarket catalog, not your
> curated subset, so results would point at markets you never mirrored; (b) it couples your
> search latency/availability to a third party. Search **local** rows. `/public-search` is
> only useful as an admin discovery aid when picking events to mirror — optional, not core.

### Decision 2 — Multi-outcome modeling: **new `events` table grouping existing binary `markets` (no model fork)**

The locked decision (event-of-binaries) maps cleanly onto the **existing** schema with the
smallest possible delta — no new outcome model, no change to the binary YES/NO
`Outcome`/settlement path, and the binary `CheckConstraint` on outcomes is untouched:

- **New `events` table** (house + mirrored): `id`, `slug` (unique), `title`, `description`,
  `category` (the curated tag), `source` (`HOUSE`/`POLYMARKET`), `source_event_id`
  (Gamma event id), `polymarket_slug`, `volume`/`volume_24hr` (Money alias), `status`,
  `created_at`/`updated_at`, `tenant_id` ghost column (mirror `Market`). Add a partial
  unique index on `(source, source_event_id)` for idempotent upsert — **identical pattern**
  to `ix_markets_source_source_market_id` in migration `0004`.
- **New nullable `Market.event_id` FK** → `events.id` (`ON DELETE SET NULL`/`CASCADE` per
  design), indexed. A binary market with `event_id = NULL` is a standalone binary (today's
  behavior, unchanged); a group of markets sharing an `event_id` is an N-outcome event.
  Each constituent market stays a real binary YES/NO market → **settlement, bets, odds
  snapshots, price history all work as-is.** "Resolve event = pick winning outcome → settle
  the constituent binaries" is orchestration over the existing idempotent `SettlementService`.
- **Category** finally gets populated: today `Market.category` is set **only** on HOUSE
  create and is **always NULL for Polymarket** (the `/markets` poll has no tags). v1.2 fixes
  this by sourcing category from the Gamma **event's** tags (see endpoints below) and writing
  it onto both the `Event` and its constituent `Market` rows during sync.

This is a schema/code delta, not a stack delta — called out here because it dictates the
migration + the new Gamma endpoints, and confirms **no new persistence/ORM technology** is needed.

---

## Polymarket Gamma API — exact current endpoints, params, and limits

Base URL (already in config): `https://gamma-api.polymarket.com` (public, no auth).
Verified live + against `docs.polymarket.com` on 2026-06-04.

### `GET /events` — the multi-outcome + category source (NEW call)

Each **event** embeds its constituent **`markets[]`** (the binaries) **and** its **`tags[]`**
in a single response — so one `/events` call yields the grouping AND the category, no N+1.

Query params (current): `limit`, `offset`, `order`, `ascending`, `id`, `slug`, `archived`,
`active`, `closed`, `liquidity_min`/`liquidity_max`, `volume_min`/`volume_max`,
`start_date_min`/`start_date_max`, `end_date_min`/`end_date_max`, **`tag`**, **`tag_id`**,
**`tag_slug`**, **`related_tags`**.

Curated-catalog sync recipe (per category): for each chosen tag,
`GET /events?tag_id={id}&active=true&closed=false&order=volume24hr&ascending=false&limit=N`,
then apply the local volume floor before upserting. (Mirror the existing top-25 call shape in
`GammaClient.fetch_top_markets`, just on `/events` with a tag filter.)

Event object key fields (verified): `id`, `ticker`, `slug`, `title`, `description`,
`active`, `closed`, `archived`, `featured`, `liquidity`, `volume`, `volume24hr`,
`volume1wk`/`1mo`/`1yr`, `openInterest`, `startDate`/`endDate`/`creationDate`,
`negRisk`, `commentCount`, `createdAt`/`updatedAt`, **`markets[]`**, **`tags[]`**.
Nested **market** fields match the spike-002 `GammaMarket` exactly, **plus** the
grouping fields **`groupItemTitle`** and **`groupItemThreshold`** (use `groupItemTitle`
as the per-outcome display label inside an event). Nested **tag**: `id`, `label`, `slug`,
`forceShow` (and `forceHide`, `publishedAt`, `createdAt`/`updatedAt`).

> **Reuse the spike-002 parser quirks verbatim** on the nested markets: `outcomes`,
> `outcomePrices`, `clobTokenIds` are **stringified JSON**; use STRING `volume`/`liquidity`
> → `Decimal` (never `*Num` floats); `extra` policy by env; never settle on `closed=true`
> alone. The `_derive_status` state machine applies per constituent market unchanged.

### `GET /events/pagination` — bounded-count variant (OPTIONAL)

Returns `{ "data": [ ...events... ], "pagination": { "hasMore": bool, "totalResults": int } }`
(verified live: `totalResults: 8815`). Useful **only** if an admin "browse all of Polymarket
to pick what to mirror" screen needs a total. The **player** catalog is curated/bounded, so
the PROJECT decision "no heavy pagination" stands — player browse needs neither this nor
offset paging.

### `GET /tags` and friends — category catalog source (NEW call)

- `GET /tags?limit=...&offset=...` → flat array of `{ id, label, slug, forceShow, isCarousel?, createdAt, updatedAt, requiresTranslation }`.
- `GET /tags/{id}`, `GET /tags/slug/{slug}` → single tag.
- `GET /tags/{id}/related-tags`, `GET /tags/slug/{slug}/related-tags`, `GET /tags/{id}/relationships` → related tags (useful to seed a sensible category set).

Tags are Polymarket's category primitive. **Curate a fixed allow-list of category tags**
(e.g. Politics, Sports, Crypto, Pop Culture, Economy) rather than ingesting all tags — the
raw `/tags` list is huge and noisy (live sample included one-off entities like
"caitlin-clark", "timothee-chalamet", and even a typo'd "product-marekt-fit"). Normalize
each chosen tag's `label` → a category slug with the **already-present** `python-slugify`.

### Current rate limits (verified `docs.polymarket.com`, 2026-06-04)

Gamma API per-endpoint, per 10 seconds:

| Endpoint | Limit (req / 10s) |
|----------|-------------------|
| general Gamma | 4,000 |
| `GET /events` | **500** |
| `GET /markets` | 300 |
| `GET /tags` (and `/comments`) | **200** |
| `GET /public-search` | 350 |

A per-category catalog sync (a handful of categories × one `/events` call each, every poll
interval) is **orders of magnitude** under these limits — the existing 25s RedBeat lock +
single-batch-call discipline (one call per category, never per-market) keeps it trivially
compliant. The stale "300 req/10s" comment in `client.py` refers to `/markets`; `/events`
is 500/10s.

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| `pg_trgm` GIN + `ILIKE` | Postgres FTS (`tsvector`+`websearch_to_tsquery`) | Only if search grows to relevance-ranked, multi-field (title+description+category) with stemming. Not needed for short-title substring search at curated scale. |
| `pg_trgm` GIN + `ILIKE` | External engine (Meilisearch/Elasticsearch/Typesense) | Never for v1.2 — adds a service, infra, and sync pipeline for a bounded catalog. Massive over-engineering. |
| Search **local** curated rows | Proxy to Gamma `GET /public-search` | Only as an **admin** mirror-discovery aid. Never for player search (returns un-mirrored markets; couples uptime to a third party). |
| New `events` table + nullable `Market.event_id` FK | Generic `market_group` / EAV multi-outcome table | The event-of-binaries decision is locked; a dedicated `events` table mirroring `markets`' conventions is simpler and reuses the partial-unique-upsert + settlement paths. |
| Reuse `GammaClient` + new `GammaEvent` parser | New HTTP client / SDK (e.g. `polymarket-kit`, `py-clob-client`) | Never — the existing tenacity+httpx client and spike-002 Pydantic parser already handle Gamma's quirks; a third-party SDK adds a dep and re-learns the same stringified-JSON gotchas. |
| `python-slugify` (present) for tag/category normalization | `unidecode` / custom slug util / `text-unidecode` | Not needed — `python-slugify` already handles unicode→ascii slugging (it depends on `text-unidecode` internally). |

## What NOT to Use (explicit "do NOT add" list)

| Avoid adding | Why | Use Instead |
|--------------|-----|-------------|
| Elasticsearch / OpenSearch / Meilisearch / Typesense / Algolia | A whole search service + sync pipeline for a **curated, bounded** catalog is unjustifiable over-engineering. | Postgres `pg_trgm` GIN + `ILIKE` (and `tsvector` only if ever needed). |
| `tsvector`/FTS as the v1.2 default | Stemming/ranking/generated-column complexity for short titles; doesn't do substring/typo. | `pg_trgm` GIN + infix `ILIKE`. |
| A new Python HTTP client or Polymarket SDK | The existing `GammaClient` (httpx + tenacity + bounded pool + lock) already works and is tested. | Add `fetch_events()` / `fetch_tags()` methods to `GammaClient`. |
| A new tag/category normalization or text lib (`unidecode`, `slugify`-alternatives, NLP) | `python-slugify` is already a dependency and sufficient. | `app.markets.models`-style `slugify(...)`. |
| `sqlalchemy-utils` `TSVectorType` (or any ORM search plugin) | Only relevant on the FTS path you're not taking; even then plain `func.to_tsvector` + raw-SQL GIN index avoids the dep. | Native SQLAlchemy 2.0 expressions. |
| Offset/keyset pagination machinery for the player browse | Catalog is curated/bounded; PROJECT decision is "no heavy pagination". | A sensible `LIMIT` + category/status filters + sort; the existing `list_markets` offset path is more than enough if any paging is wanted at all. |
| Proxying player search to Gamma `/public-search` | Returns the full un-mirrored Polymarket catalog; couples your search to a 3rd-party endpoint + its 350/10s limit. | Search local curated rows; keep `/public-search` as an optional admin discovery tool only. |
| `GET /markets` for the catalog | It has **no tags** inline → can't derive category, and doesn't express grouping. | `GET /events` (embeds `markets[]` **and** `tags[]`). |

## Stack Patterns by Variant

**If you ship the simplest first cut:**
- `WHERE question ILIKE '%' || :q || '%'` with **no** index, plus exact `category =` filter
  (the existing `list_markets` already does the category/status filters and offset paging).
- Add the `pg_trgm` GIN index in a follow-up migration — **no query rewrite** needed, it just
  starts accelerating the same `ILIKE`. Because it's index-only, it's a safe, reversible add.

**If you want credible search + fuzzy matching from day one (recommended):**
- Migration: `CREATE EXTENSION IF NOT EXISTS pg_trgm` + GIN index with `gin_trgm_ops` on
  `markets.question` (and `events.title`).
- Query: `ILIKE` for the filter; optionally `ORDER BY similarity(question, :q) DESC` to rank,
  and a `similarity(...) > 0.1` threshold for typo tolerance. All native SQLAlchemy 2.0.

**If multi-outcome event sync needs the category but you want minimal calls:**
- Drive the catalog from `GET /events?tag_id=...` (embeds markets+tags) — one call per
  curated category per poll. Write `category` onto the `Event` and cascade it to each
  constituent `Market`. This is the call that finally populates the long-empty
  `Market.category` for Polymarket rows.

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| PostgreSQL 16 | `pg_trgm` (bundled) | `CREATE EXTENSION IF NOT EXISTS pg_trgm` — no version pin, ships with PG core. testcontainers test DB gets it because the migration runs there. |
| SQLAlchemy `2.0.43` | `pg_trgm` ops + `tsvector` | `postgresql_using="gin"` + `postgresql_ops={"question": "gin_trgm_ops"}` on `Index(...)`; `func.similarity`, `col.op("%")()`, `func.to_tsvector`/`func.websearch_to_tsquery` all native. No plugin. |
| httpx `0.28` | Gamma `/events`,`/tags` | Same client/timeouts/pool as the working `/markets` poll. |
| Pydantic `2.10` | `GammaEvent`/`GammaTag` | Reuse spike-002 validators (stringified-JSON, Decimal, env-based `extra`). |
| `python-slugify 8.x` | tag→category slug | Already installed; `text-unidecode` transitive dep handles unicode. |

## Sources

- Existing code (ground truth): `backend/app/integrations/polymarket/client.py` (GammaClient, `/markets` call, stale "300 req/10s" note), `adapter.py` (`sync_top25` ON CONFLICT upsert), `tasks.py` (RedBeat poll), `schemas.py` (spike-002 `GammaMarket` parser), `backend/app/markets/{models,service,schemas,router}.py` (binary Market model, `category` set only on HOUSE, `list_markets` filters/paging, **no search today**), `backend/alembic/versions/0004_phase6_polymarket_sync.py` (partial-unique-index + raw-SQL pattern to copy), `backend/pyproject.toml` (locked deps incl. `python-slugify`), `.planning/PROJECT.md` (curated/bounded + "no heavy pagination" decisions), spike-002 README + fixtures (parser quirks; fixtures are single-`/markets`, **lack `/events`/`/tags`**). — HIGH
- `docs.polymarket.com` — Gamma API endpoints (`/events`, `/events/pagination`, `/tags`, `/tags/{id}`, `/tags/slug/{slug}`, `/tags/{id}/related-tags`, `/public-search`), `/events` params (`tag_id`, `tag_slug`, `related_tags`, `order`, `ascending`, `active`, `closed`, `limit`, `offset`), and **current rate limits** (events 500, markets 300, tags 200, public-search 350 req/10s). — HIGH
- Live Gamma API (`gamma-api.polymarket.com`, 2026-06-04) — event embeds `markets[]` + `tags[]`; `groupItemTitle`/`groupItemThreshold` grouping fields; tag shape `{id,label,slug,forceShow,...}`; `/events/pagination` → `{data,pagination:{hasMore,totalResults:8815}}`; `/public-search` → `{events,tags,profiles}`. — HIGH
- PostgreSQL docs (`/docs/current/pgtrgm.html`, textsearch) — `gin_trgm_ops` accelerates infix `LIKE/ILIKE` (PG 9.1+), GIN preferred for small result sets; `tsvector`/`websearch_to_tsquery` are lexeme/ranking-oriented (don't match substrings). — HIGH
- Search-approach corroboration (Aiven, thoughtbot, pganalyze, Medium guides) — at a few-thousand rows ILIKE is fine; trigram GIN is the right index for substring+fuzzy; FTS is for linguistic/relevance needs. — MEDIUM (multiple independent sources agree)

---
*Stack research for: XPredict v1.2 Credible Catalog — multi-outcome events + curated category catalog + browse*
*Researched: 2026-06-04*
