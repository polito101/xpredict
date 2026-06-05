# Roadmap: XPredict

> Compact milestone-grouped view. Full v1.0 detail is archived in
> [`milestones/v1.0-ROADMAP.md`](milestones/v1.0-ROADMAP.md); phase execution history in
> [`milestones/v1.0-phases/`](milestones/v1.0-phases/). See [`MILESTONES.md`](MILESTONES.md) for shipped summaries.

## Milestones

- âœ… **v1.0 MVP** â€” Phases 1-12 (shipped 2026-06-04) â€” production-grade play-money prediction market, end-to-end.
- âœ… **v1.1 Demo Polish** â€” Fases A-E (shipped 2026-06-04) â€” brand-aware design system, seed/demo harness, player & operator polish, demo QA.
- ðŸ“‹ **v1.2 Credible Catalog** â€” Phases 13-18 (planned) â€” multi-outcome events (event-of-binaries) + curated per-category catalog + browse (search/filters/sort). Play-money, single-tenant; additive schema only.

## Phases

<details>
<summary>âœ… v1.0 MVP (Phases 1-12) â€” SHIPPED 2026-06-04</summary>

- [x] **Phase 1: Project Scaffold, Infra & Cross-Cutting Foundations** â€” Docker stack, FastAPI + Next.js, Postgres 16 + Redis, Alembic, money-column standards, `tenant_id` ghost column, audit-log trigger, Sentry, gitleaks CI.
- [x] **Phase 2: Auth & Identity** â€” Player + admin auth (Argon2id / fastapi-users), email verification, password reset, refresh-token rotation, rate-limiting.
- [x] **Phase 3: Wallet & Double-Entry Ledger** â€” Append-only double-entry ledger, `NUMERIC(18,4)`/`Decimal`, `FOR UPDATE` + idempotency, non-negative + non-transferable constraints.
- [x] **Phase 4: Markets Domain & HouseAdapter** â€” `MarketSource` Protocol, house markets CRUD backend, binary YES/NO model.
- [x] **Phase 5: Bets, Settlement & First End-to-End Demo (House Markets Only)** â€” ACID bet placement, `SettlementService`, idempotent settlement, audit trail; first end-to-end demoable happy path.
- [x] **Phase 6: Polymarket Sync (Catalog Replication)** â€” Gamma API polling (Celery Beat + RedBeat lock), top-25 mirror, odds snapshots.
- [x] **Phase 7: Polymarket Auto-Resolution & Admin Override** â€” UMA confirmed-resolved auto-settle with grace window, admin force-settle override.
- [x] **Phase 8: Admin CRM (User Management & Audit Log Viewer)** â€” Paginated users, detail, ban/unban, CSV export, immutable audit log viewer.
- [x] **Phase 9: User App UX Polish (Market Detail & Real-Time)** â€” Market detail, price-history chart, WebSocket real-time prices.
- [x] **Phase 10: Admin KPI Dashboard & Configurable Branding** â€” KPI dashboard (Recharts), audit log filters, single-row TenantConfig branding.
- [x] **Phase 11: Hardening & Operator-Demo Gate** â€” "Looks Done But Isn't" hardening checklist, demo gate.
- [x] **Phase 12: Admin Market Operations UI & Player Resolution Display** â€” v1.0 closure: admin markets list/create/edit/close + resolve/reverse/force-settle dialogs, per-market stake limits (BET-06), player resolution display (STL-06). Closed the open gaps from the 2026-06-02 audit.

</details>

<details>
<summary>âœ… v1.1 Demo Polish (Fases A-E) â€” SHIPPED 2026-06-04</summary>

> Executed off the formal phase grid in parallel git worktrees and landed via PRs (not numbered phases).
> Plan-of-record: [`milestones/v1.1-MILESTONE-CONTEXT.md`](milestones/v1.1-MILESTONE-CONTEXT.md).

- [x] **Fase A: Design system brand-aware** â€” propagate `--brand-*` to primitives (CTAs, links, badges, focus, odds bar, charts) + brand typography (`next/font`) + motion tokens (`framer-motion`). *(PR #22)*
- [x] **Fase B: Seed & demo harness** â€” realistic seed (users, house + mirrored markets, open & resolved, bets with P&L, odds history) + `demo-reset`. *(PR #19)*
- [x] **Fase C: Player polish** â€” header-nav, microinteractions, weighted success states, non-silent errors + loading states, `not-found`/`global-error`, responsive. *(PR #22)*
- [x] **Fase D: Operator polish** â€” admin loading skeletons + responsive tables, panel completeness. *(PR #23)*
- [x] **Fase E: Demo QA / guion** â€” step-by-step sales script + E2E happy-path QA checklist. *(PR #24)*

</details>

### ðŸ“‹ v1.2 Credible Catalog (Phases 13-18) â€” PLANNED

**Milestone Goal:** Faithfully replicate the Polymarket catalog â€” multi-outcome events modeled as groups of independent binary markets (event-of-binaries) plus a credible per-category browse experience (text search, category tabs, status/sort filters) â€” so the product reads as the real reference. Still play-money, still single-tenant. Architecture is **purely additive**: one new `market_groups` table + nullable `Market.group_id`/`group_item_title`; the binary `CHECK`, `SettlementService`, and all bet/odds/ledger paths stay unchanged. **Zero new deps** (only the bundled `pg_trgm` extension). Resolves v1.0 `MKT-08` ("multi-outcome deferred to v2").

**Build sequence (strict dependency chain â€” schema gates everything):** Model â†’ Sync â†’ Settlement â†’ API â†’ UI â†’ Seed. Phase 13's migration `0011_phase13_market_groups` must exist before any code writes `market_groups` / reads `group_id`; API (16) before UI (17); Seed (18) last as the end-to-end integration harness.

- [x] **Phase 13: Multi-outcome Model & Catalog Indexes** â€” `market_groups` table + nullable `Market.group_id`/`group_item_title` + all catalog indexes (`pg_trgm` GIN + `odds_snapshots` composite) in migration 0011; pure additive schema seam, zero behavior change. *(verified 2026-06-05 â€” PR open)*
- [ ] **Phase 14: Curated Per-Category Gamma Sync** â€” Gamma `/events` ingestion replaces the top-25-global poll; top-N-per-category with volume floor, ~7-tag allow-list, dedup, keep-last-good resilience; finally populates `Market.category` on mirrored rows.
- [ ] **Phase 15: Event Settlement (House Resolve/Void + Mirrored Verify)** â€” `EventService` resolve-as-a-loop over the existing `SettlementService` per child; void = all-children-NO; reverse via compensating ledger; derived event status; mirrored children auto-settle via existing UMA detection (verify, no new code).
- [ ] **Phase 16: Catalog & Event API + House Event CRUD** â€” `CatalogService.browse()` (ILIKE + category + status + sort + bounded LIMIT) and event/category/admin-event endpoints; house event create/edit; explicit empty/zero states; `/markets` kept for back-compat.
- [ ] **Phase 17: Catalog Browse UI, Event Detail & Admin Event Ops** â€” Catalog browse island (search + category tabs + status/sort), multi-outcome event card, event detail with independent per-outcome rows/bars + bet-on-one-outcome + per-outcome charts, admin event forms; white-label on every new surface.
- [ ] **Phase 18: Seed/Demo Harness for Multi-outcome + Categories** â€” Extend `bin/seed_demo.py`: â‰¥1 multi-outcome event per category (3-8 outcomes, plausible prices, non-flat history), open + partially-resolved + resolved + void states, filled tabs, pinned featured allow-list; idempotent `demo-reset` with green double-entry integrity check.

## Phase Details

### Phase 13: Multi-outcome Model & Catalog Indexes

**Goal**: The database can represent a multi-outcome event as a group of N independent binary markets, with every catalog/search index in place â€” and existing binary markets behave exactly as before.
**Depends on**: Nothing within v1.2 (builds on the shipped v1.0/v1.1 schema). Gates all of Phases 14-18.
**Requirements**: EVT-01
**Success Criteria** (what must be TRUE):

  1. Migration `0011_phase13_market_groups` applies cleanly and is reversible, creating the `market_groups` table plus nullable `Market.group_id` and `group_item_title` columns â€” with no backfill and no downtime.
  2. An existing standalone (`group_id IS NULL`) binary market is read, bet on, and settled exactly as before the migration â€” zero behavior change.
  3. The migration enables `pg_trgm` (`CREATE EXTENSION IF NOT EXISTS pg_trgm`) and creates the GIN trigram indexes on `market_groups.title` and `markets.question`, the `market_groups` partial-unique `(source, source_event_id) WHERE source_event_id IS NOT NULL`, the `(category)` and `(status, volume_24hr)` indexes, and the `odds_snapshots (outcome_id, snapshot_at)` composite index.
  4. The `MarketGroup` ORM model and its `MarketGroup â†” Market` relationship load via the async session and round-trip a parent group with â‰¥2 children.

**Plans**: 2 plans

- [x] 13-01-PLAN.md â€” Schema + ORM: reversible migration `0011_phase13_market_groups` (table + 2 nullable Market columns + pg_trgm + all 6 indexes) and the `MarketGroup` ORM model + `Market.group` seam
- [x] 13-02-PLAN.md â€” Tests: NEW `test_migration_0011.py` (apply/reversibility/chain/pg_trgm/6 indexes) + extend `test_models.py` (MarketGroup round-trip, `lazy="raise"`, `group_id IS NULL` regression)

### Phase 14: Curated Per-Category Gamma Sync

**Goal**: A sync cycle ingests Polymarket via Gamma `/events` and lands a curated, per-category catalog (mirrored events grouped, children stamped, categories populated) instead of the flat top-25 â€” resiliently and without ever blanking the catalog.
**Depends on**: Phase 13 (writes `market_groups` rows and stamps `group_id`).
**Requirements**: CAT-01, CAT-02, CAT-03, CAT-04, CAT-05, CAT-06, EVT-07
**Success Criteria** (what must be TRUE):

  1. After a sync cycle, `market_groups` rows and their grouped children appear in the DB sourced from Gamma `GET /events` (embedded `markets[]` + `tags[]`); the old `poll_polymarket_top25` is replaced by `poll_polymarket_events` in the beat schedule, on a slower cadence (minutes) than the 30s odds poll.
  2. The catalog is top-N-per-category against a version-controlled allow-list of ~7 Gamma `tag_id`s; duplicates are removed by `conditionId`/event id **before** the volume floor is applied (no Polymarket volume double-counting), `limit` is capped at 500 with a short-page stop, and unmapped tags are logged for drift â€” never auto-added.
  3. Mirrored markets now carry a populated `category` (previously always NULL), and any category with zero qualifying events is suppressed at the data layer (never surfaced empty).
  4. A Gamma fetch failure keeps the last-good catalog (never blanks it), and an event with exactly one constituent market (`len == 1`) stays on the standalone binary path (no group created).**Plans**: 4 plans

**Wave 1**

- [x] 14-01-PLAN.md - Config + parsers: POLYMARKET_CATEGORIES (7 tag_ids) + GammaEvent/GammaTag/GammaEventMarket + resolve_category (CAT-03, parser half of EVT-07)
- [x] 14-02-PLAN.md - GammaClient.fetch_events (ranked /events, 500 cap) + rate-limit docstring fix (CAT-01, CAT-05)

**Wave 2** *(blocked on Wave 1 completion)*

- [ ] 14-03-PLAN.md - Adapter: extract _upsert_one_market + sync_events + _upsert_market_group (first writer of market_groups; CAT-04, EVT-07, CAT-06)

**Wave 3** *(blocked on Wave 2 completion)*

- [ ] 14-04-PLAN.md - Task + beat: poll_polymarket_events curation loop (dedup, floor, top-N, keep-last-good) + beat swap (CAT-01, CAT-02, CAT-03, CAT-05)

### Phase 15: Event Settlement (House Resolve/Void + Mirrored Verify)

**Goal**: A multi-outcome event settles correctly and idempotently by looping the proven per-market `SettlementService`, with void/reverse paths and a derived status â€” and mirrored event children auto-settle with no new settlement code.
**Depends on**: Phase 13 (group model); benefits from Phase 14 real data for mirrored verification.
**Requirements**: EVT-06, EVA-03, EVA-04, EVA-05, EVA-06
**Success Criteria** (what must be TRUE):

  1. Resolving a house event by winning outcome settles every child via `SettlementService` (winnerâ†’YES settled, losersâ†’NO settled) as per-child transactions (Option A), and re-running the resolution is a safe no-op (idempotent replay) â€” the spike-004 double-entry integrity check passes green after every resolution path.
  2. Voiding a house event resolves every child on NO (YES bettors lose, NO bettors win) â€” explicitly NOT a stake refund â€” and a resolution can be reversed via compensating ledger entries (mirrors STL-07), audit-logged.
  3. Event status (open / partially-resolved / resolved / void) is computed as a read-projection derived from the constituent markets' states â€” there is no authoritative `winning_outcome` column on the group; settlement never routes through `closed=true` alone (still requires the spike-002 `closed` + `umaResolutionStatus="resolved"` + clear-winner guard).
  4. Mirrored (Polymarket) event children auto-settle through the existing `detect_polymarket_resolutions` path (verified, not rebuilt), and mirrored events stay admin-read-only except the existing emergency force-settle (mirrors ADM-06).

**Plans**: TBD

### Phase 16: Catalog & Event API + House Event CRUD

**Goal**: A stable HTTP contract exposes browse/search/category/event reads and house-event create/edit/resolve/reverse â€” testable independently of any UI â€” with every filter combination returning an explicit, bounded result.
**Depends on**: Phase 15 (resolve/reverse endpoints are part of the admin event API surface).
**Requirements**: BRW-01, BRW-02, BRW-03, BRW-04, BRW-05, EVA-01, EVA-02
**Success Criteria** (what must be TRUE):

  1. `GET /catalog` returns a bounded result (curated, `LIMIT 100`, no heavy pagination/infinite scroll) and supports indexed text search (`pg_trgm` GIN + ILIKE on local rows only â€” never proxied to Gamma `/public-search`), category filter, status filter (open / closing soon / resolved), and sort (volume / closing soonest / newest); every filter combination yields an explicit empty/zero result rather than an error.
  2. `GET /categories` lists only non-empty categories and `GET /events/{slug}` returns an event with its per-outcome child markets and prices.
  3. An admin can create a house multi-outcome event (title, category, N outcomes each with a `group_item_title` label + initial odds) via `POST /admin/events`, and edit its outcomes/metadata via `PATCH` only while it has zero bets â€” edits lock after the first bet (mirrors ADM-07).
  4. The admin resolve/reverse endpoints enforce mandatory justification + a two-step confirm (mirroring the existing market pattern), and the legacy `GET /markets` endpoint still works for back-compat.

**Plans**: TBD

### Phase 17: Catalog Browse UI, Event Detail & Admin Event Ops

**Goal**: Players browse a credible curated catalog and bet on individual outcomes of a multi-outcome event through independent per-outcome rows, and admins operate house events end-to-end â€” all under the operator's brand and without ever lying about probabilities.
**Depends on**: Phase 16 (builds against the stable API contract).
**Requirements**: EVT-02, EVT-03, EVT-04, EVT-05, BRW-06
**Success Criteria** (what must be TRUE):

  1. A player can search the catalog (debounced input), switch categories via tabs/chips (empty categories never render), and apply status/sort controls â€” with a visible empty state for any zero-result combination.
  2. A player sees a multi-outcome event card (top 2-4 outcomes + %, "+N more"), visually distinct from the binary market card, and opens an event detail page that renders each outcome as an independent row with its own YES price/odds â€” never a single bar summing to 100%.
  3. A player can place a bet on a single outcome (reusing `OrderEntryForm` against the constituent binary market) and view per-outcome price history (reusing the existing chart per child); live-price WebSocket subscriptions are capped to on-screen rows (no connection storm on large events).
  4. Admin event create/edit/resolve forms work with per-outcome `group_item_title` labels + two-step confirm + justification, and every new catalog / browse / event surface respects the operator's `--brand-*` white-label tokens.

**Plans**: TBD
**UI hint**: yes

> **Pre-implementation design lock (research flag):** before Phase 17 build begins, the per-outcome price framing (independent YES/NO bars, display-only normalization at most, never sum-to-100) must be locked as a design spec. The admin per-outcome-label (`group_item_title`) form UX is also specced here.
> **Stretch (P2 â€” only after the P1 core above is stable; non-blocking):** P2-01 combined event chart (overlaid top-outcome histories), P2-02 live odds on event rows via WebSocket with an on-screen subscription cap, P2-03 featured "Top events" home shelf + category count chips.

### Phase 18: Seed/Demo Harness for Multi-outcome + Categories

**Goal**: One command seeds a credible multi-outcome demo across every category and every event state, and the reset is idempotent with a green integrity check â€” exercising every prior phase as the milestone's integration acceptance test.
**Depends on**: Phases 13-17 (exercises model, sync, settlement, API, and UI end-to-end).
**Requirements**: DEMO-01, DEMO-02, DEMO-03, DEMO-04
**Success Criteria** (what must be TRUE):

  1. The seed creates â‰¥1 multi-outcome event per category, each with 3-8 outcomes and plausible per-outcome YES prices, plus non-flat per-outcome odds history for the charts.
  2. The seed includes at least one fully-open, one partially-resolved, one fully-resolved, and one void event, so every event-status state is demonstrable.
  3. Every demo category tab is filled above a minimum (no empty tabs), and the specific categories/events the sales script walks are pinned via a featured allow-list insulated from upstream tag drift.
  4. `demo-reset` is idempotent, and the spike-004 double-entry integrity check passes green after both seed and reset.

**Plans**: TBD

## Progress

**Execution Order:** Phases execute in numeric order: 13 â†’ 14 â†’ 15 â†’ 16 â†’ 17 â†’ 18 (decimal insertions, if any, slot between their surrounding integers).

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1-12. v1.0 MVP | v1.0 | 44/44 | âœ… Complete | 2026-06-04 |
| A-E. Demo Polish | v1.1 | â€” | âœ… Complete | 2026-06-04 |
| 13. Multi-outcome Model & Catalog Indexes | v1.2 | 2/2 | âœ… Complete | 2026-06-05 |
| 14. Curated Per-Category Gamma Sync | v1.2 | 2/4 | In Progress|  |
| 15. Event Settlement (House Resolve/Void + Mirrored Verify) | v1.2 | 0/TBD | Not started | - |
| 16. Catalog & Event API + House Event CRUD | v1.2 | 0/TBD | Not started | - |
| 17. Catalog Browse UI, Event Detail & Admin Event Ops | v1.2 | 0/TBD | Not started | - |
| 18. Seed/Demo Harness for Multi-outcome + Categories | v1.2 | 0/TBD | Not started | - |

**Known deferred at v1.0/v1.1 close** (carried into v1.2): 3 human-UAT scenarios + 3 verification gaps from Phase 12, and the **non-deferrable Spanish legal review** of ToS/token policy before any live operator demo (see [`STATE.md`](STATE.md) â€º Deferred Items).
