# Pitfalls Research

**Domain:** Adding multi-outcome (event-of-binaries) markets + curated category catalog to an existing, shipped play-money prediction market (XPredict v1.2 "Credible Catalog")
**Researched:** 2026-06-04
**Confidence:** HIGH on Gamma/negRisk mechanics and existing-system integration points (grounded in spike fixtures + live Polymarket docs); MEDIUM on tag/category drift over time and search-relevance specifics (general API behavior, not a single authoritative source).

> **Scope note.** This is a SUBSEQUENT milestone on a live system. Pitfalls below are specific to *adding* event-of-binaries + a wider curated catalog to the EXISTING binary-market / Gamma-sync / double-entry-settlement machinery. Generic web-app advice is omitted. The recurring theme: XPredict's locked model is **plain event-of-binaries (independent YES/NO markets grouped under an event)** — this is NOT Polymarket's NegRisk model, and most pitfalls flow from that divergence plus the jump from top-25-global to top-N-per-category.

---

## The one fact that drives half of these pitfalls

Polymarket's real multi-outcome markets are **NegRisk events**: N binary markets *economically linked* by a convert action (a NO share in one market = a YES share in every other), enforcing mutual exclusivity so the outcome prices *should* sum to ~$1.00. XPredict v1.2 explicitly does **plain grouped binaries** — independent YES/NO markets, reusing binary settlement, no convert, no enforced sum-to-1. ([Polymarket NegRisk overview](https://docs.polymarket.com/developers/neg-risk/overview), [Market Types](https://polymarketguide.gitbook.io/polymarketguide/markets/structure/market-types))

Consequence: in XPredict, per-outcome YES prices will routinely **not** sum to 100%, there is no "buy all NOs = guaranteed payout" safety, and a mirrored Polymarket NegRisk event resolves its constituents independently and at different times. Half the pitfalls below are downstream of this single gap.

---

## Critical Pitfalls

### Pitfall 1: Treating per-outcome YES prices as a categorical distribution (the "sum-to-100% / free arbitrage" trap)

**What goes wrong:**
The event-detail UI shows each outcome's YES price as if they were slices of a pie (a native categorical market). Under plain event-of-binaries they are independent binaries, so the YES prices sum to anything — 85%, 130%, whatever the mirror/admin set. Users (and a sharp buyer in the demo) read this as either (a) "the platform is broken, probabilities don't add up" or (b) "free arbitrage — I can buy the cheap side of every outcome." Worse: because XPredict has **no orderbook, no convert, and a fixed 2x-style payout** (per spike 004), the "arbitrage" a user thinks they see is not actually realizable, but the *appearance* of it destroys credibility in a sales demo.

**Why it happens:**
The team mirrors Polymarket's *visual* multi-outcome layout (a ranked list of outcomes each with a %) without mirroring its *economic* layer (NegRisk convert that forces sum-to-1). The native-categorical mental model is the default any developer reaches for, and the fixtures already carry a `negRisk` boolean which invites the wrong assumption that the constraint is inherited for free.

**How to avoid:**
- Decide and document the framing up front: each outcome is an **independent YES/NO bet**, not a slice. Label the UI accordingly ("Will X win? Yes/No" per row), and avoid any "these add to 100%" affordance (no stacked bar that visually implies a closed distribution).
- If a "looks like Polymarket" stacked/ranked bar is required for demo polish, **normalize for display only** (render `price_i / Σ price` as the visual width) while the *bet* is always placed at the true independent YES price. Never let the normalized number be the price the user bets at.
- For house events, give admin an optional soft "normalize warning" when the sum of seeded YES prices is wildly off 100% (e.g. <80% or >120%) so seeded demo data looks plausible.
- Explicitly do **not** implement NegRisk convert / mutual-exclusivity enforcement (it's out of scope and would change the settlement model). Just make the framing honest.

**Warning signs:**
Demo viewers asking "why don't these add up?"; an outcome list where YES prices visibly sum to 130%+; anyone on the team writing code that computes "implied probability = price / sum"; a QA note that "the chart looks weird for 4-way events."

**Phase to address:** Player multi-outcome UX phase (event-detail rendering + price framing). Decision should be locked in the multi-outcome data-model phase so UX inherits it.

---

### Pitfall 2: Partial / staggered event resolution — siblings stay open while one outcome settles (mirror) or admin force-settles the wrong granularity (house)

**What goes wrong:**
A mirrored Polymarket event (e.g. "2028 nominee") resolves its constituent markets **independently and at different times** — UMA proposes + a 2-hour challenge window per market, and a losing candidate's market can resolve "No" weeks before the winner's resolves "Yes." If XPredict's sync/settlement assumes "an event resolves atomically," it will either (a) wait for the whole event and never settle the early-resolving legs, freezing user funds, or (b) try to settle the event as a unit and corrupt the ledger. On the **house** side, the admin UI ("resolve event = pick winner") can wrongly settle *all* constituent binaries at once when the operator only meant to resolve one, or fail to handle "this leg is void."

**Why it happens:**
Mental shortcut: "an event is one thing, so it resolves once." But Polymarket events are containers of independent markets; per-market `umaResolutionStatus` already proves this in the spike fixtures (each market carries its own status/history). The existing v1.0 settlement is per-binary-market and is actually *correct* for this — the danger is a new event-level wrapper that overrides it.

**How to avoid:**
- **Reuse, do not replace, the per-binary settlement.** Settlement stays at the binary-market grain (spike 004: lock market FOR UPDATE → set SETTLING → settle bets → idempotent replay). The "event" is purely a grouping/display layer over independent settle-able binaries. This is also the locked decision — enforce it in code review.
- Sync must resolve **each constituent market on its own UMA signal**, exactly as the top-25 path does today. Never gate a leg's settlement on its siblings.
- House admin "resolve event": model it as "resolve constituent market(s)," not "resolve event." Picking the winner = settle that leg YES and (optionally, with explicit confirm) settle the rest NO. Allow per-leg resolution and per-leg void. Keep the existing two-step confirm + justification (v1.0 Phase 12 pattern).
- Event-level status is **derived** (open / partially-resolved / fully-resolved), never authoritative. Compute it from constituent statuses.

**Warning signs:**
A DB column like `events.winning_outcome` or `events.settled_at` that tries to be the source of truth; settlement code that loops over "all markets in event" inside one transaction without per-market locks; user bets on a resolved-loser outcome still showing "open"; the integrity checker (spike 004 double-entry invariant) flagging drift after an event "resolve."

**Phase to address:** Multi-outcome data-model + settlement-integration phase (binary settlement reuse, derived event status). House resolution UX in the Admin multi-outcome phase. Mirror sync handling in the Gamma-events-sync phase.

---

### Pitfall 3: "None of the above" / void / "Other" outcomes and disputed legs not modeled (`closed != resolved`, the augmented-NegRisk "Other")

**What goes wrong:**
Two distinct edge cases collapse into one bug if ignored:
1. **Void / disputed leg.** A constituent market is `closed=true` but only `umaResolutionStatus="proposed"` or `"disputed"` (the exact spike 002 PITFALL #2 case). If the event/sync settles on `closed` alone, it pays out on an unresolved or about-to-be-overturned outcome.
2. **"None of the above" / "Other".** Polymarket's NegRisk-augmented events carry an explicit **"Other"** outcome that catches anything unnamed; if "Other" wins, all *named* legs resolve No. Also, a genuinely voided market on Polymarket can resolve **50/50** (price `["0.5","0.5"]`). A naive "highest price = winner" will mis-settle these.

**Why it happens:**
The team tests with the clean `resolved_market.json` fixture (clear `["0","1"]` winner) and forgets the `closed_not_resolved.json` and disputed fixtures already captured in spike 002. The "Other" outcome is a NegRisk-specific construct that's easy to miss because it isn't a "real" candidate. ([How markets resolve — 2h challenge period](https://help.polymarket.com/en/articles/13364518-how-are-prediction-markets-resolved), [NegRisk "Explicit Other"](https://docs.polymarket.com/developers/neg-risk/overview))

**How to avoid:**
- Carry forward the spike-002 non-negotiable: **never settle on `closed=true` alone.** Require `closed + umaResolutionStatus="resolved" + a clear winner` (`outcomePrices` containing a definitive 1). This already exists for top-25 — make sure the event path routes through the *same* guard, not a new code path.
- Model a **VOID resolution** for a constituent binary explicitly: refund stakes (reverse the bet's ledger entries) rather than pay a winner. Detect it from `outcomePrices == ["0.5","0.5"]` or an explicit admin "void this leg" action. House events need an admin "void leg" too.
- Treat an **"Other"/none-of-the-above** outcome as just another constituent binary in XPredict's model (it's a YES/NO like the rest). No special economics needed — but the seed/mirror must *include* it so a mirrored event that resolves to "Other" settles correctly and doesn't leave named legs orphaned.
- Keep `umaResolutionStatuses` (plural history) for the audit trail, as spike 002 recommends.

**Warning signs:**
Settlement keyed on `closed`; no VOID/refund path in the settlement service; mirrored events whose outcomes don't include the "Other" leg present on Polymarket; a disputed market in the demo showing a confident winner; integrity-checker drift after a refund.

**Phase to address:** Gamma-events-sync phase (state-machine routing reuse, "Other" ingestion) + settlement-integration phase (VOID/refund path). This is the highest-risk integration item — flag for a focused review.

---

### Pitfall 4: Gamma `/events` ingestion at scale — pagination ceiling, rate limits, 500s under load, and dedup of nested markets

**What goes wrong:**
Going from "top-25 markets, one global call" to "top-N per category across many categories via `/events`" multiplies request volume and surface area:
- **Pagination ceiling:** Gamma `limit` maxes at **500**; offset-based paging past the end is silent (fewer rows than `limit`). Code that hard-codes `limit=1000` or never checks for the short page will silently truncate or loop forever.
- **Rate limits:** general 4,000 / 10s, **`/events` 500 / 10s, `/markets` 300 / 10s, `/public-search` 350 / 10s.** A category-fan-out loop (one `/events?tag_id=…` per category, possibly paged) can trip these, especially if run on every Beat tick.
- **500s under load:** Gamma returns 5xx during high-traffic periods; without retry/backoff the sync task fails and the catalog goes stale mid-demo.
- **Dedup:** an event can carry **multiple markets**, and the *same* market/event can appear under multiple tags (re-tagged or multi-tagged), so a category fan-out yields duplicates. Polymarket itself has a documented **volume double-counting** issue at the event level — naive volume sums inflate the "credible" metrics. ([rate limits + pagination](https://agentbets.ai/guides/polymarket-gamma-api-guide/), [fetch-markets guide](https://docs.polymarket.com/developers/gamma-markets-api/fetch-markets-guide), [volume double-counting](https://www.paradigm.xyz/2025/12/polymarket-volume-is-being-double-counted))

**Why it happens:**
The top-25 path was small enough that none of this mattered — one call, no paging, no dedup, occasional failure invisible. The wider catalog crosses the threshold where each of these becomes load-bearing, but the existing sync code "looks done" because it works for 25.

**How to avoid:**
- Prefer **`/events?active=true&closed=false&tag_id=…&order=volume…`** (events embed their markets → fewer calls than per-market) and page with `limit<=500`, **stop when a page returns `< limit` rows.** Never hard-code an unbounded limit.
- Add **token-bucket / sleep between calls** sized to the per-endpoint budget (esp. `/events` 500/10s, `/markets` 300/10s). Don't run the full fan-out every 30s — curation can refresh on a slower cadence (e.g. minutes) than odds.
- **Retry with exponential backoff + jitter on 5xx/429**, and treat a failed refresh as "keep last good catalog" (never blank the catalog on a transient error — critical for demo).
- **Dedup by `conditionId`** (the on-chain CTF id) at the market grain and by event `id`/`slug` at the event grain, since the same item appears across tags. Compute the **volume floor on a de-duplicated, single-counted basis** to avoid the double-counting inflation.
- Reuse the spike-002 parser as-is (`extra='allow'`, stringified-JSON validators, string-numeric → Decimal). The event wrapper has 50+ fields too; don't model them exhaustively.

**Warning signs:**
A `limit` value > 500 anywhere; the sync loop with no `break` on short pages; HTTP client with no retry on 5xx; catalog row count jumping/duplicating after adding a category; volume numbers that look ~2x too high; sporadic empty catalog during the demo; logs showing 429s.

**Phase to address:** Curated-catalog Gamma-sync phase (pagination, rate-limit budget, retry/backoff, dedup, volume floor). Resilience ("keep last good") should be an explicit success criterion.

---

### Pitfall 5: Tag/category drift — categories renamed, markets re-tagged, events split/merged → curated catalog rots over time

**What goes wrong:**
XPredict's categories are *derived from Gamma tags* (numeric tag IDs: Politics=2, Crypto=21, Sports=100639, etc.). Over time Polymarket re-tags markets, adds/retires tags, and an event's market set can change (markets added/removed; events effectively split or merged). A curated "top-N per category with volume floor" snapshot taken once will drift: a mirrored market's category silently changes, an event loses a leg, or a whole category empties out. Because the catalog is *curated* (not "all active"), drift shows up as **categories that slowly go stale, sparse, or mis-sorted** — and there's no firehose to mask it. The Gamma docs do **not** guarantee slug stability or tag permanence.

**Why it happens:**
Curation is treated as a one-time import rather than a continuously-reconciled projection. Tag IDs are assumed stable forever. The team maps Gamma tags → XPredict categories with a hard-coded table and never revisits it. ([tag IDs & filtering](https://docs.polymarket.com/developers/gamma-markets-api/fetch-markets-guide), [markets & events container model](https://docs.polymarket.com/concepts/markets-events))

**How to avoid:**
- Treat the curated catalog as a **reconciled projection, refreshed every sync**: re-pull per-category top-N, upsert by `conditionId`/event id, and **mark items no longer meeting the floor/category as inactive** (don't delete — preserves bet history and ledger). Mirrored items that vanish from Gamma get an explicit "delisted/closed-upstream" state, not a hard delete (users may have open bets).
- Keep a **stable internal `category` enum** decoupled from Gamma tag IDs, with an explicit, version-controlled **tag-id → category mapping**. If Polymarket changes a tag id or a market gets re-tagged, only the mapping changes, not the schema. Log unmapped tags so drift is visible.
- Pin the demo to a **curated allow-list of events/categories** (or a "featured" flag) so a live sales demo isn't at the mercy of upstream re-tagging that day. Re-tagging can move a market out of its category mid-demo otherwise.
- Reconcile event membership: if a mirrored event's constituent set changes, add new legs as new binaries and mark removed legs as delisted — never silently drop a leg someone bet on.

**Warning signs:**
A hard-coded `tag_id == 2 → "Politics"` with no fallback; categories that were full at import and are now sparse; a market that "moved" categories between syncs; orphaned bets on a leg that disappeared upstream; the demo showing an empty "Sports" tab because the tag id changed.

**Phase to address:** Curated-catalog sync phase (reconciliation, tag→category mapping, delist vs delete). Demo allow-list/featured flag in the Seed/demo phase.

---

### Pitfall 6: Mirrored-vs-house event divergence leaks through the MarketSource abstraction

**What goes wrong:**
Two event sources behave differently: **mirrored** events resolve per-leg via UMA on Polymarket's schedule (out of admin's control, can be disputed/void, prices update from sync); **house** events are admin-controlled (manual resolve/void, prices admin-set, no UMA). If the multi-outcome layer special-cases `if source == polymarket` throughout the codebase, the clean MarketSource/HouseAdapter seam built in v1.0 erodes — settlement, resolution, price-update, and admin-edit paths sprout source-conditionals. The opposite failure: forcing house events through the mirror's UMA-shaped resolution and discovering the admin can't actually resolve them.

**Why it happens:**
Multi-outcome is the first feature that meaningfully *groups* markets, and grouping tempts a new event-level abstraction that bypasses the existing per-market source seam. The differences (who resolves, where price comes from) are real, so conditionals feel natural.

**How to avoid:**
- Keep the **MarketSource Protocol at the binary-market grain** (it already works in v1.0). The "event" is a thin grouping over source-typed binaries; an event can in principle hold legs of one source. Resolution/price-update dispatch stays via the adapter, *not* via `if event.source`.
- Define the **divergent behaviors as adapter methods**, not call-site conditionals: "can admin resolve this leg?", "is price authoritative-from-sync or admin-set?", "is void allowed manually?". Mirror adapter and house adapter answer differently; the event layer stays source-agnostic.
- **Block editing mirrored legs' prices/outcomes** in admin (they come from sync) — surface them read-only with a "mirrored from Polymarket" badge, while house legs are fully editable. Enforce at the adapter, not the UI only.
- Add a test that the event layer never imports a concrete source — only the Protocol.

**Warning signs:**
`if source == "polymarket"` / `isinstance(..., HouseAdapter)` appearing in event/settlement/price code; admin able to hand-edit a mirrored market's price; a new `EventService` that re-implements resolution instead of delegating to existing per-market settlement; the abstraction requiring a change in two adapters for every new event feature.

**Phase to address:** Multi-outcome data-model phase (event-as-grouping-over-source-typed-binaries; adapter method surface). Reinforce in Admin multi-outcome phase (read-only mirrored legs).

---

### Pitfall 7: Real-time price fan-out and odds-snapshot growth across many more markets

**What goes wrong:**
The WS design (spike 003) is **per-market channels** (`psubscribe("prices:*")`, a `set[WebSocket]` per market) and odds snapshots are written per market per poll. Top-25 → curated catalog (potentially several hundred markets, each multi-outcome event multiplying market count) changes two things:
1. **Snapshot table growth:** `odds_snapshots` rows = markets × poll frequency × time. 25 markets was trivial; 300+ markets at a 30s odds cadence is ~10x+ row growth, and an event-detail "chart per outcome" multiplies reads. Unbounded, this bloats the table and slows chart queries — visible as a laggy demo.
2. **Fan-out / publish volume:** each poll now publishes far more `prices:{id}` messages; an event-detail page subscribing to N outcome channels at once multiplies client connections. The spike proved the pipeline is fast at small scale but didn't test hundreds of markets × multi-outcome pages.

**Why it happens:**
The streaming spike's own note: "the bottleneck will be the Polymarket poll interval, not the streaming pipeline" — true at 25 markets. The catalog widening invalidates the scale assumption, but the code "looks done."

**How to avoid:**
- **Only stream/poll what's curated and open.** Don't snapshot resolved/delisted/closed markets. Tie the poll set to the active curated catalog, not "everything ever synced." This alone caps the multiplier.
- **Bound odds-snapshot growth**: write a snapshot only on *price change* (skip no-op writes), and/or downsample older history (retain dense recent + sparse old). The chart only needs enough points to look credible.
- For event-detail pages, prefer **one event-level subscription** (a `prices:event:{id}` channel that batches all legs) over N per-leg WS connections, or cap concurrent per-leg subscriptions. Reuse the existing per-market channel for single-market detail.
- Differentiate cadence: **odds poll stays ~30s; catalog/curation refresh is slower** (minutes) — they're separate concerns and shouldn't share a Beat tick.
- Index `odds_snapshots (market_id, captured_at)` for the chart range query; verify the plan with the wider row count.

**Warning signs:**
`odds_snapshots` row count growing linearly with no retention; chart endpoint latency rising as the catalog grows; an event-detail page opening 6+ WebSocket connections; the 30s poll task duration creeping up as market count rises; Redis publish volume spiking.

**Phase to address:** Curated-catalog sync phase (poll-set = active curated only; snapshot-on-change). Player multi-outcome UX phase (event-level subscription / chart-per-outcome read pattern + index).

---

### Pitfall 8: Search performance & relevance + empty/sparse categories silently degrade the demo

**What goes wrong:**
The browse feature (search + category filters + status/sort) introduces two demo-killers:
1. **Relevance:** naive `ILIKE '%query%'` over titles gives unranked, substring-only matches (no typo tolerance, "biden" won't match "Biden's", multi-word queries match poorly). In a live demo, searching the obvious term and getting junk or nothing reads as "the product doesn't work."
2. **Sparse/empty categories:** because the catalog is *curated* (top-N + volume floor), some categories legitimately have 0–2 items, and after drift (Pitfall 5) more empty out. A category tab that opens to a blank grid, or a sort that surfaces a single stale market, looks broken in a sales context.

**Why it happens:**
Search is treated as an afterthought ("just filter the list"), and the curated/sparse nature of the catalog isn't reconciled against the UI's assumption that every category is full. The dataset is small enough that performance isn't the issue — *relevance and emptiness* are.

**How to avoid:**
- For this dataset size (hundreds, not millions of rows), use **Postgres full-text search (`tsvector` + GIN) with relevance ranking**, optionally combined with **`pg_trgm` trigram** for typo/partial tolerance on short titles. This is well within Postgres's comfort zone and rivals a dedicated search engine at this scale. Weight title > description with `setweight`. ([Postgres FTS + trigram for short titles](https://smoketrees.in/blog/full-text-search-using-trigram-and-tsvector/))
- **Guarantee non-empty categories for the demo**: enforce a *minimum* per-category count in curation (if a category can't meet top-N above the floor, either lower its floor, borrow related-tag items, or hide the category tab entirely rather than show it empty). Never render a category that resolves to an empty grid.
- Design **explicit empty/sparse states** ("No open markets in Crypto right now" + suggested categories) so even a genuinely thin category looks intentional, not broken.
- Sort defaults that flatter the demo: default to volume/liquidity desc so the strongest markets lead each category.

**Warning signs:**
`ILIKE` or `LIKE` as the search implementation; searching a known market by name and getting no result or a bad order; a category tab that can open empty; QA finding a "Politics" tab with one resolved market; no empty-state component.

**Phase to address:** Browse/search phase (Postgres FTS + trigram, ranking, empty states). Minimum-per-category guarantee in the Curated-catalog sync phase. Empty-state polish reinforced in Seed/demo.

---

### Pitfall 9: Demo seed no longer realistic — multi-outcome events + categories seeded shallowly

**What goes wrong:**
The v1.1 seed harness seeds *binary* markets. If extended naively, it produces multi-outcome events that betray the "credible catalog" claim: 2-outcome "events" that are really just binaries (no reason to be an event), every event with the same outcome count, YES prices that sum absurdly (Pitfall 1) because they were random, categories that are uneven (one full, rest empty — Pitfall 8), no partially-resolved event to showcase staggered settlement (Pitfall 2), and no void/"Other" leg (Pitfall 3). A sharp buyer probing the demo finds the cracks the locked decisions were meant to avoid.

**Why it happens:**
Seed data is the last thing built and is treated as filler. But for a *sales demo* it's the primary surface — and multi-outcome + categories massively expand what "realistic" requires versus binary-only.

**How to avoid:**
- Seed **varied, plausible events**: a mix of 3–8 outcome events across categories, with per-outcome YES prices that are *individually* believable (and whose normalized display roughly approximates a distribution, even though they're independent).
- Seed **every demo state on purpose**: at least one fully-open event, one **partially-resolved** event (one leg settled, siblings open — proves Pitfall 2 handling), one fully-resolved event with a clear winner and the rest No, and one event with a **void/"Other"** leg (proves Pitfall 3). Include bets with P&L on resolved legs (reuse v1.1 P&L seeding).
- **Fill every category above the demo minimum** (Pitfall 8) so no tab is empty; mark a curated "featured" subset that the sales script walks through, insulated from upstream drift (Pitfall 5).
- Seed **odds history per outcome** so the per-outcome charts aren't flat (reuse v1.1 odds-history seeding, extended to event legs).
- Keep the **reset** command working with the new shape (idempotent re-seed), and run the existing double-entry integrity check (spike 004) over the seeded ledger so seeded bets/settlements balance.

**Warning signs:**
Every seeded event has exactly 2 outcomes; seeded YES prices sum to random totals; one category full and others empty; no partially-resolved or void event in the seed; flat outcome charts; the reset command breaking on multi-outcome rows; integrity checker flagging seeded data.

**Phase to address:** Seed/demo phase. Depends on all prior phases being correct (it exercises them end-to-end) — schedule it last and treat it as the integration acceptance test for the milestone.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Store `events.winning_outcome` / `settled_at` as event-level source of truth | Simple "resolve event" mental model | Breaks staggered/partial resolution (Pitfall 2), corrupts per-leg ledger | **Never** — derive event status from constituent binaries |
| Settle all constituent binaries in one loop without per-market FOR UPDATE | Less code than reusing per-market settlement | Reintroduces the spike-004 late-bet race + drift; bypasses idempotency | **Never** — reuse proven per-market settlement |
| `ILIKE '%q%'` search for v1.2 | Ships in an hour | Bad relevance kills the demo; rework to FTS later | Only as a throwaway spike, never in the demo build |
| Hard-coded `tag_id → category` with no fallback/logging | Fast mapping | Silent category drift, empty tabs (Pitfall 5) | Acceptable only with unmapped-tag logging + version-controlled mapping |
| One-time catalog import (no per-sync reconciliation) | Simplest sync | Catalog rots; orphaned bets on delisted legs | **Never** for a "credible" catalog — must reconcile + delist |
| Snapshot every market every poll forever | No retention logic | `odds_snapshots` bloat, laggy charts (Pitfall 7) | Acceptable short-term *only* if poll set is capped to active-curated and snapshot-on-change is planned next |
| Hard-code `limit` > 500 / no short-page break | "Gets everything" in one call | Silent truncation or infinite loop (Pitfall 4) | **Never** — 500 is the ceiling |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Gamma `/events` | Assuming event resolves atomically | Each constituent market resolves independently via its own UMA signal (2h challenge window); settle per-leg |
| Gamma `/events` | `limit=1000`, never check short page | `limit<=500`; stop when page returns `< limit` rows |
| Gamma rate limits | Full category fan-out on every 30s Beat tick | Curation on slower cadence; token-bucket to `/events` 500/10s, `/markets` 300/10s; backoff on 5xx/429 |
| Gamma volume | Summing event volume naively | De-dup by `conditionId`; account for documented event-level double-counting before applying the volume floor |
| Gamma dedup | Same market under multiple tags → duplicates in catalog | Dedup by `conditionId` (market) / event `id`/`slug` (event) |
| UMA resolution | Settling on `closed=true` | Require `closed + umaResolutionStatus="resolved" + clear winner`; route event path through the *same* guard as top-25 |
| NegRisk "Other" | Dropping the unnamed/"Other" leg when mirroring | Ingest "Other" as an ordinary constituent binary so the event settles fully |
| Void markets | Mis-settling a 50/50 void as a winner | Detect `["0.5","0.5"]` (or admin void) → refund path, not payout |
| MarketSource seam | `if source == "polymarket"` in event/settlement code | Divergent behavior as adapter methods; event layer stays source-agnostic |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| `odds_snapshots` unbounded growth | Table bloat, slow chart queries | Snapshot-on-change + retention/downsample; poll only active-curated | ~10x market count (top-25 → few-hundred) over days |
| Per-leg WS connection storms | Event page opens N WebSockets | Event-level batched channel or cap concurrent subscriptions | Multi-outcome detail pages with 5+ legs |
| Category fan-out request volume | 429s, sync task slow/failing | Slower curation cadence, rate-limit budget, backoff | Many categories × paging on a 30s tick |
| Search without index/ranking | Slow or irrelevant results | Postgres FTS (GIN) + `pg_trgm`; ranked | Relevance breaks immediately; perf only at large scale (not this dataset) |
| Chart range scan per outcome | Event page slow as history grows | Index `(market_id, captured_at)`; bounded point count | Wider catalog × long history |

## Security / Integrity Mistakes

(Beyond OWASP — domain-specific ledger/resolution integrity, which IS the product's credibility.)

| Mistake | Risk | Prevention |
|---------|------|------------|
| Event-level settle bypassing per-market FOR UPDATE | Ledger drift / double-payout under concurrent admin+sync (spike 004 late-bet race) | Reuse per-market lock → SETTLING → settle → idempotent replay; run integrity checker after event resolves |
| Settling on `closed` not `resolved` | Pays out on disputed/overturnable outcome | Spike-002 guard on the shared settlement path |
| No refund path for void/50-50 legs | Funds mis-assigned; double-entry invariant violated | Explicit VOID resolution that reverses bet entries; verify SUM(entries)=0 |
| Admin editing mirrored leg prices | Operator desyncs from Polymarket truth, demo credibility loss | Mirrored legs read-only at the adapter level, not just UI |
| Non-idempotent event re-resolve | Replaying a partially-resolved event double-settles a leg | Per-leg `settled_at IS NULL` idempotency gate (existing) must cover the event path |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Outcomes shown as a closed % distribution that doesn't sum to 100 | "Broken / free arbitrage" perception (Pitfall 1) | Per-row YES/NO framing; normalize for display only, bet at true price |
| One leg resolved, siblings still "open" with no indicator | Confusion about partially-settled events | Clear per-leg status + derived event status (open/partial/resolved) |
| Empty category tab | "Product doesn't work" in demo (Pitfall 8) | Guarantee min-per-category or hide tab; explicit empty state |
| Bad search results for an obvious query | Demo credibility loss | Ranked FTS + trigram typo tolerance |
| Flat outcome charts (no history) | Looks unfinished | Seed per-outcome odds history |
| No "mirrored from Polymarket" vs "house" signal | Operator/user can't tell why a market behaves differently | Source badge + read-only mirrored legs |

## "Looks Done But Isn't" Checklist

- [ ] **Multi-outcome event:** renders N outcomes — but verify YES prices are framed as independent (not implied sum-to-100), and a >2-leg event displays/sorts correctly.
- [ ] **Event resolution:** "resolve" works — but verify a **partially-resolved** event (one leg settled, siblings open) is correct, and an early-resolving loser leg actually settles instead of waiting for the event.
- [ ] **Void/"Other":** clear-winner settles — but verify a **50/50 void** refunds and an **"Other"/none-of-the-above** outcome settles named legs No.
- [ ] **Catalog sync:** categories populate — but verify short-page stop, dedup by `conditionId`, retry/backoff on 5xx, and "keep last good" on failure (no blank catalog).
- [ ] **Drift handling:** import works — but verify a re-synced market that left its category is delisted (not deleted) and orphaned bets are handled.
- [ ] **Search:** returns results — but verify ranking, typo tolerance, and an obvious by-name lookup; verify no category opens empty.
- [ ] **Streaming/snapshots:** prices update — but verify snapshot-on-change (not every poll), poll set limited to active-curated, and event-detail doesn't open a WS-connection storm.
- [ ] **MarketSource seam:** events work — but grep for `if source ==` / `isinstance(...Adapter)` in event/settlement/price code (should be none); confirm mirrored legs are read-only.
- [ ] **Seed/demo:** seeds events — but verify varied outcome counts, every category filled, a partially-resolved + a void event present, per-outcome history, reset idempotent, integrity checker green.
- [ ] **Ledger integrity:** settlement runs — but run the spike-004 double-entry invariant after every event resolution path (including partial + void).

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Event-level settlement corrupted ledger (Pitfall 2) | HIGH | Reverse affected settlement entries via audit log; re-settle per-leg; run integrity checker; backfill correct payouts |
| Settled on `closed` not `resolved` (Pitfall 3) | HIGH | Reverse premature payouts; re-resolve once UMA `resolved`; audit-log the correction |
| Catalog rotted / sparse from drift (Pitfall 5) | MEDIUM | Re-run reconciliation; fix tag→category mapping; delist orphans; re-seed featured set |
| Catalog blanked on sync failure (Pitfall 4) | LOW | "Keep last good" prevents it; if hit, re-run sync; add the resilience guard |
| `odds_snapshots` bloat (Pitfall 7) | LOW-MEDIUM | Add retention/downsample job; switch to snapshot-on-change; archive old rows |
| Sum-to-100 confusion shipped (Pitfall 1) | LOW | Display-only normalization + per-row framing; copy change, no data migration |
| Empty category tabs in demo (Pitfall 8) | LOW | Add min-per-category guard / hide-empty + empty-state component |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1. Sum-to-100 / arbitrage perception | Multi-outcome data-model (framing decision) → Player multi-outcome UX | Demo viewer doesn't ask "why don't these add up"; bets place at true price |
| 2. Partial/staggered resolution | Multi-outcome data-model + settlement-integration; house in Admin multi-outcome | Partially-resolved event correct; integrity checker green; no event-level source-of-truth column |
| 3. Void / "Other" / `closed!=resolved` | Gamma-events-sync + settlement-integration | `closed_not_resolved` + 50/50 + "Other" fixtures all settle correctly |
| 4. Pagination / rate limits / dedup / 5xx | Curated-catalog Gamma-sync | Short-page stop; dedup by conditionId; backoff on 5xx; catalog never blanks |
| 5. Tag/category drift | Curated-catalog sync; demo allow-list in Seed/demo | Re-tagged market delisted not deleted; unmapped tags logged; featured set stable |
| 6. Mirror-vs-house divergence | Multi-outcome data-model; Admin multi-outcome | No `if source==` in event/settlement code; mirrored legs read-only |
| 7. Fan-out / snapshot growth | Curated-catalog sync + Player multi-outcome UX | Snapshot-on-change; poll set = active-curated; no WS storm on event page |
| 8. Search relevance / empty categories | Browse/search; min-per-category in sync | Ranked results for by-name query; no empty category tab |
| 9. Unrealistic seed | Seed/demo (last) | Varied events, every category filled, partial+void states, history, reset idempotent, integrity green |

## Sources

- [Polymarket NegRisk Overview](https://docs.polymarket.com/developers/neg-risk/overview) — convert mechanism, "Explicit Other", standard-multi-outcome (independent) vs negRisk (linked) — HIGH
- [Polymarket Market Types (PolymarketGuide)](https://polymarketguide.gitbook.io/polymarketguide/markets/structure/market-types) — mutual exclusivity, prices sum to $1 under negRisk — MEDIUM
- [Polymarket Gamma — Fetch Markets Guide](https://docs.polymarket.com/developers/gamma-markets-api/fetch-markets-guide) — events embed markets, pagination, tag_id filtering — HIGH
- [Polymarket Gamma — Get Events](https://docs.polymarket.com/developers/gamma-markets-api/get-events) — `/events` params (tag_id, related_tags, exclude_tag_id, order, active, closed, limit, offset, slug) — HIGH
- [Polymarket Markets & Events concepts](https://docs.polymarket.com/concepts/markets-events) — event = container of related markets; slug identity — HIGH
- [AgentBets Gamma API Guide (2026)](https://agentbets.ai/guides/polymarket-gamma-api-guide/) — rate limits (4000/10s general, events 500/10s, markets 300/10s, public-search 350/10s), max limit 500, larger-page advice — MEDIUM
- [How Are Prediction Markets Resolved (Polymarket Help)](https://help.polymarket.com/en/articles/13364518-how-are-prediction-markets-resolved) — 2h challenge window, $1/share payout — HIGH
- [Arbitrage in Prediction Markets (arXiv 2508.03474)](https://arxiv.org/abs/2508.03474) — "total < 100%" multi-outcome arbitrage, unity-constraint violations, thin markets drift — MEDIUM
- [Polymarket Volume Is Being Double-Counted (Paradigm)](https://www.paradigm.xyz/2025/12/polymarket-volume-is-being-double-counted) — event-level volume double-counting (affects volume floor) — MEDIUM
- [Postgres FTS: trigram + tsvector for short titles](https://smoketrees.in/blog/full-text-search-using-trigram-and-tsvector/) — FTS + pg_trgm hybrid for short strings, setweight ranking — MEDIUM
- XPredict spike 002 (polymarket-gamma-parser) — `closed != resolved` guard, stringified JSON, per-market `umaResolutionStatus`, `negRisk` field present, schema drift via `extra='allow'` — HIGH (internal, validated)
- XPredict spike 004 (settlement-acid-transaction) — per-market FOR UPDATE → SETTLING → idempotent replay, late-bet race, double-entry invariant — HIGH (internal, validated)
- XPredict spike 003 (websocket-price-streaming) — per-market `prices:*` channels, snapshot-from-table-not-stream, "bottleneck is poll interval at 25 markets" scale assumption — HIGH (internal, validated)

---
*Pitfalls research for: multi-outcome (event-of-binaries) + curated category catalog on an existing play-money prediction market (XPredict v1.2)*
*Researched: 2026-06-04*
