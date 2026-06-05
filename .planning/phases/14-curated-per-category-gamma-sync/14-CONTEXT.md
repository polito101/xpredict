# Phase 14: Curated Per-Category Gamma Sync - Context

**Gathered:** 2026-06-05
**Status:** Ready for planning

<domain>
## Phase Boundary

A sync cycle ingests Polymarket via Gamma `GET /events` (embedded `markets[]` + `tags[]`) and lands a curated, per-category catalog: mirrored events grouped into `market_groups`, child markets stamped with `group_id`, and `Market.category` populated for the first time. The curated catalog replaces the flat top-25-global poll (`poll_polymarket_top25` → `poll_polymarket_events`), runs on a slower beat cadence than the 30s odds poll, and is resilient (keep-last-good on fetch failure, never blank the catalog).

This phase covers **CAT-01..06 + EVT-07** (the Sync layer). It writes `market_groups` rows + stamps `group_id` (consuming the Phase 13 seam). It does NOT touch settlement (Phase 15), API/browse (Phase 16), UI (Phase 17), or seed (Phase 18). The binary market/outcome model, `SettlementService`, the spike-002 closed/UMA guard, and all bet/odds/ledger paths stay unchanged. **Zero new dependencies.**

</domain>

<decisions>
## Implementation Decisions

### Category Allow-List (CAT-03/04)
- Curated categories are a fixed allow-list of **7**: Politics, Sports, Crypto, Pop Culture, Economy, Tech, World (research HIGH-confidence; top-level Gamma tags).
- `Market.category` stores the **human-readable name** ("Politics") — display-ready for the Phase 16/17 browse tabs without a join.
- When an event carries multiple allow-listed tags, the **first by allow-list priority order** wins (deterministic, version-controlled ordering).
- The allow-list is a **version-controlled Python constant** (`POLYMARKET_CATEGORIES`, ~7 `{name → tag_id}` entries) — not env/DB. The exact Gamma `tag_id` integers are resolved via a one-time `GET /tags` lookup during execution and pinned in the constant; unmapped tags are logged for drift, **never auto-added**.

### Curation Thresholds (CAT-02/05)
- **top-N = 10** events per category (≈70 curated events total — credible but bounded).
- **Volume floor = $10,000** on **`volume24hr`** per event, applied **after** conditionId/event-id dedup (avoids Polymarket event-level volume double-counting). *(Refined 2026-06-05 from live-data research: floor on `volume24hr` not total — consistent with the `volume24hr` top-N ranking and the meaningful credibility gate; an event with high historical-but-stale volume is not "credible". `GammaEvent` exposes both metrics so it stays a one-line switch.)*
- `poll_polymarket_events` beat cadence = **every 5 minutes (300s)** — "minutes, not 30s", slower than the 30s odds poll; gentle on the 500 req/10s Gamma /events budget.
- Ranking metric for top-N selection = **`volume24hr`** (freshness; matches the existing `order=volume24hr` sort).
- Pagination: `limit` capped at **500** with a **short-page stop** (stop when a page returns < limit rows).

### Sync Semantics & Migration from top-25 (EVT-07/CAT-05/06)
- Existing top-25 mirrored markets that no longer qualify under curation are **left intact** (they may carry bets; they resolve naturally via the existing UMA detection). The sync only upserts curated rows — **no destructive cleanup**.
- An event with exactly **one** constituent market (`len(markets) == 1`) stays on the **standalone binary path** — no `market_groups` row created. Grouping applies only to events with ≥ 2 outcomes.
- `poll_polymarket_top25` is **removed from the beat schedule** (replaced by `poll_polymarket_events`); the underlying function / `sync_top25` logic is **kept for back-compat and tests** (refactor: extract `_upsert_one_market(parsed, group_id)` so the event and legacy paths share the upsert).
- **keep-last-good is per-category**: a Gamma fetch failure for one category keeps that category's last-good rows while other categories still sync; the catalog is never blanked.
- CAT-06: a category with zero qualifying events is suppressed at the **data layer** — categories are derived from `markets.category` (COUNT > 0); no authoritative categories table.

### Claude's Discretion
- New `GammaEvent` / `GammaTag` Pydantic parsers modeled verbatim on the spike-002 `GammaMarket` template (stringified-JSON validators, Decimal discipline, env-based `extra` policy).
- `source_event_id` for the `market_groups` partial-unique = the Gamma **event id**.
- Lock key for `poll_polymarket_events` distinct from the poll/detect locks (reuse the SETNX owner-token + Lua compare-and-delete release pattern, WR-05).
- Route any event sync through the SAME spike-002 `_derive_status` guard — never a new code path; never settle on `closed=true` alone.
- Capture fresh `GET /events?tag_id=...` + `GET /tags` fixtures before writing parser tests (spike-002 fixtures are single-/markets only).

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/app/integrations/polymarket/client.py` — `GammaClient` (httpx + tenacity, lazy singleton, bounded pool). Add `fetch_events()` + `fetch_tags()`; keep `fetch_top_markets` for back-compat.
- `backend/app/integrations/polymarket/schemas.py` — `GammaMarket` (spike-002 parser: stringified-JSON `field_validator`, `_safe_decimal`, `_derive_status` truth table). Template for `GammaEvent` / `GammaTag`.
- `backend/app/integrations/polymarket/adapter.py` — `PolymarketAdapter.sync_top25` (pg_insert ON CONFLICT (source, source_market_id) upsert; YES/NO outcomes; `changed_markets` for realtime publish). Extract `_upsert_one_market(parsed, group_id)`; add `sync_events()` + parent group upsert + `group_id` stamp + dedup.
- `backend/app/integrations/polymarket/tasks.py` — `poll_polymarket_top25` (`_run_poll_sync` + Redis SETNX lock + post-commit realtime publish). Sibling `poll_polymarket_events` task.
- `backend/app/celery_app.py` — `beat_schedule` dict (`poll-polymarket-top25` @30s, `snapshot-odds` @300s, `detect` @60s). Replace the top25 entry with events @300s; never reassign the dict, `.update()` it.

### Established Patterns
- INSERT ... ON CONFLICT idempotent upsert on partial-unique indexes (migration 0004 markets; migration 0011 added `market_groups` partial-unique `(source, source_event_id) WHERE source_event_id IS NOT NULL`).
- Redis SETNX ownership-token lock + Lua compare-and-delete release (WR-05); distinct lock key per task family.
- `_derive_status` is the single source of truth for closed/UMA → MarketStatus; NEVER settle on `closed=true` alone (spike-002).
- Decimal-only money (string fields → Decimal; never the *Num float variants).
- `Market` already has `volume`, `volume_24hr`, `condition_id`, `polymarket_slug`, `category` (nullable, currently always NULL), and (Phase 13) nullable `group_id` + `group_item_title`; `MarketGroup` ORM model + `Market.group` relationship exist.

### Integration Points
- `market_groups` table + indexes (Phase 13, migration 0011) — this phase is the first writer.
- `Market.category` column — first populated here.
- Beat schedule (`celery_app.py`) — swap the periodic task.
- `backend/app/core/config.py` — add `POLYMARKET_CATEGORIES`, top-N, volume-floor, events-poll-interval settings (`GAMMA_API_BASE_URL`, `POLYMARKET_POLL_INTERVAL_SECONDS` already present).

</code_context>

<specifics>
## Specific Ideas

- Gamma `/events` rate limit is 500 req/10s (NOT the stale "300" comment in client.py, which is /markets-only); limit ceiling 500; `groupItemTitle` on each nested market is the per-outcome display label; live data proof that per-outcome YES prices do NOT sum to 100% (World Cup 60 outcomes → 0.45).
- Run the spike-002 `_derive_status` guard on the event path; never settle on `closed=true` alone.
- Phase 14 = research "Phase 2 (Sync)"; flagged as needing fresh /events + /tags fixtures + a one-time tag_id pin (see `research/SUMMARY.md` §Research Flags).

</specifics>

<deferred>
## Deferred Ideas

- Event settlement (resolve / void / reverse, derived status) — Phase 15.
- Catalog / browse API + house event CRUD — Phase 16.
- Browse UI, event detail, per-outcome rows — Phase 17.
- Seed / demo multi-outcome harness — Phase 18.
- `odds_snapshots` prune / retention task (growth ~23×) — research flags low-urgency, a later phase.

</deferred>
