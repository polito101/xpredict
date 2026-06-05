# Requirements: XPredict v1.2 — Credible Catalog

**Defined:** 2026-06-04
**Core Value:** El operador puede ofrecer un catálogo creíble de mercados de predicción (mezcla de Polymarket y house) con liquidación correcta y CRM, todo bajo su marca — sin construir ni operar la pieza técnica.
**Milestone goal:** Replicar fielmente el catálogo de Polymarket — multi-outcome (eventos de binarios) + navegación creíble por categorías con búsqueda/filtros — para que el producto se vea como la referencia real. Sigue play-money y single-tenant.

> Grounded in `.planning/research/SUMMARY.md` (HIGH confidence). Architecture is **additive**: one new `market_groups` table + nullable `Market.group_id` FK; binary model, `SettlementService`, bet/odds/ledger paths unchanged. **Zero new deps** (only the bundled `pg_trgm` extension). Resolves v1.0 `MKT-08` ("multi-outcome deferred to v2").

## v1.2 Requirements

Committed scope (P1 — table stakes). Each maps to a roadmap phase. Categories note the v1.0 category they extend.

### Multi-outcome Events (EVT) — extends MKT/BET; resolves MKT-08

- [x] **EVT-01**: A multi-outcome event groups N independent binary (YES/NO) markets under one event entity (`market_groups` + nullable `Market.group_id`), without changing the binary market or settlement model.
- [ ] **EVT-02**: Player sees an event detail page rendering each outcome as an independent row with its own YES price/odds — never as a single distribution summing to 100%.
- [ ] **EVT-03**: Player can place a bet on a single outcome of an event, reusing the existing bet path on the constituent binary market.
- [ ] **EVT-04**: Player sees a multi-outcome event card in the catalog (top 2–4 outcomes + %, "+N more"), visually distinct from the binary market card.
- [ ] **EVT-05**: Player can see per-outcome price history on the event detail (reuses the existing price-history chart per child market).
- [ ] **EVT-06**: Event status (open / partially-resolved / resolved / void) is derived from its constituent markets' states — never stored as an authoritative winning-outcome column.
- [x] **EVT-07**: A "single-market event" (len == 1) stays on the standalone binary path; grouping applies only to events with ≥ 2 outcomes.

### Curated Catalog & Sync (CAT) — extends MKT sync

- [x] **CAT-01**: System syncs Polymarket via Gamma `GET /events` (embeds `markets[]` + `tags[]`), replacing the top-25-global `/markets` poll.
- [x] **CAT-02**: Catalog is curated as top-N per category with a volume floor (NOT the full active firehose); duplicates removed by `conditionId`/event id **before** applying the floor (avoids Polymarket volume double-counting).
- [x] **CAT-03**: Categories derive from a version-controlled allow-list of ~7 Gamma `tag_id`s (e.g. Politics, Sports, Crypto, Pop Culture, Economy, Tech, World); unmapped tags are logged for drift detection, never auto-added.
- [x] **CAT-04**: Polymarket-mirrored markets get their `category` populated for the first time (today always NULL).
- [x] **CAT-05**: Sync is resilient — keeps the last-good catalog on Gamma failure (never blanks), caps `limit` at 500 with a short-page stop, and runs on a slower cadence than the odds poll.
- [x] **CAT-06**: A category with zero qualifying events is suppressed at the data layer (never surfaced empty).

### Browse & Discovery (BRW) — new

- [ ] **BRW-01**: Player can text-search the catalog by event/market title (indexed substring search via `pg_trgm` GIN + ILIKE).
- [ ] **BRW-02**: Player can browse by category via tabs/chips; empty categories are not rendered.
- [ ] **BRW-03**: Player can filter the catalog by status (open / closing soon / resolved).
- [ ] **BRW-04**: Player can sort the catalog by volume / closing soonest / newest.
- [ ] **BRW-05**: Browse is bounded (curated — no heavy pagination/infinite scroll); every filter combination has an explicit empty/zero state.
- [ ] **BRW-06**: All new catalog / browse / event surfaces respect the operator's white-label branding (`--brand-*`).

### Admin: Event Operations (EVA) — extends ADM/STL

- [ ] **EVA-01**: Admin can create a house multi-outcome event: title, category, and N outcomes each with a per-outcome label (`group_item_title`) and initial odds.
- [ ] **EVA-02**: Admin can edit a house event's outcomes/metadata while it has zero bets; edits lock after the first bet (mirrors ADM-07).
- [ ] **EVA-03**: Admin can resolve a house event by selecting the winning outcome (mandatory justification + two-step confirm); resolution loops the existing `SettlementService` per child (winner→YES settled, losers→NO settled), idempotently.
- [ ] **EVA-04**: Admin can void a house event (no winner): every child resolves on NO (YES bettors lose, NO bettors win) — explicitly NOT a stake refund (true refund-on-cancel is out of scope).
- [ ] **EVA-05**: Admin can reverse an event resolution via compensating ledger entries (mirrors STL-07), audit-logged.
- [ ] **EVA-06**: Mirrored (Polymarket) events are read-only to admins except emergency force-settle (mirrors ADM-06); mirrored children auto-settle via the existing UMA detection (verify, no new settlement code).

### Seed & Demo Harness (DEMO) — extends v1.1 harness

- [ ] **DEMO-01**: The seed creates ≥ 1 multi-outcome event per category, each with 3–8 outcomes and plausible per-outcome YES prices.
- [ ] **DEMO-02**: The seed includes at least one fully-open, one partially-resolved, one fully-resolved, and one void event, each with non-flat per-outcome odds history.
- [ ] **DEMO-03**: Every demo category tab is filled above a minimum (no empty tabs); a featured allow-list of the categories/events the sales script walks is pinned and insulated from upstream tag drift.
- [ ] **DEMO-04**: `demo-reset` is idempotent and the double-entry integrity check passes green after seed and after reset.

## Stretch (P2 — in-scope if time, NOT blocking the milestone)

High "looks-real" payoff; fold into the relevant phase only after its P1 core is stable. All three land in Phase 17 (UI) after its P1 core is stable.

- **P2-01**: Combined event chart — overlaid top-outcome price histories on event detail. *(Phase 17 stretch)*
- **P2-02**: Live odds on event rows via WebSocket, with an on-screen subscription cap (lazy-subscribe — avoids a WS connection storm on 60-outcome events). *(Phase 17 stretch)*
- **P2-03**: Featured "Top events" home shelf + category count chips (e.g. "Politics 12"). *(Phase 17 stretch)*

## Future Requirements

Deferred to a later milestone. Tracked, not in this roadmap.

| Item | Notes |
|------|-------|
| True cancel-and-refund on void | v1.2 void = all-children-NO; a real stake-refund path does not exist in the current ledger. |
| Scalar / range markets | v1.2 is categorical (event-of-binaries) only. |
| Multi-tenancy runtime (MTN) | Single-tenant in v1.2; seams (`tenant_id` ghost, feature-flags) already in place. |
| Real money (RM) — Stripe/KYC/AML | Play-money only; Stripe stub interface ready. **Gated** by Spanish legal review (ToS/token policy) before any live operator demo. |
| Live-bets integration (LB) | `LiveBetsAdapter` against live-bets v3, deferred until that source is available. |

## Out of Scope

Explicitly excluded for v1.2. Documented to prevent scope creep (per research anti-features).

| Feature | Reason |
|---------|--------|
| Single 100%-stacked outcome bar | Live data sums to ~0.45 across 60 outcomes — a stacked bar would visibly lie. Independent bars only. |
| negRisk / mutually-exclusive auto-balancing | Polymarket's CLOB mechanism; play-money has no order book. Outcomes are independent binaries. |
| Cross-outcome arbitrage surfacing / "buy all NOs" tooling | Invites demo-killing questions; not a player capability. |
| Full active-catalog firehose ("todos los activos") | Curated per-category only; long tail of illiquid markets adds noise + heavy sync. |
| Proxying player search to Gamma `/public-search` | Returns un-mirrored markets + couples uptime to a third party. Search local rows only. |
| Heavy pagination / infinite scroll | Curated catalog is bounded; not needed. |
| Secondary trading / order book / cash-out before resolution | Out since v1.0; unchanged. |

## Traceability

Which phases cover which requirements. Populated during roadmap creation (gsd-roadmapper, 2026-06-04). Phases continue the numbered grid from v1.0 (last numbered phase was 12; v1.1 ran off-grid as Fases A–E).

| Requirement | Phase | Status |
|-------------|-------|--------|
| EVT-01 | Phase 13 (Model) | Complete |
| EVT-02 | Phase 17 (UI) | Pending |
| EVT-03 | Phase 17 (UI) | Pending |
| EVT-04 | Phase 17 (UI) | Pending |
| EVT-05 | Phase 17 (UI) | Pending |
| EVT-06 | Phase 15 (Settlement) | Pending |
| EVT-07 | Phase 14 (Sync) | Complete |
| CAT-01 | Phase 14 (Sync) | Complete |
| CAT-02 | Phase 14 (Sync) | Complete |
| CAT-03 | Phase 14 (Sync) | Complete |
| CAT-04 | Phase 14 (Sync) | Complete |
| CAT-05 | Phase 14 (Sync) | Complete |
| CAT-06 | Phase 14 (Sync) | Complete |
| BRW-01 | Phase 16 (API) | Pending |
| BRW-02 | Phase 16 (API) | Pending |
| BRW-03 | Phase 16 (API) | Pending |
| BRW-04 | Phase 16 (API) | Pending |
| BRW-05 | Phase 16 (API) | Pending |
| BRW-06 | Phase 17 (UI) | Pending |
| EVA-01 | Phase 16 (API) | Pending |
| EVA-02 | Phase 16 (API) | Pending |
| EVA-03 | Phase 15 (Settlement) | Pending |
| EVA-04 | Phase 15 (Settlement) | Pending |
| EVA-05 | Phase 15 (Settlement) | Pending |
| EVA-06 | Phase 15 (Settlement) | Pending |
| DEMO-01 | Phase 18 (Seed/Demo) | Pending |
| DEMO-02 | Phase 18 (Seed/Demo) | Pending |
| DEMO-03 | Phase 18 (Seed/Demo) | Pending |
| DEMO-04 | Phase 18 (Seed/Demo) | Pending |

**Coverage:**
- v1.2 P1 requirements: 29 total (EVT 7 · CAT 6 · BRW 6 · EVA 6 · DEMO 4)
- Mapped to phases: 29 ✓ (0 unmapped)
- Stretch (P2): 3 (Phase 17, not counted in coverage)

**Per-phase requirement counts:**
- Phase 13 (Model): 1 — EVT-01
- Phase 14 (Sync): 7 — CAT-01..06, EVT-07
- Phase 15 (Settlement): 5 — EVT-06, EVA-03..06
- Phase 16 (API): 7 — BRW-01..05, EVA-01, EVA-02
- Phase 17 (UI): 6 — EVT-02..05, BRW-06 (+ P2-01..03 stretch)
- Phase 18 (Seed/Demo): 4 — DEMO-01..04

---
*Requirements defined: 2026-06-04*
*Last updated: 2026-06-04 — roadmap traceability populated (Phases 13–18); 29/29 P1 mapped, 0 unmapped.*
