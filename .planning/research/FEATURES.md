# Feature Research

**Domain:** White-label play-money prediction market — v1.2 "Credible Catalog" DELTA (multi-outcome events-of-binaries + curated category catalog). Mirrors Polymarket presentation.
**Researched:** 2026-06-04
**Confidence:** HIGH (Polymarket docs + live Gamma API `/events` sample + existing XPredict frontend grounded; only live-site DOM details are MEDIUM since polymarket.com blocks scraping)

> Scope note: This file covers ONLY the v1.2 delta. Binary YES/NO markets, MarketSource Protocol, Gamma sync, UMA auto-resolution, wallet/ACID bets, settlement, auth, admin CRM, KPI dashboard, branding, real-time WS prices, price-history chart, and the seed/demo harness are SHIPPED and treated as given. "Existing" in the dependency notes refers to these.

## How Polymarket Actually Models & Presents This (grounded reference)

Confirmed against [Polymarket Markets & Events docs](https://docs.polymarket.com/concepts/markets-events) and a **live `gamma-api.polymarket.com/events` pull (2026-06-04)**:

- **Hierarchy:** `Event` (container) → 1..N `Market`s → each Market is a **binary `["Yes","No"]` pair**. This is exactly the v1.2 LOCKED "event-of-binaries" model. A single binary question is just an event with one market.
- **Per-outcome label** lives in `market.groupItemTitle` (e.g. `"Spain"`, `"France"`, `"June 30"`), NOT in the `outcomes` array (which stays `["Yes","No"]`). The event `title` is the question ("World Cup Winner"); the rows are the candidates.
- **Prices are stringified JSON** (`outcomePrices: '["0.1595","0.8405"]'`) — same parsing discipline as Spike 002 (`json.loads`, → `Decimal`, use string `volume` not `volumeNum`).
- **CRITICAL — prices DO NOT sum to 100%.** Live "World Cup Winner" event = **60 outcomes, YES prices summed to 0.45** (most teams at \$0.00–\$0.01). "US x Iran peace deal" = 17 outcomes summing to 0.96. Some markets returned `outcomePrices: None` (no liquidity yet). Resolved-but-still-listed sub-markets show `["0","1"]`. **The UI must render each outcome as an independent bar/percentage; it must NEVER show a single 100%-stacked bar across outcomes, and must tolerate null/zero prices.** (See Anti-Features.)
- **Why Polymarket's *featured* multi-candidate sets look ~100%:** the `negRisk` / `enableNegRisk` mechanism (a CLOB/AMM "negative-risk" construct that lets traders convert a basket of NO shares). XPredict is play-money with no order book → this is **out of scope** and must NOT be replicated. Independent binaries that don't sum to 100% are the correct, honest model.
- **Categories = tags.** Each event carries `tags: [{label,...}]` (e.g. `Soccer`, `Sports`, `FIFA World Cup`). Polymarket's top-level nav categories are Politics, Sports, Crypto, Geopolitics, Economy, Tech, Culture, etc. ([predictions pages](https://polymarket.com/predictions)). v1.2's "categories from Gamma tags" maps directly.
- **Catalog UX (live site):** category tabs/chips across the top, a search bar, and a card grid sortable by **Trending / Volume / Liquidity / Newest / Ending soon** ([Polymarket review](https://cryptoslate.com/prediction-markets/polymarket-review/), [predictions/all](https://polymarket.com/predictions/all)). Cards show title, top outcome(s) + %, 24h/total volume, and an icon/image. Multi-outcome event cards show a **mini list of the top 2–4 outcomes with their %** (not a single YES/NO bar).
- **Event-page row UX:** each outcome is a row — name + implied % + (on the featured layout) a per-row **Buy Yes / Buy No** affordance, with a single combined chart at the top of the event for the headline outcomes. Each outcome trades independently with its own price ([Markets & Events docs](https://docs.polymarket.com/concepts/markets-events), [PolymarketGuide outcomes](https://polymarketguide.gitbook.io/polymarketguide/markets/structure/outcomes)).

**What XPredict already has to extend (from the codebase):** a flat `MarketCard` (YES/NO `OddsDisplay` bar + volume + deadline + `SourceBadge`), a `MarketList` server component hitting `GET /api/v1/markets` (no search/filter/sort params), a `markets/[slug]` detail with sticky order-entry + live-odds socket + price-history + activity, and a home `page.tsx` that is just `<h1>Markets</h1>` + the list. There is **no `/events` route, no category nav, no search/sort UI** today.

---

## Feature Landscape

### Table Stakes (Users Expect These)

Missing these makes the catalog feel *less* credible than Polymarket — which directly defeats a sales demo whose job is "look like the real thing."

| Feature | Why Expected | Complexity | Notes / Dependencies |
|---------|--------------|------------|----------------------|
| **Event entity grouping N binary markets** | The entire v1.2 thesis; Polymarket's native model. | MEDIUM (BE) | New `Event` table + `market.event_id` FK; **reuses existing binary market/settlement untouched**. Single-question markets = event with 1 market (or "standalone"). |
| **Event detail page: per-outcome rows (label, %, bet affordance)** | This is what a multi-outcome market *is* to a user. | MEDIUM (FE) | Extend `markets/[slug]` pattern into `/events/[slug]`. Each row = one existing binary market; clicking a row → bet on THAT outcome's YES (reuse `OrderEntryForm`). |
| **Per-outcome independent price bar (NOT summed to 100%)** | Polymarket shows independent implied probs; honesty + matches source. | LOW (FE) | Reuse `OddsDisplay` per row. **Do not normalize across outcomes.** Handle null/0.00 prices gracefully (see anti-features). |
| **Bet on a single chosen outcome** | Core action of a multi-outcome market. | LOW (reuse) | The chosen outcome IS a binary market → existing bet/wallet/settlement path applies with zero new financial logic. |
| **Multi-outcome event card (top 2–4 outcomes + %)** | Catalog scanability; cards must distinguish events from binaries. | MEDIUM (FE) | New card variant alongside `MarketCard`; show leading outcomes by price, "+N more". |
| **Category navigation (tabs/chips from Gamma tags)** | Primary way users browse a bigger catalog; Polymarket-defining. | MEDIUM (BE+FE) | Tag→category mapping on sync; category filter on list endpoint. Curated set (Politics/Sports/Crypto/…); **suppress empty categories** (anti-feature). |
| **Text search (title/question)** | Expected the instant a catalog exceeds ~25 items. | LOW–MEDIUM (BE+FE) | `ILIKE`/`pg_trgm` over event title + market `groupItemTitle`; debounced input. No full-text infra needed at this scale. |
| **Status filter (Open / Resolved / Closing soon)** | Users expect to hide dead markets; trust signal. | LOW (BE+FE) | Reuse existing market status; filter param on list endpoint. |
| **Sort (Volume / Closing / Newest)** | Polymarket's exact sort affordances; "show me the action." | LOW (BE+FE) | `order_by` param. Volume already on `MarketItem.volume`/`volume_24hr`. |
| **Event-level aggregate volume on cards/detail** | Users judge "is this live?" by volume. | LOW (BE) | Sum constituent markets' volume; Gamma `event.volume` already provides this for mirrored events. |
| **Curated top-N-per-category sync (volume floor)** | Replaces global top-25; the "credible catalog" mechanic itself. | MEDIUM (BE) | Extend existing Gamma sync to iterate tags, take top-N each with a min-volume floor. **Floor is the quality gate** that keeps illiquid noise out. |
| **Admin: create/edit a house multi-outcome event** | Operator must add own events; parity with existing house binary CRUD. | MEDIUM (BE+FE) | Extend existing house-market admin: "event" wrapper + add N outcomes (each spawns a binary market). |
| **Admin: resolve a house event = pick winning outcome → settle binaries** | Closes the loop; reuses existing settlement. | MEDIUM (BE+FE) | "Pick winner" sets the winning outcome's binary → YES, all others → NO, then existing `SettlementService` runs each. Reuse the existing two-step confirm + justification UI. |
| **Seed/demo: populate multi-outcome events across categories** | The demo *is* the product; harness must showcase the new shape. | MEDIUM | Extend v1.1 harness: ≥1 rich multi-outcome event (e.g. mock election/world-cup) per showcased category, mix of open/resolved. |
| **Breadcrumb / event↔outcome navigation** | Users need to get from event → outcome detail → back. | LOW (FE) | Event page links to per-outcome chart/detail; outcome links back to its event. |
| **Empty/zero-state per filter & per category** | Bigger catalog = more ways to hit "no results"; silent empty = looks broken. | LOW (FE) | Reuse existing empty-state pattern from `MarketList`; per-filter copy. |

### Differentiators (Competitive Advantage for a SALES demo)

Not required, but they make the demo *sell* — they signal "production-grade white-label," which is the Core Value. Keep each cheap; this is a demo, not a Polymarket clone.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Fully branded catalog surface** | "It's *their* product." Categories/cards/event pages inherit `--brand-*` + brand font/motion. | LOW (reuse) | v1.1 already propagates branding to player surface; just extend to new components. Cheap, high sales impact. |
| **Combined event chart (headline outcomes overlaid)** | The single most "Polymarket-like" visual; instantly recognizable in a live demo. | MEDIUM (FE) | Reuse `price-history` infra; overlay top 2–4 outcomes' YES history on one chart. Cap series count to stay readable. |
| **"Trending" sort (24h volume)** | Makes the catalog feel alive on stage. | LOW (BE) | `volume_24hr` already synced; one more sort option. |
| **Featured / curated home shelf ("Top events this week")** | A credible landing for a bigger catalog beats a flat grid; great demo opener. | LOW–MEDIUM (FE) | Curated rail of high-volume events above the grid. Mirrors Polymarket's hero carousel without building a real carousel engine. |
| **Category + count chips ("Politics · 12")** | Signals catalog depth at a glance; reassures buyer it's not empty. | LOW (BE+FE) | Counts from the same curated sync. Only render non-zero categories. |
| **Live odds on event rows (WS)** | The existing socket already does this for binaries; extending to event rows makes the demo feel real-time across the board. | MEDIUM (FE) | Reuse `use-market-socket`; subscribe per visible outcome. Watch fan-out cost on 60-outcome events → cap subscriptions to on-screen rows. |
| **Resolution transparency on events** | Existing "Resolution criteria always visible" trust signal, carried to events. | LOW (reuse) | Show per-outcome resolution criteria/source; reuse existing panel. Differentiates from a toy demo. |

### Anti-Features (Look right, but hurt a play-money sales demo)

These are the traps the quality gate flags. Each would make the demo look *worse* or invite awkward questions.

| Feature | Why Requested | Why Problematic (for THIS demo) | Alternative |
|---------|---------------|----------------------------------|-------------|
| **Single 100%-stacked outcome bar across an event** | Looks tidy; many bookmaker UIs do it. | XPredict prices are independent binaries that **don't sum to 100%** (live World Cup event summed to 0.45). A 100% bar would be a lie and would visibly break. | Independent per-outcome bars/%, exactly like Polymarket's candidate rows. |
| **Exposing/surfacing cross-outcome arbitrage** (e.g. "buy all NOs", "sum < 100% → free money" hints) | "Power-user" feel. | Invites the buyer to notice that play-money "odds" are mechanically exploitable; turns a sales demo into a debate about market-maker correctness. [Arb is a real Polymarket phenomenon](https://www.gate.com/learn/articles/the-quiet-arbitrageurs-making-fortunes-on-polymarket/12914) but it's a CLOB artifact. | Present odds as implied probabilities only. No basket/portfolio-arb tooling. |
| **`negRisk` / mutually-exclusive auto-balancing engine** | Makes candidate sets sum to ~100% like Polymarket's featured markets. | It's a CLOB/AMM mechanism; XPredict has no order book. Building it = large financial complexity for zero demo value, and contradicts play-money simplicity. | Keep independent binaries. Accept that sums ≠ 100% (it's honest and matches the raw Gamma data). |
| **Full firehose catalog ("all active markets")** | "More = more credible." | Already OUT per PROJECT.md. The illiquid long tail adds noise, ugly \$0-volume cards, heavy sync, and empty categories — all of which make the demo look *less* curated. | Curated top-N-per-category + volume floor (the v1.2 plan). |
| **Empty/near-empty category tabs** | "Show every category Polymarket has." | A tab that opens to 0–1 markets screams "incomplete." Worst possible look in a sales demo. | Only render categories that clear the volume floor with ≥N events. Hide the rest. |
| **Heavy pagination / infinite scroll** | "Real catalogs paginate." | Already OUT ("no heavy pagination"). At curated scale (dozens, not thousands) it's unneeded ceremony; infinite scroll also breaks SSR simplicity and demo determinism. | Single curated grid per category/filter; optional "show more" within a long event's outcomes only. |
| **Secondary trading / sell-a-position / order book per outcome** | "Polymarket lets you sell." | Explicitly OUT (no orderbook). Multiplies financial logic; not what the demo sells. | Simple bet-at-current-price on the chosen outcome (existing path). |
| **Scalar/range outcome UI (slider/number line)** | World-cup-style numeric markets exist on Polymarket. | Explicitly OUT for v1.2 (categorical only). The live "Knicks/Spurs spread" event (112 spread markets) is exactly the noise to *exclude*, not render. | Categorical events-of-binaries only; filter spread/scalar-style mega-events out of the curated sync. |
| **Live updating of all 60 outcomes via WS at once** | "Everything real-time." | A 60-outcome event (real, from live data) would open 60 socket subscriptions → fan-out cost, jank, and a fragile live demo. | Subscribe only to on-screen/top-N outcomes; lazy-subscribe on scroll. |
| **Admin free-form "number of outcomes" with no guardrails** | Flexibility. | An operator could create a 50-outcome house event that looks broken and is unsettleable cleanly. | Cap house-event outcomes (e.g. ≤ ~12) in the admin form; mutually-exclusive winner-pick resolution assumes a sane N. |

---

## Feature Dependencies

```
[Event entity (N binary markets)]                         <- foundational; everything below needs it
    ├──requires──> [Existing binary market + settlement]  (SHIPPED, reused unchanged)
    │
    ├──> [Event detail page: per-outcome rows]
    │        ├──requires──> [Per-outcome independent price bar]
    │        ├──enhanced-by──> [Combined event chart]      (reuses SHIPPED price-history)
    │        └──enhanced-by──> [Live odds on event rows]   (reuses SHIPPED use-market-socket)
    │
    ├──> [Multi-outcome event card]
    │        └──feeds──> [Catalog grid]
    │
    └──> [Admin: create/edit house event]
             └──> [Admin: resolve event = pick winner → settle binaries]  (reuses SHIPPED SettlementService)

[Curated top-N-per-category sync (volume floor)]           <- extends SHIPPED Gamma sync
    ├──produces──> [Category nav (tags→categories)]
    │                  └──requires──> [Suppress empty categories]
    ├──produces──> [Category + count chips]
    └──feeds──> [Catalog grid] ──needs──> [Search] + [Status filter] + [Sort]

[Branding (SHIPPED)] ──enhances──> [all new player surfaces]
[Seed/demo harness (SHIPPED)] ──must-be-extended-for──> [multi-outcome events + categories]

[Per-outcome independent bar]  ──conflicts──>  [Single 100%-stacked event bar]   (pick the former)
[Independent binaries]         ──conflicts──>  [negRisk auto-balancing]           (pick the former)
[Curated catalog + volume floor] ──conflicts──> [Full firehose / empty categories] (pick the former)
```

### Dependency Notes

- **Event entity requires existing binary market + settlement:** an outcome *is* a binary market. This is the whole reason v1.2 is cheap — no new financial logic, no new settlement path. Resolution of a house event is "set winner's binary → YES, others → NO, run existing settlement N times."
- **Category nav requires the curated sync:** categories are derived from Gamma `tags` *during sync*; the nav can only show categories the sync actually populated. Hence "suppress empty categories" is a hard dependency, not a nicety.
- **Search/Status/Sort all hang off one extended list endpoint:** today `GET /api/v1/markets` takes no params. The cheapest path is to add `q`, `category`, `status`, `order_by` query params to a single events-aware list endpoint and drive all four UI controls from it.
- **Live odds on event rows enhances but must be capped:** the socket exists; the risk is fan-out on large events. Cap subscriptions to visible rows.
- **Per-outcome bar conflicts with a 100% stacked bar; independent binaries conflict with negRisk:** these are mutually exclusive design choices. v1.2 must pick independence (honest, matches raw data, zero new market-maker logic).

---

## MVP Definition (v1.2 delta)

### Launch With (v1.2 core — the "Credible Catalog")

- [ ] **Event entity** grouping N binary markets (BE schema + read API). *Foundational.*
- [ ] **Curated top-N-per-category Gamma sync with volume floor**, replacing global top-25. *The "credible" in Credible Catalog.*
- [ ] **Category nav from tags + suppress-empty-categories.** *Primary browse mechanic.*
- [ ] **Text search + status filter + sort (volume/closing/newest)** on one extended list endpoint. *Table-stakes browse.*
- [ ] **Multi-outcome event card** (top outcomes + %) in the grid, alongside binary cards. *Catalog scanability.*
- [ ] **Event detail page** with per-outcome rows, independent bars, bet-on-one-outcome (reusing order entry). *The product.*
- [ ] **Admin create/edit/resolve house multi-outcome event** (winner-pick → existing settlement). *Operator parity.*
- [ ] **Seed/demo extended** with multi-outcome events across categories (open + resolved). *The demo must show it.*
- [ ] **Branding carried to all new surfaces** + empty/zero states per filter. *Cheap, sales-critical polish.*

### Add After Validation (later in v1.2 / fast-follow)

- [ ] **Combined event chart** (overlaid top-outcome histories) — add once event detail is solid; highest "looks real" payoff. Trigger: detail page shipped and stable.
- [ ] **Live odds on event rows (WS)** with on-screen subscription cap. Trigger: static event detail validated; only then add real-time fan-out.
- [ ] **Featured "Top events" home shelf** + category count chips. Trigger: catalog grid + categories shipped.

### Future Consideration (v2+ / explicitly deferred)

- [ ] **Scalar/range markets** — OUT of v1.2 (categorical only).
- [ ] **Heavy pagination / infinite scroll** — OUT; revisit only if catalog scale grows past curated.
- [ ] **Secondary trading / sell position / order book** — OUT (no orderbook in v1).
- [ ] **negRisk / mutually-exclusive auto-balancing** — OUT; conflicts with play-money simplicity.
- [ ] **Multi-tenant per-operator catalogs** — OUT (single-tenant in v1).

## Feature Prioritization Matrix

| Feature | User/Sales Value | Implementation Cost | Priority |
|---------|------------------|---------------------|----------|
| Event entity (N binaries) | HIGH | MEDIUM | P1 |
| Curated top-N-per-category sync + volume floor | HIGH | MEDIUM | P1 |
| Category nav (tags) + suppress empty | HIGH | MEDIUM | P1 |
| Event detail: per-outcome rows + independent bars + bet | HIGH | MEDIUM | P1 |
| Multi-outcome event card | HIGH | MEDIUM | P1 |
| Text search | HIGH | LOW–MED | P1 |
| Status filter + sort | MEDIUM | LOW | P1 |
| Admin create/edit/resolve house event | HIGH | MEDIUM | P1 |
| Seed/demo extended | HIGH | MEDIUM | P1 |
| Branding on new surfaces + empty states | MEDIUM | LOW | P1 |
| Combined event chart (overlaid) | HIGH | MEDIUM | P2 |
| Featured home shelf / category counts | MEDIUM | LOW–MED | P2 |
| Live odds on event rows (WS, capped) | MEDIUM | MEDIUM | P2 |
| Resolution transparency on events | MEDIUM | LOW | P2 |
| Scalar/range, pagination, secondary trading, negRisk | LOW (for demo) | HIGH | P3 (out) |

**Priority key:** P1 = must-have for the v1.2 demo · P2 = should-have, add when core is stable · P3 = out of scope / deferred.

## Competitor Feature Analysis

| Feature | Polymarket (reference) | XPredict v1.2 approach |
|---------|------------------------|------------------------|
| Multi-outcome model | Event → N binary `["Yes","No"]` markets; `groupItemTitle` per outcome | Identical event-of-binaries; reuse existing binary settlement |
| Outcome price sum | Independent; **does not sum to 100%** (negRisk only on featured sets) | Independent per-outcome bars; **no** negRisk; honest non-100% sums |
| Event page | Candidate rows + %, per-row Buy Yes/No, combined headline chart | Per-outcome rows + independent bar + bet-on-one (reuse order entry); combined chart as P2 |
| Categories | Tag-driven top nav (Politics/Sports/Crypto/…), left subcategory nav | Curated categories from Gamma tags; suppress empty; no deep subcategory tree |
| Catalog scale | Thousands of markets, pagination, infinite scroll | Curated top-N-per-category + volume floor; **no** heavy pagination |
| Search/sort | Search bar; Trending/Volume/Liquidity/Newest/Ending-soon | Search + status filter + Volume/Closing/Newest (Trending=24h vol as P2) |
| Secondary market | Full CLOB order book, sell positions | None — bet-at-current-price only |
| Branding | Polymarket-branded | White-label `--brand-*` across the whole new surface (the differentiator) |
| Admin authoring | N/A (on-chain/UMA) | House events created/edited/resolved (winner-pick → settle) from admin |

## Sources

- [Polymarket — Markets & Events (data model: Event→Market→Yes/No)](https://docs.polymarket.com/concepts/markets-events) — HIGH
- [Polymarket — Gamma API Get Events (tag_id/active/closed/order/limit/offset filters)](https://docs.polymarket.com/developers/gamma-markets-api/get-events) — HIGH
- **Live `gamma-api.polymarket.com/events` pull, 2026-06-04** — event keys (`tags`, `negRisk`, `enableNegRisk`, `showAllOutcomes`, `featured`, `competitive`, `volume24hr`), market keys (`groupItemTitle`, `outcomePrices`, `outcomes`), and the empirical proof that YES prices do **not** sum to 100% (World Cup: 60 outcomes → 0.45; Iran: 17 → 0.96; null prices present) — HIGH
- [Polymarket — How prices are calculated (implied probability, midpoint)](https://docs.polymarket.com/polymarket-learn/trading/how-are-prices-calculated) — HIGH
- [PolymarketGuide — Outcomes (each outcome = own contract/order book)](https://polymarketguide.gitbook.io/polymarketguide/markets/structure/outcomes) — MEDIUM
- [Polymarket Review 2026 — sort options (Trending/Volume/Liquidity/Newest/Ending soon), card data](https://cryptoslate.com/prediction-markets/polymarket-review/) — MEDIUM
- [Polymarket predictions/all + category pages (category nav, card layout)](https://polymarket.com/predictions/all) — MEDIUM
- [Gate Learn — Polymarket arbitrage (overround / sum<100% is a CLOB artifact)](https://www.gate.com/learn/articles/the-quiet-arbitrageurs-making-fortunes-on-polymarket/12914) — MEDIUM (informs the arbitrage anti-feature)
- Existing XPredict frontend: `frontend/src/components/market-card.tsx`, `market-list.tsx`, `app/markets/[slug]/page.tsx`, `app/page.tsx`, `lib/api.ts` — HIGH (the surface being extended)
- `.planning/PROJECT.md` (locked scope/out-of-scope) + `.planning/spikes/002-polymarket-gamma-parser/README.md` (Gamma parsing discipline) — HIGH

---
*Feature research for: white-label play-money prediction market — v1.2 Credible Catalog delta*
*Researched: 2026-06-04*
