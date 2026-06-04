# Project Research Summary

**Project:** XPredict v1.2 - Credible Catalog
**Domain:** Multi-outcome events (event-of-binaries) + curated category catalog + browse - DELTA on a shipped play-money prediction market
**Researched:** 2026-06-04
**Confidence:** HIGH

---

## Executive Summary

XPredict v1.2 adds three tightly coupled capabilities to the shipped binary-market platform: (1) multi-outcome events modeled as a group of N independent binary markets (event-of-binaries), (2) a curated per-category catalog sourced from Polymarket Gamma tags with a volume floor, and (3) browse - text search, category tabs, status filter, and sort. The locked architecture is additive: a new market_groups table plus a nullable Market.group_id FK are the only schema changes; the binary CHECK constraint, the per-market SettlementService, and all existing bet/odds/ledger paths stay unchanged. This milestone needs zero new Python or Node dependencies - only enabling the bundled pg_trgm Postgres extension via an Alembic migration.

The recommended approach is model to sync to settlement to API to UI to seed, in strict dependency order. The event model is a thin metadata container; settlement of a multi-outcome event is a loop of the existing idempotent SettlementService.resolve_market per child binary. Curated sync replaces the global top-25 Celery task with a per-category GET /events?tag_id={id} call that embeds constituent markets and tags in one response - eliminating the N+1 problem and finally populating the long-empty Market.category for Polymarket rows. Search is ILIKE backed by a pg_trgm GIN index on market_groups.title and markets.question; full-text tsvector is deliberate overkill at a bounded catalog of hundreds of rows.

The two load-bearing risks are (1) the UI must never display per-outcome YES prices as a closed probability distribution summing to 100% - they are independent binaries and the live World Cup event summed to 0.45 across 60 outcomes; and (2) the catalog is only as credible as its curation logic - empty category tabs, silent volume double-counting, and tag drift are all demo-killers. Both risks have known mitigations called out in each phase below.

---

## Key Findings

### Recommended Stack

This milestone needs essentially zero new dependencies. The single infrastructure addition is CREATE EXTENSION IF NOT EXISTS pg_trgm in an Alembic migration, enabling GIN-indexed infix ILIKE search on both market_groups.title and markets.question. All other capabilities - async HTTP via httpx, Pydantic v2 parsing, python-slugify for category normalization, Celery + redbeat for sync scheduling, and shadcn/ui primitives for the browse UI - are already locked dependencies.

**Resolved search tension across research files:** STACK.md and ARCHITECTURE.md both recommend pg_trgm GIN + ILIKE; PITFALLS.md warns against unindexed ILIKE. The consensus is **indexed pg_trgm GIN (gin_trgm_ops) + ILIKE**. Full-text tsvector/websearch_to_tsquery is explicitly out - it does not match arbitrary substrings or typos, adds generated-column complexity, and is overkill for a curated catalog of hundreds of rows. External search engines are never appropriate here.

**Core technologies (v1.2 delta only):**
- pg_trgm (Postgres extension, bundled in PG 16): GIN index for infix ILIKE search - the only infra addition; enabled via op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm") in migration 0011
- GammaClient (existing httpx + tenacity): add fetch_events() + fetch_tags() methods; keep fetch_top_markets for back-compat
- Pydantic v2 (existing): new GammaEvent / GammaTag parsers modeled exactly on the spike-002 GammaMarket template (stringified-JSON validators, Decimal discipline, extra policy by env)
- SQLAlchemy 2.0 async (existing): Market.question.ilike(f"%{q}%"), func.similarity, composite index definition - no ORM plugin needed
- Celery + redbeat (existing): poll_polymarket_events replaces poll_polymarket_top25 in the beat schedule; RedBeat SETNX lock pattern reused verbatim
- shadcn/ui (existing): Tabs, Select, Input, Badge, ToggleGroup cover the entire browse + multi-outcome UI

**Critical API notes:**
- Gamma /events rate limit is **500 req/10s** (not the stale "300" comment in client.py, which applies to /markets only)
- Gamma limit ceiling is **500**; hard-coding > 500 or omitting a short-page break silently truncates
- outcomePrices, outcomes, clobTokenIds are **stringified JSON** in every nested market - reuse spike-002 parser verbatim; use string volume/liquidity to Decimal, never the *Num float variants
- GET /events embeds markets[] + tags[] in one call - no N+1 needed for category derivation; groupItemTitle on each nested market is the per-outcome display label

### Expected Features

**Must have (P1 - table stakes for the v1.2 demo):**
- Event entity grouping N binary markets: new market_groups table + nullable Market.group_id FK - foundational, gates everything
- Curated top-N-per-category Gamma sync with volume floor: replaces top-25-global; the "credible" in Credible Catalog
- Category navigation from Gamma tags + suppress empty categories: primary browse mechanic; must never render a tab with 0 items
- Event detail page with per-outcome rows, independent price bars, bet-on-one-outcome (reuses OrderEntryForm)
- Multi-outcome event card (top 2-4 outcomes + %, "+N more") alongside existing binary card
- Text search + status filter + sort (volume / closing / newest) on one extended list endpoint
- Admin create/edit/resolve house multi-outcome event (winner-pick -> existing SettlementService)
- Seed/demo extended with multi-outcome events across categories (open + partially-resolved + void)
- Branding on all new surfaces + explicit empty/zero states per filter

**Should have (P2 - add when P1 core is stable):**
- Combined event chart (overlaid top-outcome price histories) - highest "looks real" visual payoff; reuses PriceHistorySection per child
- Live odds on event rows (WS) with on-screen subscription cap - reuses use-market-socket per child
- Featured "Top events" home shelf + category count chips (e.g. "Politics 12")

**Defer to v2+:**
- Scalar/range markets, heavy pagination/infinite scroll, secondary trading/order book, negRisk/mutually-exclusive auto-balancing, multi-tenant catalogs

**Anti-features (must not build):**
- Single 100%-stacked outcome bar (live data sums to 0.45 for a 60-outcome event - would visibly lie)
- Cross-outcome arbitrage surfacing or "buy all NOs" tooling (invites demo-killing questions)
- Proxying player search to Gamma /public-search (returns full un-mirrored catalog; couples uptime to a third party)
- Ingesting the full Gamma tag firehose as categories (raw /tags includes micro-tags like "caitlin-clark", typo "product-marekt-fit")

### Architecture Approach

The architecture is pure additive layering over the binary core. market_groups is a metadata container - not a bettable entity - so every binary query, bet path, settlement lock, and ledger invariant stays unchanged. A multi-outcome event resolves as a loop of N calls to the proven SettlementService.resolve_market(market_id, winning_outcome_id): the winner child gets its YES outcome settled, all losers get their NO outcome settled. Idempotent replay (Spike 004 property: PENDING filter skips already-settled children) makes partial failure safely retryable without a refactor of the service signature. Event status (open/partial/resolved) is a derived read-model projection - never an authoritative column.

**Major new/modified components:**
1. market_groups table (NEW) + Market.group_id / group_item_title columns (additive nullable) - schema seam; migration 0011_phase13_market_groups; no backfill, no downtime
2. GammaEvent / GammaTag Pydantic schemas (NEW) - siblings of GammaMarket; reuse all spike-002 parser quirks verbatim
3. GammaClient.fetch_events() (MODIFIED) - add method; keep fetch_top_markets for back-compat and tests
4. PolymarketAdapter.sync_events() (MODIFIED) - extract _upsert_one_market(parsed, group_id) from sync_top25; add parent group upsert + group_id stamp; dedup by conditionId / event id
5. poll_polymarket_events Celery task (NEW) - iterates POLYMARKET_CATEGORIES config (~7 curated tag_id entries); applies volume floor client-side; replaces poll_polymarket_top25 in beat schedule
6. EventService (NEW) - house event CRUD + resolve_event orchestration loop + void path (all-children-NO when winning_market_id is None)
7. CatalogService.browse() (NEW) - ILIKE + category + status + sort + LIMIT 100; unifies events + standalone markets
8. New API: GET /catalog, GET /categories, GET /events/{slug}, admin POST/PATCH /admin/events, POST /admin/events/{id}/resolve|reverse
9. New/modified Next.js: catalog-browse, category-nav, modified market-card, event-card, app/events/[slug]/page.tsx, event-outcome-row

**Key indexes (all in migration 0011 - non-optional):**
- market_groups: partial unique (source, source_event_id) WHERE source_event_id IS NOT NULL (idempotent upsert), (category), (status, volume_24hr), GIN pg_trgm(title)
- markets: (group_id), GIN pg_trgm(question)
- odds_snapshots: composite (outcome_id, snapshot_at) - prevents 30-day downsample scan from degrading at 23x row count

### Critical Pitfalls

1. **Per-outcome prices are independent, not a categorical distribution** - render each as an independent YES/NO bar; display-only normalization is acceptable for visual layout but the bet price must always be the true independent YES price. Never implement a 100%-stacked bar or negRisk auto-balancing. Owning phase: Model (lock decision) + Player UI.

2. **Staggered per-leg resolution** - mirrored event constituent markets resolve independently on their own UMA schedules; never gate one leg's settlement on its siblings. House resolution is EventService looping SettlementService per child (per-child transactions, Option A). Event status is derived from child statuses - never an authoritative events.winning_outcome column. Void path is all-children-NO (not a refund; true refund deferred). Owning phase: Model + Settlement.

3. **Never settle on closed=true alone** - carry forward the spike-002 non-negotiable: require closed + umaResolutionStatus="resolved" + clear winner. The event sync path must route through the same guard as the top-25 path. Owning phase: Sync + Settlement.

4. **Gamma /events pagination, rate limits, and dedup** - limit ceiling is 500; stop on short page; dedup by conditionId (market) / event id (group); apply volume floor on de-duplicated basis to avoid the documented Polymarket event-level volume double-counting. Category fan-out sync should run on a slower cadence than the odds poll (minutes, not 30s); keep-last-good on sync failure - never blank the catalog. Owning phase: Sync.

5. **Curated category taxonomy must be pinned to known tag_id values** - not the raw tag firehose. Maintain a version-controlled allow-list of ~7 top-level categories each pinned to a known Gamma tag_id. Log unmapped tags to detect drift. Suppress any category with zero qualifying events. Owning phase: Sync + Seed.

6. **odds_snapshots growth is ~23x** - top-25 to ~140 events x avg 4 child markets x 2 outcomes = ~1,120 rows/5 min vs ~50 today. Composite index (outcome_id, snapshot_at) in migration 0011 is non-optional; a prune/retention task is low-urgency but must be planned for a subsequent phase. Owning phase: Phase 1 (index).

7. **Spike-002 fixtures lack /events and /tags responses** - existing fixtures are single-/markets payloads. Capture fresh GET /events?tag_id=... (with embedded markets[] + tags[]) and GET /tags fixtures before writing parser tests. Owning phase: Sync (fixture capture prerequisite).

---

## Implications for Roadmap

Based on the strict dependency chain (schema gates everything), the build sequence is: **Model -> Sync -> Settlement -> API -> UI -> Seed**.

### Phase 1: Model - market_groups schema + ORM
**Rationale:** Migration 0011 gates every subsequent phase. Zero behavior change; pure additive schema seam. Safe to ship independently.
**Delivers:** market_groups table, nullable Market.group_id + group_item_title columns, all catalog indexes (including pg_trgm extension and odds_snapshots composite index), MarketGroup ORM model + relationship.
**Addresses:** Event entity grouping (foundational feature); catalog index infra for search; odds_snapshots degradation prevention
**Avoids:** group_id IS NULL standalone markets work exactly as today (no backfill); zero behavior change
**Research flag:** Standard Alembic pattern - follow 0004_phase6_polymarket_sync.py exactly. No deeper research needed.

### Phase 2: Sync - Gamma events ingestion + curated catalog
**Rationale:** Mirrored events must exist before settlement, API, or UI can be validated end-to-end. This phase also populates Market.category for the first time on Polymarket rows.
**Delivers:** GammaEvent / GammaTag Pydantic parsers; GammaClient.fetch_events(); PolymarketAdapter.sync_events() + _upsert_one_market() refactor; POLYMARKET_CATEGORIES config (~7 entries, tag_ids pinned from a one-off /tags lookup); poll_polymarket_events task (replaces poll_polymarket_top25 in beat schedule); dedup by conditionId/event id; volume floor; keep-last-good resilience; market_groups rows + grouped children appearing in DB after a sync cycle.
**Implements:** Architecture Pattern 3 (Reuse-the-Upsert); sync data flow
**Avoids:** Tag firehose anti-pattern; pagination ceiling (limit <= 500, short-page stop); volume double-counting (dedup before floor); rate-limit breach (slower curation cadence, minutes not 30s); closed != resolved (same spike-002 guard); blank catalog on failure
**Research flag:** Needs fresh /events + /tags fixture capture before parser tests (spike-002 fixtures lack these). tag_id pinning requires a one-time GET /tags lookup.

### Phase 3: Settlement - house event resolve/void + mirrored auto-verify
**Rationale:** Settlement correctness must be validated before any API or UI surface exercises the full bet lifecycle.
**Delivers:** EventService.resolve_event() (loop SettlementService per child, Option A per-child transactions, idempotent); void path (all-children-NO when winning_market_id is None); group winner/status read-projection (derived only); confirmation that detect_polymarket_resolutions auto-settles mirrored children (zero new code - verify only); admin resolve/reverse endpoints (mirrors existing two-step-confirm + justification pattern).
**Implements:** Architecture Pattern 2 (Settlement-as-a-Loop)
**Avoids:** Authoritative events.winning_outcome column; single giant transaction wrapping all children; event-level settlement bypassing per-market FOR UPDATE; voiding as a refund (scoped as all-NO only, full refund deferred to v2+)
**Research flag:** Standard pattern on Spike 004 primitives. No deeper research needed. Run spike-004 double-entry invariant after every resolution path as acceptance criterion.

### Phase 4: API - catalog/events endpoints + house event CRUD
**Rationale:** API surface must exist before frontend work begins. Provides a testable layer independent of UI.
**Delivers:** CatalogService.browse() (ILIKE + category + status + sort + LIMIT 100); EventService.create_event() / update_event(); catalog_router (GET /catalog, GET /categories, GET /events/{slug}); admin event endpoints (POST/PATCH /admin/events, resolve, reverse); GET /markets kept for back-compat.
**Implements:** Architecture Part 4 (Browse/Search backend)
**Avoids:** Proxying player search to Gamma /public-search; heavy pagination machinery; tsvector FTS (plain ILIKE + pg_trgm GIN is correct at curated scale)
**Research flag:** Standard FastAPI router pattern. No deeper research needed.

### Phase 5: UI - catalog browse + category nav + event detail + admin event ops
**Rationale:** Builds on the complete API layer. Each component independently testable against the live API.
**Delivers:** Modified app/page.tsx to CatalogBrowse; catalog-browse island (search input debounced + category tabs + sort/status select); category-nav horizontal chips; modified market-card (event variant with top 2-4 outcomes + "+N more"); app/events/[slug]/page.tsx (per-outcome rows reusing OrderEntryForm + PriceHistorySection + use-market-socket per child, capped to on-screen rows); event-outcome-row component; admin event create/edit/resolve forms with two-step confirm + justification.
**Implements:** Architecture Part 4 (Catalog UI)
**Avoids:** 100%-stacked outcome bar; WS connection storm (cap subscriptions to visible rows); per-outcome prices displayed as a closed distribution
**Research flag:** Standard Next.js 15 / shadcn patterns. The per-outcome price framing decision (independent bars, no sum-to-100) must be locked as a design spec before implementation begins.

### Phase 6: Seed/Demo - extend harness for multi-outcome events + categories
**Rationale:** Last phase because it exercises every prior phase end-to-end. The seed is the integration acceptance test for the milestone.
**Delivers:** Extended bin/seed_demo.py: >= 1 multi-outcome event per category (3-8 outcomes, plausible per-outcome YES prices), at least one fully-open + one partially-resolved + one fully-resolved + one void event; per-outcome odds history (non-flat charts); every category tab filled above a minimum; featured allow-list insulated from upstream drift; reset command idempotent; double-entry integrity check green.
**Avoids:** Pitfall 9 (shallow demo seed): 2-outcome events only, random YES prices, empty categories, flat charts, no partial/void state
**Research flag:** Standard seeding pattern. Run spike-004 integrity checker as acceptance criterion.

### Phase Ordering Rationale

- Phase 1 gates everything: migration 0011 must exist before any code writes to market_groups or reads group_id
- Phase 2 before 3: mirrored events from sync validate that detect_polymarket_resolutions auto-settles children; house settlement (Phase 3) is independently testable but benefits from real data
- Phase 3 before 4: settlement endpoints are part of the admin API surface
- Phase 4 before 5: frontend builds against a stable API contract
- Phase 6 last: exercises every phase as an integration harness; scheduled intentionally last
- Mirrored auto-resolution is free in Phase 3: detect_polymarket_resolutions already iterates all source=POLYMARKET markets - event children are automatically covered; the Phase 3 task is to verify, not build

### Research Flags

**Phases needing targeted work before or during planning:**
- **Phase 2 (Sync):** Must capture fresh /events?tag_id=... and /tags fixtures before parser tests - spike-002 fixtures are single-/markets only. Also requires a one-time lookup to pin the ~7 curated tag_id values.
- **Phase 5 (UI):** The per-outcome price framing decision (independent bars, no sum-to-100) must be locked as a design spec before implementation begins.

**Phases with standard patterns (skip research-phase during /gsd-plan-phase):**
- Phase 1 (Model): Alembic migration - follow 0004_phase6_polymarket_sync.py exactly
- Phase 3 (Settlement): Orchestration over Spike 004 primitives - well-documented, idempotent loop
- Phase 4 (API): Standard FastAPI router + service pattern already established in the codebase
- Phase 6 (Seed): Extend existing bin/seed_demo.py - established pattern

---

## Watch Out For

| Pitfall | Prevention | Owning Phase |
|---------|------------|--------------|
| Per-outcome YES prices displayed as a closed distribution (sum-to-100) | Independent bars per row; display-only normalization only; lock framing decision before Phase 5 | Phase 1 (lock) + Phase 5 (UI) |
| Staggered resolution: one leg resolves, siblings stay open | Settlement-as-a-loop per child (Option A); event status derived from children, never authoritative column | Phase 3 |
| Settling on closed=true without umaResolutionStatus=resolved | Route event sync through the exact same spike-002 guard, not a new code path | Phase 2 + Phase 3 |
| odds_snapshots 23x growth degrades chart queries | Composite index (outcome_id, snapshot_at) in migration 0011 (non-optional); plan prune task for a later phase | Phase 1 (index) |
| Empty category tabs in the demo | Suppress categories below a minimum qualifying count; hide, do not show empty | Phase 2 (sync floor) + Phase 5 (UI) |
| Tag firehose as categories | Version-controlled allow-list of ~7 tag_ids only; log unmapped tags | Phase 2 |
| Gamma limit > 500 / no short-page stop | Hard cap limit=500; stop loop when page returns < limit rows | Phase 2 |
| Volume double-counting inflating the floor | Dedup by conditionId before applying the volume floor | Phase 2 |
| Spike-002 fixtures lack /events and /tags shapes | Capture fresh fixtures before writing parser tests | Phase 2 |
| WS connection storm on large multi-outcome event pages | Cap subscriptions to on-screen rows; lazy-subscribe | Phase 5 |

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All decisions grounded in real codebase + live Gamma API + Postgres docs. Zero new dependencies confirmed. |
| Features | HIGH | Grounded in Polymarket docs + live /events pull (incl. empirical sum-to-45% proof) + existing XPredict frontend. P2/P3 boundaries are opinionated but well-supported. |
| Architecture | HIGH | Every claim anchored to a named module in backend/app/**. Spike 002 + 004 validate the two load-bearing assumptions (parser quirks; idempotent per-market settlement). |
| Pitfalls | HIGH (integration-specific) / MEDIUM (tag drift over time) | NegRisk mechanics, rate limits, and settlement correctness are high-confidence. Tag drift and search-relevance specifics are MEDIUM (general API behavior). |

**Overall confidence:** HIGH

### Gaps to Address

- **Curated tag_id values:** the specific Gamma tag_id integers for Politics, Sports, Crypto, Pop Culture, Economy, Tech, World must be confirmed via a one-time GET /tags lookup and pinned in config. Phase 2 prerequisite, not a Phase 1 blocker.
- **Single-market events (len(markets) == 1):** ARCHITECTURE.md recommends grouping only when len(markets) >= 2, keeping singletons on the standalone binary path. This is a MEDIUM-confidence recommendation; encode as an explicit acceptance criterion in Phase 2 planning.
- **group_item_title for house events:** admin must supply a per-outcome label when creating a house event. The admin form UX for this is not detailed in FEATURES.md; spec it in Phase 5 planning.
- **Void = all-NO, not a refund:** current scope locks void as every child resolves on its NO outcome (NO bettors win, YES bettors lose). A true cancel-and-refund path does not exist in the current ledger. Document prominently in Phase 3 so the demo script does not promise refunds on void.
- **Demo allow-list / featured flag:** identify and pin the specific categories and events the sales script walks through during Phase 6 planning.

---

## Sources

### Primary (HIGH confidence)
- Real backend code (backend/app/markets/, backend/app/settlement/, backend/app/integrations/polymarket/, backend/alembic/, frontend/src/) - ground truth for every integration point
- XPredict Spike 002 (polymarket-gamma-parser) - parser quirks, closed != resolved guard, groupItemTitle, negRisk field, stringified-JSON discipline
- XPredict Spike 004 (settlement-acid-transaction) - per-market FOR UPDATE to SETTLING to idempotent replay, double-entry invariant, late-bet race
- XPredict Spike 003 (websocket-price-streaming) - per-market channels, scale assumption at 25 markets
- docs.polymarket.com - Gamma /events params, /tags, rate limits (events 500/10s, markets 300/10s, tags 200/10s), Markets and Events concepts, NegRisk overview, how markets resolve (2h challenge window)
- Live gamma-api.polymarket.com (2026-06-04) - GET /events response shape with nested markets[] + tags[]; groupItemTitle; empirical proof YES prices do not sum to 100% (World Cup: 60 outcomes to 0.45; Iran: 17 to 0.96; null prices present); GET /events/pagination to totalResults: 8815; raw /tags noisiness confirmed
- PostgreSQL docs (pgtrgm.html) - gin_trgm_ops accelerates infix LIKE/ILIKE (PG 9.1+); GIN preferred for small result sets; tsvector does not match substrings
- .planning/PROJECT.md - locked v1.2 decisions, out-of-scope boundaries, no heavy pagination, categorias derivadas de tags

### Secondary (MEDIUM confidence)
- AgentBets Gamma API Guide (2026) - rate limits, max limit 500, pagination behavior
- Polymarket Volume Is Being Double-Counted (Paradigm, 2025) - event-level volume double-counting
- Aiven / thoughtbot / pganalyze community guides - pg_trgm GIN is the right index for substring+fuzzy at small scale
- CryptoSlate Polymarket Review 2026 - sort options, card data layout
- PolymarketGuide - outcome structure, mutual exclusivity under negRisk
- Gate.com - arbitrage in Polymarket (sum < 100% as CLOB artifact, informs anti-feature)
- arXiv 2508.03474 - multi-outcome arbitrage, unity-constraint violations
- Smoketrees blog - Postgres FTS + trigram hybrid for short titles

### Tertiary (LOW confidence)
- (none - all findings are grounded in at least MEDIUM-confidence sources)

---
*Research completed: 2026-06-04*
*Ready for roadmap: yes*
