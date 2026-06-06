# Phase 18: Seed/Demo Harness for Multi-outcome + Categories - Context

**Gathered:** 2026-06-06
**Status:** Ready for planning
**Mode:** Autonomous smart-discuss (grey areas decided + documented; no user pause per the run directive)

<domain>
## Phase Boundary

Extend `backend/bin/seed_demo.py` (the v1.1 Demo Polish harness) so one command seeds a
**credible multi-outcome demo** across every category and every event state, exercising the
whole v1.2 stack (model → sync → settlement → API → UI) as the milestone's integration
acceptance test. Requirements **DEMO-01..04**:

- **DEMO-01** — ≥1 multi-outcome event per category, each 3–8 outcomes, plausible per-outcome YES prices.
- **DEMO-02** — ≥1 fully-open, ≥1 partially-resolved, ≥1 fully-resolved, ≥1 void event, each with non-flat per-outcome odds history.
- **DEMO-03** — every demo category tab filled above a minimum (no empty tabs); a featured allow-list pinned, insulated from upstream tag drift.
- **DEMO-04** — `demo-reset` idempotent; the spike-004 double-entry integrity check is green after seed AND after reset.

**Backend/seed phase only — zero frontend changes.** The Phase-17 UI already renders categories
from `GET /categories` and events from `GET /catalog`; this phase only produces the data they read.
**Build entirely on the merged service layer** (`EventService.create_house_event` / `resolve_event`
/ `void_event`, `SettlementService.resolve_market`, `WalletService`, `BetService`) — no new domain
code, no schema change beyond the reset-table fix below.
</domain>

<decisions>
## Implementation Decisions (grey areas — decided autonomously)

### D1 — Events created through the real service layer, never hand-rolled rows
`seed_events` calls `EventService.create_house_event(session, admin_id, CreateEventRequest(...))`
(one fresh session per event — it commits once internally, mirroring the existing per-call session
discipline). Resolution uses `EventService.resolve_event` / `void_event` (they open their own
per-child sessions). This keeps the money/audit invariants intact and makes the seed a genuine
end-to-end exercise of Phases 15–16 (the milestone-integration intent). **Rationale:** money
discipline + "no shortcuts" > convenience.

### D2 — Partially-resolved state via a single-child `SettlementService.resolve_market`
`EventService` exposes only all-or-nothing resolve/void. To produce a genuine `partially_resolved`
derived status (≥1 child RESOLVED, ≥1 OPEN) through the **real ledger path**, `seed_event_resolutions`
settles exactly ONE child of the partial event via `SettlementService.resolve_market` (a fresh
session — the same call the existing standalone resolution already uses), leaving the rest OPEN.
This is ledger-correct (identical to what `EventService` does internally per child) and reconciles green.

### D3 — `market_groups` ADDED to the reset truncate set (idempotency fix)
`_RESET_TABLES` currently omits `market_groups`. Since `markets.group_id → market_groups.id`
(the FK points markets→groups), `TRUNCATE markets … CASCADE` does NOT clear `market_groups`;
re-seeding deterministic group slugs would then hit the `market_groups.slug` UNIQUE constraint.
Phase 18 is the first seed to write `market_groups`, so this is the correct place to add it to
`_RESET_TABLES`. **Required for DEMO-04 idempotency.**

### D4 — Featured allow-list = the 7 canonical category names, pinned + coherence-guarded
The demo seeds exactly ONE marquee multi-outcome house event per canonical category
(**Politics, Sports, Crypto, Pop Culture, Economy, Tech, World** — the `POLYMARKET_CATEGORIES`
allow-list, `app/core/config.py`). The featured set is **hardcoded** in the seed (pinned →
insulated from upstream Gamma tag drift; the marquee events are house events, never synced). A
runtime guard `_assert_featured_categories_match_canonical()` asserts the seed's featured set ==
`{e.name for e in settings.POLYMARKET_CATEGORIES}` so the pin can never silently drift out of
alignment with the catalog's category vocabulary.

### D5 — Retag existing standalone templates to canonical categories
The v1.1 standalone `_MARKET_TEMPLATES` used some non-canonical category strings (Space, Climate,
Entertainment, Commodities, Finance). Retag them onto the canonical 7 (Space→World, Climate→World,
Entertainment→Pop Culture, Commodities→Economy, Finance→Economy) so the entire demo catalog reads in
exactly the 7 canonical tabs (no stray tabs), and every featured tab clears the minimum (event +
standalone markets). **Rationale:** a "credible catalog" demo should mirror the canonical 7;
small, cosmetic, money-neutral change.

### D6 — "Above a minimum" = ≥2 catalog items per featured category
Operationalize DEMO-03's "filled above a minimum" as `MIN_ITEMS_PER_FEATURED_CATEGORY = 2`
(the marquee event + ≥1 standalone market). The default seed (`n_markets=15`, `n_events=7`, post-retag)
satisfies this for all 7 — asserted in a test.

### D7 — Integrity self-check surfaced, asserted baseline-relative in tests
`verify_integrity()` wraps `app.wallet.reconcile._reconcile_async` and the CLI prints
`integrity: accounts=N drift=M` after both seed and reset. Tests assert **baseline-relative**
(`after["drift_count"] == baseline["drift_count"]`) — the repo idiom robust to drift other
integration tests leak into the shared session-scoped container.

### D8 — `n_events` parameterizes events; existing tests pinned to `n_events=0`
`SeedConfig` gains `n_events: int = 7` (full demo by default). The 3 pre-existing seed tests get
`n_events=0` to stay standalone-focused/fast; new event tests drive the event paths. Event templates
are ordered so the first four cover all four states (resolved, partial, void, open) — a small
`n_events` still exercises every state.

### D9 — Makefile convenience targets `seed` / `demo-reset`
Repoint the stale `seed` target at the real seed and add a `demo-reset` target
(`uv run python bin/seed_demo.py --reset`) — names "demo-reset" explicitly (DEMO-04) for POSIX users;
Windows users keep `bin/dev.ps1`.
</decisions>

<code_context>
## Existing Code Insights (verified by read, this session)

- **`EventService.create_house_event(session, *, admin_id, body: CreateEventRequest) -> MarketGroup`**
  (`app/settlement/event_service.py:634`) — group slug-retry (`begin_nested`), N children via
  `_add_event_child` (YES@initial_odds + NO@1−odds), one `event.created` audit, **commits once**,
  returns reloaded group. `CreateEventRequest`: title, category, deadline (future), resolution_criteria,
  slug, outcomes[≥2] (`OutcomeInput`: label, initial_odds ∈ (0,1)) — `event_schemas.py:41`.
- **`resolve_event(*, group_id, winning_outcome_id, justification, actor_user_id) -> EventSettleResult`**
  / **`void_event(*, group_id, justification, actor_user_id)`** (`event_service.py:217/327`) — open their
  OWN per-child fresh sessions (the 23505 landmine). `resolve_event` requires `winning_outcome_id` be the
  winner child's **YES** outcome (CR-01 guard).
- **`derive_event_status(children) -> {"open","partially_resolved","resolved","void"}`** (`event_service.py:105`, pure).
- **`SettlementService.resolve_market(session, *, market_id, winning_outcome_id, market_resolver, justification, actor_user_id)`**
  (`app/settlement/service.py:84`) + `HouseMarketResolveAdapter` — the existing standalone resolution path; reused for the single partial child.
- **`CatalogService.list_categories(session) -> list[str]`** / **`list_catalog(session, *, q, category, status, sort)`**
  (`app/catalog/service.py:291/201`) — category surfaces if ≥1 group has it (no status filter) → seeding ≥1 event per category fills the tab (CAT-06).
- **`app.wallet.reconcile._reconcile_async(session=None) -> {"accounts_checked","drift_count"}`**
  (`app/wallet/reconcile.py:61`) — house_promo excluded; GREEN = drift 0.
- **Seed spine** (`bin/seed_demo.py`): Bloques users→markets→odds→bets→resolutions→reset→CLI;
  session-per-call for self-committing services; `SeededMarket` carries id/slug/yes_outcome_id/no_outcome_id/initial_odds_yes
  (event children reuse this shape → `seed_odds_history` works on the combined list unchanged).
- **`tests/seed/test_seed_demo_e2e.py`** exists (testcontainers + `alembic upgrade head` via parent `engine` fixture; `pytest.mark.integration` + asyncio session loop). Extend it.
</code_context>

<specifics>
## Specific Ideas

- 7 marquee events (ordered so the first four cover all states):
  1. **Politics** — "Which party controls the Senate after the next election?" (3–4 outcomes) → **resolved**
  2. **Sports** — "Which club wins the Champions League?" (6 outcomes) → **partially_resolved** (one eliminated club's child settled NO)
  3. **Economy** — "Which quarter does the central bank first cut rates?" (4 outcomes) → **void** (scenario withdrawn — all children NO)
  4. **Crypto** — "Which asset posts the highest yearly return?" (5 outcomes) → **open**
  5. **Pop Culture** — "Who wins Album of the Year?" (5 outcomes) → **open**
  6. **Tech** — "Which lab ships the next frontier model first?" (5 outcomes) → **open**
  7. **World** — "Which city hosts the 2036 Summer Olympics?" (4 outcomes) → **open**
- Per-outcome YES prices are **independent** (event-of-binaries — never sum-to-100; the framing LOCK).
- Deterministic group slugs `demo-evt-{NN}-{category-slug}` for stable demo URLs (clean DB after the guard/reset → no collision).
- Event bets: a small deterministic both-sides spread per child so resolved/void/partial events show winners AND losers.
</specifics>

<deferred>
## Deferred Ideas

- A dedicated admin event-list endpoint (Phase 17 follow-up) — not needed by the seed.
- True cancel-and-refund on void (out of scope for v1.2; void = all-children-NO).
- Parameterizing odds-history density per call — module constants are fine for the demo.
</deferred>
