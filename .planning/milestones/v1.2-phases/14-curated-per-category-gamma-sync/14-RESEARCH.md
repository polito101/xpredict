# Phase 14: Curated Per-Category Gamma Sync - Research

**Researched:** 2026-06-05
**Domain:** Polymarket Gamma `/events` ingestion → curated per-category catalog (Python 3.12 · FastAPI · SQLAlchemy 2 async · Postgres 16 · Celery+redbeat · httpx+tenacity · Pydantic v2)
**Confidence:** HIGH — milestone architecture (HIGH) + live Gamma API confirmed this session (all 7 tag_ids resolved, `/events` shape captured, parser design executed against fresh fixtures)

## Summary

This phase swaps the flat top-25-global `/markets` poll for a curated **top-N-per-category** ingestion off Gamma `GET /events`. The milestone research (`research/ARCHITECTURE.md` Pattern 3, `research/SUMMARY.md` Phase 2) already nailed the architecture: an event JSON is a 1:1 match with the Phase-13 `market_groups` seam — `event → 1 market_groups row`, each nested `markets[]` child → 1 binary `Market` stamped with `group_id` + `group_item_title` + `category`. This research closes the **implementation** gaps so the planner can write concrete tasks.

**Everything load-bearing was verified live this session** (not assumed): the 7 category `tag_id` integers are pinned from live `GET /tags/slug/{slug}` (HTTP 200 each); the `/events` nested shape was captured into three fresh fixtures; and a prototype `GammaEvent` / `GammaEventMarket` / `GammaTag` was **executed against those fixtures** through the real `app.integrations.polymarket.schemas` module — nested `markets[]` parse through the existing `GammaMarket` verbatim, and the first-by-priority category resolver correctly routed a dual-tagged (World+Politics) event to **Politics**.

**Primary recommendation:** Add `GammaEvent`/`GammaTag`/`GammaEventMarket(GammaMarket)` to `schemas.py`; add `GammaClient.fetch_events()`; refactor `sync_top25`'s per-market body into `_upsert_one_market(session, parsed, group_id, category)` and build `sync_events()` on top (parent group upsert via `ON CONFLICT (source, source_event_id)` + child stamp); add `poll_polymarket_events` task (per-category loop, dedup-before-floor, keep-last-good per category, distinct SETNX lock); swap the beat schedule entry (drop `poll-polymarket-top25`, add `poll-polymarket-events` @300s). Pin `POLYMARKET_CATEGORIES` in `config.py` with the 7 verified tag_ids. **Zero new dependencies.**

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **7 categories**, allow-list = version-controlled Python constant `POLYMARKET_CATEGORIES` ({name→tag_id}): Politics, Sports, Crypto, Pop Culture, Economy, Tech, World.
- `Market.category` stores the **human-readable name** ("Politics") — display-ready for Phase 16/17 browse tabs without a join.
- **First-by-allow-list-priority wins** when an event carries multiple allow-listed tags (deterministic, version-controlled ordering).
- The exact Gamma `tag_id` integers resolved via a one-time `GET /tags` lookup and pinned in the constant; unmapped tags logged for drift, **never auto-added**.
- **top-N = 10** events per category (≈70 curated events total).
- **Volume floor = $10,000** on `volume24hr` per event, applied **after** conditionId/event-id dedup. *(RESOLVED 2026-06-05: refined from "total" → `volume24hr` — see CONTEXT line 26 + Open Question 1.)*
- `poll_polymarket_events` beat cadence = **every 5 minutes (300s)** — slower than the 30s odds poll.
- Ranking metric for top-N = **`volume24hr`** (matches the existing `order=volume24hr` sort).
- Pagination: `limit` capped at **500** with a **short-page stop** (stop when a page returns < limit rows).
- Existing top-25 mirrored markets that no longer qualify are **left intact** (no destructive cleanup) — sync only upserts curated rows.
- An event with exactly **one** constituent market (`len(markets) == 1`) stays on the **standalone binary path** — no `market_groups` row. Grouping applies only to events with ≥ 2 outcomes.
- `poll_polymarket_top25` is **removed from the beat schedule**; the function / `sync_top25` logic is **kept for back-compat and tests** (refactor: extract `_upsert_one_market(parsed, group_id)`).
- **keep-last-good is per-category**: a Gamma fetch failure for one category keeps THAT category's last-good rows while other categories still sync; the catalog is never blanked.
- CAT-06: a category with zero qualifying events is suppressed at the **data layer** — categories derived from `markets.category` (COUNT > 0); **no authoritative categories table**.

### Claude's Discretion
- New `GammaEvent` / `GammaTag` Pydantic parsers modeled verbatim on the spike-002 `GammaMarket` template (stringified-JSON validators, Decimal discipline, env-based `extra` policy).
- `source_event_id` for the `market_groups` partial-unique = the Gamma **event id**.
- Lock key for `poll_polymarket_events` distinct from the poll/detect locks (reuse the SETNX owner-token + Lua compare-and-delete release pattern, WR-05).
- Route any event sync through the SAME spike-002 `_derive_status` guard — never a new code path; never settle on `closed=true` alone.
- Capture fresh `GET /events?tag_id=...` + `GET /tags` fixtures before writing parser tests (spike-002 fixtures are single-/markets only). **→ DONE this session (3 fixtures written).**

### Deferred Ideas (OUT OF SCOPE)
- Event settlement (resolve / void / reverse, derived status) — Phase 15.
- Catalog / browse API + house event CRUD — Phase 16.
- Browse UI, event detail, per-outcome rows — Phase 17.
- Seed / demo multi-outcome harness — Phase 18.
- `odds_snapshots` prune / retention task (growth ~23×) — later phase.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CAT-01 | Sync via Gamma `GET /events` (embeds `markets[]` + `tags[]`), replacing top-25-global `/markets` | `GammaClient.fetch_events()` + `sync_events()` (Patterns 1–2 below); live `/events` shape captured + parsed |
| CAT-02 | top-N per category + volume floor; dedup by `conditionId`/event id **before** floor | Curation algorithm (Pattern 3); dedup sets keyed on event `id` + child `conditionId`; floor on `event.volume24hr` post-dedup |
| CAT-03 | Categories from a version-controlled allow-list of ~7 `tag_id`s; unmapped tags logged, never auto-added | `POLYMARKET_CATEGORIES` constant (7 tag_ids verified live); first-by-priority resolver (executed against live data) |
| CAT-04 | Mirrored markets get `category` populated (today always NULL) | `_upsert_one_market(..., category=)` writes `Market.category` + `MarketGroup.category`; Pattern 2 |
| CAT-05 | Resilient: keep last-good on Gamma failure (never blank), cap `limit`=500 + short-page stop, slower cadence | Per-category try/except keep-last-good (Pattern 4); beat @300s; short-page stop (live-verified: Tech=100 events < 500 = single page) |
| CAT-06 | Category with zero qualifying events suppressed at data layer (no categories table) | Derived from `markets.category` COUNT>0; NOTHING to build here beyond not-writing empty categories (Phase 16 reads it) |
| EVT-07 | A `len == 1` event stays standalone (no group created); grouping only for ≥2 outcomes | `if len(parsed.markets) == 1: _upsert_one_market(child, group_id=None, category)`; live single-market fixture captured |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Fetch `/events` per category | Integration (`GammaClient`) | — | HTTP boundary; tenacity retry + bounded pool already live in this class |
| Parse event JSON → typed model | Integration (`schemas.py` Pydantic) | — | spike-002 parser discipline (stringified JSON, Decimal, `_derive_status`) lives here |
| Curation (dedup, floor, top-N, category resolve) | Integration (task `_run_poll_events`) | Adapter | Business rules over fetched data; runs client-side (no `volume_num_min` param on `/events`) |
| Upsert group + children | Integration (`PolymarketAdapter.sync_events`) | DB (`market_groups`, `markets`) | Idempotent ON CONFLICT writes; reuses the proven `(source, source_market_id)` partial-unique |
| Schedule the periodic sync | Celery Beat (`celery_app.beat_schedule`) | Redis (redbeat + SETNX lock) | Beat owns cadence; distinct SETNX lock prevents overlap |
| Category suppression (empty hidden) | DB read (Phase 16, NOT this phase) | — | Derived `SELECT DISTINCT category ... COUNT>0`; this phase only avoids writing empty categories |

## Standard Stack

**Zero new dependencies.** Everything is already a locked dependency in `backend/pyproject.toml`. This phase ADDS code, not packages.

### Core (all already installed — reused)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `httpx` | (installed) | async HTTP to Gamma `/events` | Already the transport in `GammaClient`; just add a method |
| `tenacity` | (installed) | retry/backoff on transient errors | Already wraps `fetch_top_markets`; reuse the exact decorator |
| `pydantic` v2 | (installed) | `GammaEvent`/`GammaTag` parsers | `GammaMarket` is the spike-002-validated template — subclass + sibling |
| `sqlalchemy` 2 async | (installed) | `pg_insert ... on_conflict_do_update` | `sync_top25` already does this on `markets`; add `market_groups` |
| `celery` + `redbeat` | (installed) | `poll_polymarket_events` beat task | `poll_polymarket_top25` is the template; swap in the schedule |
| `redis.asyncio` | (installed) | SETNX ownership-token lock | WR-05 pattern is in `tasks.py` — new lock KEY only |
| `structlog` | (installed) | drift logging (unmapped tags) | Already the logger; `log.warning("gamma.unmapped_tag", ...)` |
| `python-slugify` (`slugify`) | (installed) | event slug from title | `generate_slug` / `_slugify` already in `markets/models.py` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Client-side volume floor | Gamma `volume_num_min` query param | NOT confirmed on `/events` (only `/markets`); ARCHITECTURE.md says filter in adapter. Client-side is deterministic + testable. **Use client-side.** |
| `GammaEventMarket(GammaMarket)` subclass | Add `group_item_title` to `GammaMarket` directly | Either works (additive field). Subclass keeps the legacy `/markets` model unchanged and is cleaner. **Recommend subclass** (verified to parse live data). |
| One `/events` call per category at `limit=top_N` | Page with `offset` | Top-N=10 < 500 ceiling → never paginates in practice (live: even full Tech = 100 events). Single call per category is correct; **still implement the short-page stop for CAT-05 correctness.** |

**Installation:** none. (`uv sync` already covers every import.)

## Package Legitimacy Audit

> Not applicable — this phase installs **zero external packages** (CONTEXT.md: "Zero new dependencies"). Every import is an existing locked dependency already vendored in `backend/uv.lock`. slopcheck gate skipped (no new packages to audit). If the planner discovers a new package is needed, gate it behind `checkpoint:human-verify` before install.

## Live Gamma API Findings (verified this session, 2026-06-05)

> **I reached the live Gamma API.** All findings below are HTTP-200-confirmed, not assumed. Endpoints used: `GET /tags?limit=400`, `GET /tags/slug/{slug}` (×8), `GET /events?tag_id=...`.

### The 7 category tag_ids — PINNED (each via live `GET /tags/slug/{slug}`, HTTP 200)

| Category (human-readable name) | Gamma slug | **tag_id** | Note |
|--------------------------------|-----------|-----------|------|
| Politics | `politics` | **`2`** | label="Politics" |
| Sports | `sports` | **`1`** | label="Sports" |
| Crypto | `crypto` | **`21`** | label="Crypto" |
| Pop Culture | `pop-culture` | **`596`** | Gamma label is **"Culture"**, slug `pop-culture` — store OUR name "Pop Culture" |
| Economy | `economy` | **`100328`** | label="Economy" |
| Tech | `tech` | **`1401`** | label="Tech" |
| World | `world` | **`101970`** | label="World" |

`[VERIFIED: gamma-api.polymarket.com/tags/slug/{slug} — HTTP 200, this session]`

**Re-verify-during-execute command** (cheap, idempotent — confirms IDs haven't drifted before pinning):
```bash
for slug in politics sports crypto pop-culture economy tech world; do
  curl -s "https://gamma-api.polymarket.com/tags/slug/$slug" \
    | python -c "import sys,json; t=json.load(sys.stdin); print(f\"{t['slug']:14} id={t['id']:8} label={t['label']}\")"
done
```
These are **stable, long-lived top-level tags** (Politics id=2 created 2023-10-25, Sports id=1 created 2023-10-24). Drift risk is LOW but the one-time re-verify is free.

### `GET /events` response shape (captured live, Crypto tag_id=21, 176 KB)

Confirmed parameters that work: `?tag_id=21&active=true&closed=false&order=volume24hr&ascending=false&limit=N&offset=N`.

**Event-level fields** (top-level array element):
```
id, ticker, slug, title, description, startDate, endDate,
volume (FLOAT), volume24hr (FLOAT), liquidity (FLOAT), openInterest,
active, closed, archived, negRisk, enableNegRisk, negRiskAugmented,
markets: [ ...nested binary markets... ],
tags:    [ {id, label, slug, forceShow, ...} ]
```
⚠️ **CRITICAL DIVERGENCE FROM `GammaMarket`:** event-level `volume`/`volume24hr`/`liquidity` are **floats**, NOT stringified JSON. (Live: `volume24hr: 1892830.4674290004`.) The nested `markets[]` keep the stringified-string form. So `GammaEvent.volume_24hr` is `float | None` → `_safe_decimal()`; do NOT apply the stringified-JSON validator to event volume.

**Nested `markets[]` child fields** — **identical to `GammaMarket`** (stringified JSON), plus `groupItemTitle`:
```
id, question, conditionId, slug, groupItemTitle, groupItemThreshold,
outcomes ("[\"Yes\", \"No\"]"), outcomePrices ("[\"0.0695\", \"0.9305\"]"),
clobTokenIds (stringified), volume ("465013.72"), volume24hr (float),
liquidity ("31519.83"), closed, active, umaResolutionStatus (null/absent),
endDate, description, negRisk, volumeNum (float — IGNORE), ...80+ fields
```
`[VERIFIED: live /events?tag_id=21, parsed through app.integrations.polymarket.schemas.GammaMarket this session]`

### Empirical proofs (live data, this session)

| Claim | Evidence | Source |
|-------|----------|--------|
| Nested `markets[]` parse through existing `GammaMarket` verbatim | 3 Bitcoin-ladder children → status=OPEN, outcomes=['Yes','No'], volume→Decimal — executed | `[VERIFIED: ran GammaMarket.model_validate on live fixture]` |
| Per-outcome YES prices do NOT sum to 100% | Bitcoin event (14 mk): `[0.0695, 0.0085, ... 0.9915, 0.912, 0.57]`; another (23 mk) sums to ~6.5 (several `1.0` strikes) | `[VERIFIED: live /events]` |
| `outcomePrices` of `"1"`/`"0"` appear on OPEN events | A 23-market OPEN event had several children at `["1", ...]` (already-settled strikes within an active event). The `_derive_status` "has_winner" check keys on **`closed + uma=resolved`**, never price alone, so these do NOT false-trigger RESOLVED. | `[VERIFIED: live /events + schemas.py:88]` |
| len==1 events exist and are dual-tagged | Politics top-20: 2 len==1 events; sample len==1 event ("Iranian regime fall") tagged BOTH `world` (101970) AND `politics` (2) → first-by-priority resolves to **Politics** | `[VERIFIED: live /events?tag_id=2 + executed resolver]` |
| `groupItemTitle` is `""` (empty string) on single-market events, a real label on grouped | Single-market Iran event: `groupItemTitle=""`; Bitcoin ladder children: `"64,000"`, `"66,000"`, `"68,000"` | `[VERIFIED: live /events]` |
| Volume floor rarely filters the top-N | Politics top-20 by volume24hr: 0/20 below the $10k floor. The floor's real job is **suppressing thin categories** (CAT-06), not trimming healthy ones. | `[VERIFIED: live /events?tag_id=2]` |
| Single-page in practice; short-page stop still needed | Tech (1401) total active events at `limit=500` = **100** (< 500 → one page). top-N=10 never paginates. | `[VERIFIED: live /events?tag_id=1401&limit=500]` |
| `/tags` default firehose is noisy | `?limit=400` returns micro-tags: "product marekt fit" (typo, id=101867), "caitlin clark", "virgins", "Viktoria Plzen" — confirms the allow-list-by-slug approach (NEVER iterate raw /tags) | `[VERIFIED: live /tags]` |
| No rate-limit headers exposed | `/events` responses are Cloudflare-fronted; no `RateLimit-*`/`Retry-After` headers. The 500 req/10s budget is documented, not header-advertised. At ~7 req/cycle/300s we use **~0.0047 req/s** — three orders of magnitude under budget. | `[VERIFIED: curl -D - on /events]` + `[CITED: agentbets.ai gamma guide]` |

### Fixtures written this session (ready for execute)

| File | Contents | Exercises |
|------|----------|-----------|
| `backend/tests/fixtures/gamma/events_multi_outcome.json` | 1 Crypto event, 3 trimmed Bitcoin-ladder children, 7 tags (incl. micro-tags) | sync_events grouping, `group_item_title`, category=Crypto, dedup, `volumeNum`-ignored |
| `backend/tests/fixtures/gamma/events_single_market.json` | 1 Politics/World event, `len==1`, `groupItemTitle=""`, dual-tagged world+politics | EVT-07 standalone path, first-by-priority → Politics |
| `backend/tests/fixtures/gamma/tags_categories.json` | the 7 verified category {id,label,slug} | `fetch_tags()` parse test / `POLYMARKET_CATEGORIES` cross-check |

Each fixture intentionally includes the `volumeNum` float variant on children to prove `extra="ignore"` swallows it, and event-level float `volume`/`volume24hr` to prove the float→Decimal path.

## Architecture Patterns

### System Architecture Diagram

```
Celery Beat (redbeat) @ 300s
  └─ poll_polymarket_events  [NEW task; replaces poll-polymarket-top25 in schedule]
       └─ acquire SETNX lock  KEY="xpredict:poll:events:lock"  [NEW key; WR-05 owner-token]
       └─ for cat in POLYMARKET_CATEGORIES (7, ordered by priority):   [config]
       │    ┌── try ──────────────────────────────────────────────────────────────┐
       │    │  raw = GammaClient.fetch_events(tag_id=cat.tag_id, limit=top_N=10)   │ [MODIFIED client]
       │    │       params: active=true, closed=false, order=volume24hr, asc=false │
       │    │       short-page stop: stop when page < limit (CAT-05)               │
       │    │  events = [GammaEvent.model_validate(e) for e in raw]                │ [NEW parser]
       │    │  DEDUP by event.id  (skip events already taken by a higher-priority  │ CAT-02
       │    │        category this cycle — first-by-priority wins)                 │
       │    │  FLOOR: keep events where event.volume24hr >= $10k  (AFTER dedup)    │ CAT-02
       │    │  TOP-N: already ordered by volume24hr; take[:10]                     │ CAT-02
       │    │  await adapter.sync_events(session, events, category=cat.name)       │ [MODIFIED adapter]
       │    │  await session.commit()    # commit per category                     │ CAT-05 keep-last-good
       │    └── except Exception: log + rollback + CONTINUE (this cat keeps last- ─┘ CAT-05
       │         good rows; other categories still sync — never blank the catalog)
       └─ publish per-child odds deltas (REUSED publisher.py, POST-COMMIT, on-change)

sync_events(session, events, category):                    [MODIFIED PolymarketAdapter]
  └─ for ev in events:
       child_conditionIds = dedup within event by child.condition_id   CAT-02
       if len(ev.markets) == 1:                                         EVT-07
            _upsert_one_market(session, ev.markets[0], group_id=None, category)  # standalone
            continue
       group = upsert market_groups ON CONFLICT (source, source_event_id)        CAT-04
               index_where source_event_id IS NOT NULL  [Phase-13 idx 0011]
       for child in ev.markets:
            _upsert_one_market(session, child, group_id=group.id, category)      Pattern 2
               # writes Market.category, Market.group_id, Market.group_item_title

_upsert_one_market(session, parsed, group_id, category):   [EXTRACTED from sync_top25 body]
  └─ pg_insert(Market) ON CONFLICT (source, source_market_id)  [REUSED idx 0004]
       set group_id, group_item_title, category  (+ existing fields)
  └─ upsert YES/NO outcomes (parsed.outcomes_raw[:2])         [REUSED loop verbatim]
  └─ record changed_markets for realtime publish             [REUSED]
```

### Recommended Project Structure (files this phase touches)
```
backend/app/
├── integrations/polymarket/
│   ├── client.py     # + fetch_events()  (+ optional fetch_tags() for the one-off pin)
│   ├── schemas.py    # + GammaEvent, GammaTag, GammaEventMarket(GammaMarket)
│   ├── adapter.py    # extract _upsert_one_market(); + sync_events()
│   └── tasks.py      # + poll_polymarket_events + _run_poll_events + EVENTS_LOCK_KEY
├── celery_app.py     # beat_schedule: drop poll-polymarket-top25, add poll-polymarket-events @300s
└── core/config.py    # + POLYMARKET_CATEGORIES, POLYMARKET_EVENTS_* settings
backend/tests/
├── fixtures/gamma/   # events_multi_outcome.json, events_single_market.json, tags_categories.json  [DONE]
└── polymarket/
    ├── test_schemas.py   # + GammaEvent/GammaTag/GammaEventMarket parse tests
    ├── test_adapter.py   # + sync_events integration tests (grouping, EVT-07, category, dedup)
    ├── test_tasks.py     # + poll_polymarket_events lock + curation + keep-last-good + beat-schedule swap
    └── test_client.py    # + fetch_events param/short-page test (mock httpx)
```

### Pattern 1: `GammaEvent` / `GammaTag` / `GammaEventMarket` parsers (verified design)
**What:** Three Pydantic v2 models modeled on the spike-002 `GammaMarket`. `GammaEventMarket` subclasses `GammaMarket` to inherit ALL the validated quirks and just add `group_item_title`.
**When to use:** Parsing each `/events` array element.
**Verified design (executed against live fixtures this session):**
```python
# backend/app/integrations/polymarket/schemas.py — ADD below GammaMarket
class GammaEventMarket(GammaMarket):
    """A nested /events child market — GammaMarket + the per-outcome label.

    Inherits the spike-002 stringified-JSON validators, _derive_status, Decimal
    discipline, and env-based extra policy VERBATIM. Only adds groupItemTitle.
    """
    group_item_title: str = Field(alias="groupItemTitle", default="")


class GammaTag(BaseModel):
    model_config = _gamma_model_config()   # same env-based extra policy
    id: str
    label: str = ""
    slug: str = ""


class GammaEvent(BaseModel):
    """Pydantic v2 model for one Gamma /events array element."""
    model_config = _gamma_model_config()

    id: str
    slug: str = ""
    title: str = ""
    description: str = ""
    closed: bool = False
    end_date_raw: str | None = Field(alias="endDate", default=None)
    # ⚠️ event-level volume is FLOAT (not stringified) — do NOT use the JSON-list validator
    volume_24hr: float | None = Field(alias="volume24hr", default=None)
    volume_total: float | None = Field(alias="volume", default=None)
    markets: list[GammaEventMarket] = Field(default_factory=list)
    tags: list[GammaTag] = Field(default_factory=list)

    @property
    def volume_24hr_decimal(self) -> Decimal:
        return _safe_decimal(self.volume_24hr)   # reuse the module helper

    @property
    def volume_total_decimal(self) -> Decimal:
        return _safe_decimal(self.volume_total)
```
**Source:** `[VERIFIED: this exact design executed against backend/tests/fixtures/gamma/events_{multi_outcome,single_market}.json via the real schemas module — both parsed, status=OPEN, prices/volume correct]`

**Category resolution helper** (first-by-priority, executed against live data → dual-tagged event resolved to Politics):
```python
def resolve_category(event: GammaEvent, allow_list: list[CategoryEntry]) -> str | None:
    """First allow-listed tag by priority order wins (CAT-03). None if no match."""
    tag_ids = {t.id for t in event.tags}
    for entry in allow_list:               # allow_list is priority-ordered
        if entry.tag_id in tag_ids:
            return entry.name              # human-readable "Politics"
    return None                            # event has no allow-listed tag → skip
# Also: log tags NOT in any allow-list entry for drift (CAT-03 "logged, never auto-added").
```

### Pattern 2: Reuse-the-Upsert — extract `_upsert_one_market`, build `sync_events`
**What:** Lift the per-market upsert body out of `sync_top25` (`adapter.py:196-290`) into a helper; `sync_events` adds only the parent group upsert + the `group_id`/`category` stamp.
**When to use:** The whole sync. `sync_top25` then delegates to the SAME helper (back-compat, tests).
**Concrete refactor target — current `sync_top25` body → `_upsert_one_market`:**
```python
async def _upsert_one_market(
    self,
    session: AsyncSession,
    parsed: GammaMarket,           # GammaMarket OR GammaEventMarket (subclass)
    *,
    group_id: UUID | None,
    category: str | None,
) -> bool:
    """Upsert ONE binary market + its YES/NO outcomes. Returns True on success.

    This is the EXACT body of today's sync_top25 loop, plus three writes:
    group_id, group_item_title (if parsed has it), category. Records
    self.changed_markets for the realtime publish, identically to today.
    """
    # ... deadline parse, slug=f"pm-{parsed.slug}", description ...
    market_values = {
        "source": MarketSourceEnum.POLYMARKET.value,
        "source_market_id": parsed.id,
        "condition_id": parsed.condition_id,
        "question": parsed.question,
        "slug": slug,
        "polymarket_slug": parsed.slug,
        "status": parsed.internal_status.value,
        "volume": parsed.volume,
        "volume_24hr": parsed.volume_24hr_decimal,
        "deadline": deadline,
        "resolution_criteria": description,
        "category": category,                                    # CAT-04 (NEW)
        "group_id": group_id,                                    # EVT-07/grouping (NEW)
        "group_item_title": getattr(parsed, "group_item_title", None),  # NEW
    }
    stmt = pg_insert(Market).values(**market_values).on_conflict_do_update(
        index_elements=["source", "source_market_id"],
        index_where=Market.source_market_id.isnot(None),
        set_={
            "question": ..., "status": ..., "volume": ..., "volume_24hr": ...,
            "polymarket_slug": ...,
            "category": pg_insert(Market).excluded.category,          # NEW
            "group_id": pg_insert(Market).excluded.group_id,          # NEW
            "group_item_title": pg_insert(Market).excluded.group_item_title,  # NEW
            "updated_at": datetime.now(UTC),
        },
    )
    # ... rest identical to sync_top25: fetch market.id, upsert YES/NO outcomes,
    #     flush, append self.changed_markets, IntegrityError→rollback+return False ...


async def sync_events(
    self,
    session: AsyncSession,
    events: list[GammaEvent],
    *,
    category: str,
) -> int:
    """Upsert curated events: 1 market_groups row + N stamped children.

    len(markets)==1 → standalone child (group_id=None), NO group row (EVT-07).
    """
    synced = 0
    for ev in events:
        # dedup children within the event by condition_id (CAT-02 market grain)
        seen: set[str] = set()
        children = [m for m in ev.markets
                    if m.condition_id and not (m.condition_id in seen or seen.add(m.condition_id))]
        if len(children) == 1:                                   # EVT-07
            if await self._upsert_one_market(session, children[0], group_id=None, category=category):
                synced += 1
            continue
        group_id = await self._upsert_market_group(session, ev, category)  # ON CONFLICT (source, source_event_id)
        for child in children:
            if await self._upsert_one_market(session, child, group_id=group_id, category=category):
                synced += 1
    return synced
```

**Parent group upsert** (uses the Phase-13 partial-unique `ix_market_groups_source_source_event_id`):
```python
async def _upsert_market_group(self, session, ev: GammaEvent, category: str) -> UUID:
    slug = f"pm-evt-{_slugify(ev.title, max_length=80)}"[:100] or generate_slug(ev.title)
    values = {
        "source": MarketSourceEnum.POLYMARKET.value,
        "source_event_id": ev.id,                # Gamma event id (CONTEXT discretion)
        "title": ev.title,
        "slug": slug,
        "category": category,                    # CAT-04
    }
    stmt = pg_insert(MarketGroup).values(**values).on_conflict_do_update(
        index_elements=["source", "source_event_id"],
        index_where=MarketGroup.source_event_id.isnot(None),
        set_={"title": ..., "category": ..., "updated_at": datetime.now(UTC)},
    )
    await session.execute(stmt)
    row = await session.execute(
        select(MarketGroup.id).where(
            MarketGroup.source == MarketSourceEnum.POLYMARKET.value,
            MarketGroup.source_event_id == ev.id))
    return row.scalar_one()
```
**Source:** `[VERIFIED: adapter.py:196-299 read; market_groups + ix_market_groups_source_source_event_id confirmed in migration 0011 + models.py:218-230]`. The `MarketGroup` slug is `String(100) UNIQUE NOT NULL` — slugify the event title; on the rare slug collision across different events, fall back to a suffixed slug (mirror `generate_slug`).

### Pattern 3: Curation algorithm (dedup → floor → top-N, cross-category first-wins)
**What:** Inside `_run_poll_events`, per category, in this strict order (CAT-02):
1. `fetch_events(tag_id, limit=top_N)` with `order=volume24hr&ascending=false` (already volume-ranked).
2. **Dedup by event `id`** across the whole cycle — keep a cycle-level `seen_event_ids: set[str]`; because categories iterate in priority order, an event already taken by a higher-priority category is skipped (this IS the first-by-priority guarantee at the event grain). Child `conditionId` dedup happens inside `sync_events`.
3. **Volume floor** AFTER dedup: `[e for e in events if e.volume_24hr_decimal >= POLYMARKET_VOLUME_FLOOR]`.
4. **Top-N:** already ordered → `[:top_N]` (defensive; `limit=top_N` already bounds it).
**Why this order (CAT-02 verbatim):** dedup BEFORE floor avoids Polymarket's documented event-level volume double-counting from inflating a borderline event over the floor. `[CITED: paradigm.xyz/2025/12/polymarket-volume-is-being-double-counted]`
**Note on "first-by-priority":** the locked decision is about the CATEGORY an event lands in (a dual-tagged event → its highest-priority category). Implement by iterating `POLYMARKET_CATEGORIES` in order and skipping any event id already synced this cycle. Live-verified: the World+Politics Iran event → Politics.

### Pattern 4: Keep-last-good PER CATEGORY (CAT-05)
**What:** Wrap each category's fetch+sync+commit in its own try/except. On any exception, log + rollback that category's uncommitted work and `continue`. Other categories proceed; the failed category retains its previously-committed (last-good) rows because the sync NEVER deletes — it only upserts.
**Why per-category (not per-cycle):** CONTEXT locks "keep-last-good is per-category". One category's Gamma 5xx must not abort the other six. Commit per category (not one big commit at the end) so a later category's failure can't roll back an earlier category's successful sync.
```python
for entry in get_settings().POLYMARKET_CATEGORIES:   # priority order
    try:
        raw = await client.fetch_events(tag_id=entry.tag_id, limit=top_n)
        events = curate(raw, seen_event_ids, floor)   # dedup + floor + top-N
        await adapter.sync_events(session, events, category=entry.name)
        await session.commit()                          # commit THIS category
    except Exception as exc:
        log.warning("poll_events.category_failed", category=entry.name, error=str(exc))
        sentry_sdk.capture_exception(exc)
        with contextlib.suppress(Exception):
            await session.rollback()
        continue                                        # keep last-good; next category
```
**Source:** mirrors the existing `_run_poll_sync` error handling (`tasks.py:136-146`), generalized to per-category. `[VERIFIED: tasks.py read]`

### Pattern 5: Beat-schedule swap + distinct lock
**What:** In `celery_app.py`, the `beat_schedule` dict currently has `"poll-polymarket-top25": {schedule: 30.0}`. Replace that ENTRY with `"poll-polymarket-events": {task: "...poll_polymarket_events", schedule: 300.0}`. Keep `snapshot-odds` (300s) and `detect-polymarket-resolutions` (60s) untouched.
**⚠️ Edit-in-place gotcha:** the dict is **assigned literally** at `celery_app.py:48-64`, then `.update()`-ed at line 76. CONTEXT says "never reassign the dict, `.update()` it" — but the top25 entry lives in the **literal assignment** block, so the swap is editing that literal (removing one key, adding another) — NOT a reassignment of the whole `beat_schedule`. Do the swap inside the existing literal at lines 50-53; leave the `reconcile-wallets-nightly` `.update()` block alone.
**Lock:** add `EVENTS_LOCK_KEY = "xpredict:poll:events:lock"` in `tasks.py` (distinct from `LOCK_KEY` and `DETECT_LOCK_KEY`). Reuse `acquire_poll_lock`/`release_poll_lock`'s owner-token+Lua pattern but parameterize the key (or write `acquire_events_lock` mirroring it). TTL should be < 300s (e.g. reuse `POLYMARKET_LOCK_TTL_SECONDS`, or a new `POLYMARKET_EVENTS_LOCK_TTL_SECONDS` default 280) so a crashed task auto-releases before the next 5-min tick.
**Source:** `[VERIFIED: celery_app.py:48-83, tasks.py:41-79 read]`

### Config additions (`core/config.py`, append to the Phase-6 block)
```python
# Phase 14 — Curated Per-Category Gamma Sync (CAT-01..06, EVT-07)
POLYMARKET_EVENTS_POLL_INTERVAL_SECONDS: int = 300   # 5 min (CONTEXT)
POLYMARKET_EVENTS_TOP_N: int = 10                    # events/category (CONTEXT)
POLYMARKET_VOLUME_FLOOR: Decimal = Decimal("10000")  # $10k/event AFTER dedup (CONTEXT)
POLYMARKET_EVENTS_LIMIT_CAP: int = 500               # Gamma ceiling (CAT-05)
POLYMARKET_EVENTS_LOCK_TTL_SECONDS: int = 280        # < 300s tick

# Version-controlled allow-list (CAT-03). PRIORITY ORDER = first-wins on multi-tag.
# tag_ids VERIFIED live 2026-06-05 via GET /tags/slug/{slug}.
POLYMARKET_CATEGORIES: list[CategoryEntry] = [
    CategoryEntry(name="Politics",    slug="politics",    tag_id="2"),
    CategoryEntry(name="Sports",      slug="sports",      tag_id="1"),
    CategoryEntry(name="Crypto",      slug="crypto",      tag_id="21"),
    CategoryEntry(name="Pop Culture", slug="pop-culture", tag_id="596"),
    CategoryEntry(name="Economy",     slug="economy",     tag_id="100328"),
    CategoryEntry(name="Tech",        slug="tech",        tag_id="1401"),
    CategoryEntry(name="World",       slug="world",       tag_id="101970"),
]
```
**Pydantic-settings note:** a `list[CategoryEntry]` (a small frozen dataclass / `BaseModel` / `NamedTuple`) is fine as a Python default in `Settings` since it's NOT env-driven (CONTEXT: "version-controlled Python constant — not env/DB"). Define `CategoryEntry` as a frozen dataclass or module-level constant. Do NOT make it an env var. `Settings.model_config` already has `extra="ignore"` (config.py:35) so this is additive-safe. **Decimal default is already an established pattern** (`SIGNUP_BONUS_AMOUNT: Decimal` at config.py:79).

### `GammaClient.fetch_events()` (client.py — mirror `fetch_top_markets`)
```python
@retry(  # SAME decorator as fetch_top_markets (client.py:47-52)
    retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=1, max=10, jitter=2),
    reraise=True,
)
async def fetch_events(self, *, tag_id: str, limit: int = 10, offset: int = 0) -> list[dict[str, object]]:
    client = self._get_client()
    resp = await client.get("/events", params={
        "active": "true", "closed": "false",
        "tag_id": tag_id, "order": "volume24hr", "ascending": "false",
        "limit": str(min(limit, 500)),    # CAT-05 hard cap
        "offset": str(offset),
    })
    resp.raise_for_status()
    data: list[dict] = resp.json()
    log.info("gamma.fetch_events", tag_id=tag_id, event_count=len(data), limit=limit)
    return data
```
⚠️ **Stale comment fix:** `client.py:7-8` says "Rate limit is 300 req/10s" — that is the **/markets** limit. `/events` is **500 req/10s**. Update the docstring (CONTEXT specifics + research). `[CITED: agentbets.ai gamma guide; docs.polymarket.com]`

### Anti-Patterns to Avoid
- **Iterating the raw `/tags` firehose as categories** — live-confirmed noise ("product marekt fit" typo, "caitlin clark"). Use the 7-entry allow-list by slug ONLY. (PITFALLS Pitfall 5 / Anti-Pattern 2.)
- **Settling on `closed=true` alone / a new status code path** — route every child through the existing `GammaMarket._derive_status`. This phase does NOT settle (Phase 15), but the sync must still derive status via the same model. (spike-002.)
- **`volumeNum` / float volume on children** — use the stringified `volume` → Decimal. The fixtures include `volumeNum` to catch a regression. (spike-002.)
- **Reassigning `beat_schedule`** — edit the literal entry in place; don't rebind the dict.
- **Destructive cleanup of orphaned top-25 rows** — CONTEXT locks "left intact". Sync only upserts.
- **Summing event volume across categories before dedup** — inflates the floor (Polymarket double-count). Dedup by event id first.
- **`limit > 500` or no short-page stop** — 500 is the ceiling; stop on a short page even though top-N=10 never reaches it (correctness, not perf).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Stringified-JSON / Decimal / status parsing | A new event parser from scratch | `GammaEventMarket(GammaMarket)` subclass | spike-002 already solved every quirk; subclass inherits + verified live |
| Idempotent group upsert | Manual SELECT-then-INSERT | `pg_insert(...).on_conflict_do_update(index_elements=["source","source_event_id"])` | Phase-13 migration 0011 already created the partial-unique index FOR this |
| Idempotent child upsert | New upsert logic | `_upsert_one_market` (extracted `sync_top25` body) | The `(source, source_market_id)` index (0004) already guarantees it |
| Overlap prevention | A new lock scheme | `acquire_poll_lock` owner-token + Lua release (WR-05), new KEY | Race-correct release already validated; just a distinct key |
| Retry/backoff on 5xx | A retry loop | the existing tenacity decorator on `fetch_top_markets` | Identical transient-error policy; copy the decorator |
| Slug generation | String munging | `_slugify` / `generate_slug` (`models.py:33`) | Already handles max_length + collision-suffix |
| Category derivation read | A categories table | derive `SELECT DISTINCT category FROM markets ... HAVING COUNT>0` (Phase 16) | CONTEXT: no authoritative categories table |

**Key insight:** This phase is ~90% reuse. The genuinely NEW code is: `GammaEvent`/`GammaTag` (~40 LOC), `fetch_events` (~15 LOC), `_upsert_market_group` (~20 LOC), the `sync_events` loop (~25 LOC), the `_run_poll_events` curation loop (~40 LOC), config (~15 LOC). Everything else is extracting or copying proven code.

## Runtime State Inventory

> This phase WRITES new runtime state but does not rename/migrate existing state. Included for completeness because it changes what the running system ingests.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `markets` rows: existing top-25 mirrored markets stay (CONTEXT: left intact). NEW `market_groups` rows + `Market.category`/`group_id`/`group_item_title` populated by this sync. Phase 13 created the empty `market_groups` table; THIS phase is its first writer. | Code edit (sync writes). NO data migration — additive upsert; orphaned top-25 rows untouched. |
| Live service config | **Celery Beat schedule (redbeat — stored in Redis, NOT git).** Swapping `poll-polymarket-top25`→`poll-polymarket-events` in `celery_app.py` changes the code, but **redbeat persists the schedule in Redis** and reloads on beat restart. The dropped `poll-polymarket-top25` redbeat key may linger in Redis until beat restarts. | Restart the beat process after deploy so redbeat reloads the new schedule. (Local dev: `docker compose restart` the beat service; see [[xprediction-local-runtime-recipe]].) The dropped entry is harmless (its task still importable) but won't fire once removed from the schedule + beat restart. |
| OS-registered state | None — no OS-level registration. Beat runs in a container. | None — verified (no Task Scheduler / launchd / systemd involvement). |
| Secrets/env vars | None new. Gamma API needs no auth (`client.py:7`). New settings (`POLYMARKET_*`, `POLYMARKET_CATEGORIES`) are **code constants**, not secrets — no `.env` change. | None. |
| Build artifacts | None — pure Python source change, zero new deps, no compiled artifact. `uv.lock` unchanged. | None. |

**The canonical question — what runtime state survives a code-only deploy?** The **redbeat schedule in Redis**. Without a beat restart, the old `poll-polymarket-top25` could keep firing from the persisted Redis schedule. The plan MUST include a beat-restart step (or document it in the deploy notes) so the schedule swap actually takes effect.

## Common Pitfalls

### Pitfall 1: Event volume is FLOAT, child volume is STRING (mixed encoding)
**What goes wrong:** Applying the stringified-JSON list validator to `event.volume24hr` (a float) fails or returns `[]`; or worse, parsing it as a string drops precision.
**Why it happens:** `GammaMarket` trained the team to expect stringified everything. `/events` event-level numerics are raw floats (`volume24hr: 1892830.4674290004`) while nested `markets[]` stay stringified.
**How to avoid:** `GammaEvent.volume_24hr: float | None` + `_safe_decimal()` property (NO list validator on it). Children use `GammaEventMarket` (inherits the string→Decimal path). `[VERIFIED live this session.]`
**Warning signs:** `volume_24hr_decimal` always 0; floor filters everything; a `ValidationError` on event volume.

### Pitfall 2: `closed=true` / settling on price alone (carry forward spike-002)
**What goes wrong:** A child with `outcomePrices` containing `"1"` is treated as resolved even though the event is OPEN (live-confirmed: OPEN events contain `1.0` strike children).
**Why it happens:** "price 1 = winner" is the naive read. The real guard is `closed + umaResolutionStatus="resolved" + clear winner`.
**How to avoid:** Route every child through `GammaMarket._derive_status` (inherited by `GammaEventMarket`). This phase does NOT settle (Phase 15), but it must still derive `status` via the same model so the stored `Market.status` is correct. NEVER add a new status path. `[VERIFIED: schemas.py:58-95 + live OPEN-event-with-1.0-strike data.]`
**Warning signs:** A mirrored child stored as RESOLVED inside an active event; tests on `events_multi_outcome.json` showing non-OPEN status.

### Pitfall 3: `len==1` event silently creates an empty-feeling group (EVT-07)
**What goes wrong:** A single-market event ("Will the Iranian regime fall?") gets a `market_groups` row with one child — violating EVT-07 and creating a degenerate "event" in the catalog.
**Why it happens:** Treating every `/events` element uniformly. Many Polymarket "events" wrap a single binary.
**How to avoid:** `if len(deduped_children) == 1: _upsert_one_market(child, group_id=None, category); continue` — no group row. `[VERIFIED: events_single_market.json captured live, `groupItemTitle=""`.]`
**Warning signs:** `market_groups` rows with exactly one child; the single-market fixture creating a group in tests.

### Pitfall 4: Cross-category duplicate events double-synced (CAT-02 + first-wins)
**What goes wrong:** The Iran event is tagged BOTH World and Politics. Without cycle-level event-id dedup, it syncs under World AND Politics — duplicate catalog entry, category flip-flop on `category` last-writer-wins.
**Why it happens:** Each category fetch is independent; the same event surfaces under multiple allow-listed tags.
**How to avoid:** Cycle-level `seen_event_ids: set[str]`; iterate `POLYMARKET_CATEGORIES` in priority order; skip any event id already synced this cycle. This gives first-by-priority (Politics before World) for free. `[VERIFIED: live dual-tagged event + executed resolver → Politics.]`
**Warning signs:** Same `source_event_id` updated twice per cycle with different categories; an event appearing in two category tabs (Phase 16/17).

### Pitfall 5: redbeat schedule not reloaded after the swap
**What goes wrong:** Code drops `poll-polymarket-top25`, but the running beat keeps firing it from the Redis-persisted redbeat schedule; `poll-polymarket-events` never starts.
**Why it happens:** redbeat stores the schedule in Redis (`celery_app.py:46-47`) and loads on beat start — a code change alone doesn't re-sync it.
**How to avoid:** Restart the beat process on deploy. Document in the plan's deploy notes. `[VERIFIED: celery_app.py beat_scheduler=RedBeatScheduler.]`
**Warning signs:** top-25 markets still updating post-deploy; no `market_groups` rows appearing; `poll_complete` logs but no `poll_events` logs.

### Pitfall 6: `MarketGroup.slug` uniqueness collision
**What goes wrong:** Two different events slugify to the same `pm-evt-...` slug → `IntegrityError` on the UNIQUE slug index (`models.py:248-253`), aborting the group upsert.
**Why it happens:** `slug` is `String(100) UNIQUE NOT NULL`; truncation at 100 chars can collide; ON CONFLICT is on `(source, source_event_id)`, NOT on slug, so a slug clash isn't absorbed by the upsert.
**How to avoid:** On `IntegrityError` for the slug, fall back to a suffixed slug (mirror `generate_slug`'s `-{uuid hex[:6]}`). Or pre-suffix with a short hash of `source_event_id`. Test with two events sharing a title prefix.
**Warning signs:** Group upsert `IntegrityError` on `ix_market_groups_slug`; an event failing to group while its siblings sync.

## Code Examples

### Loading the new fixtures in tests (mirror the existing loader)
```python
# backend/tests/polymarket/conftest.py — ADD (loader already exists at line 13)
@pytest.fixture
def gamma_events_multi() -> list[dict]:
    return load_gamma_fixture("events_multi_outcome")   # returns a LIST (events array)

@pytest.fixture
def gamma_events_single() -> list[dict]:
    return load_gamma_fixture("events_single_market")

@pytest.fixture
def gamma_tags_categories() -> list[dict]:
    return load_gamma_fixture("tags_categories")
```
⚠️ `load_gamma_fixture` returns `json.loads(...)` which for these fixtures is a **list**, not a dict (the existing fixtures are single dicts). The loader works unchanged; just the return type differs. `[VERIFIED: conftest.py:13-16.]`

### Parser unit test (modeled on `test_schemas.py::TestGammaMarketParser`)
```python
def test_gamma_event_multi_outcome(gamma_events_multi):
    ev = GammaEvent.model_validate(gamma_events_multi[0])
    assert ev.id == "538337"
    assert len(ev.markets) == 3
    assert isinstance(ev.volume_24hr_decimal, Decimal)        # float→Decimal
    assert ev.markets[0].group_item_title == "64,000"          # subclass field
    assert ev.markets[0].internal_status == MarketStatus.OPEN  # inherited _derive_status
    assert ev.markets[0].outcomes_raw == ["Yes", "No"]         # inherited validator

def test_gamma_event_single_market_stays_standalone(gamma_events_single):
    ev = GammaEvent.model_validate(gamma_events_single[0])
    assert len(ev.markets) == 1
    assert ev.markets[0].group_item_title == ""                # empty label

def test_category_first_by_priority(gamma_events_single):
    # Iran event tagged BOTH world(101970) AND politics(2) → Politics wins
    ev = GammaEvent.model_validate(gamma_events_single[0])
    assert resolve_category(ev, POLYMARKET_CATEGORIES) == "Politics"
```

### sync_events integration test (mirror `test_adapter.py::TestAdapterIntegration`)
```python
@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_sync_events_groups_multi_outcome(async_session, gamma_events_multi):
    adapter = PolymarketAdapter()
    events = [GammaEvent.model_validate(e) for e in gamma_events_multi]
    n = await adapter.sync_events(async_session, events, category="Crypto")
    assert n == 3                                              # 3 children
    # 1 market_groups row, source_event_id=538337
    grp = (await async_session.execute(
        select(MarketGroup).where(MarketGroup.source_event_id == "538337"))).scalar_one()
    assert grp.category == "Crypto"
    # children stamped
    kids = (await async_session.execute(
        select(Market).where(Market.group_id == grp.id))).scalars().all()
    assert len(kids) == 3
    assert all(k.category == "Crypto" for k in kids)
    assert {k.group_item_title for k in kids} == {"64,000", "66,000", "68,000"}

@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_sync_events_single_market_no_group(async_session, gamma_events_single):
    adapter = PolymarketAdapter()
    events = [GammaEvent.model_validate(e) for e in gamma_events_single]
    await adapter.sync_events(async_session, events, category="Politics")
    # NO market_groups row for a len==1 event (EVT-07)
    grp = (await async_session.execute(
        select(MarketGroup).where(MarketGroup.source_event_id == "108634"))).scalar_one_or_none()
    assert grp is None
    # the lone market is standalone (group_id IS NULL) with category populated
    m = (await async_session.execute(
        select(Market).where(Market.source_market_id == "958443"))).scalar_one()
    assert m.group_id is None and m.category == "Politics"

async def test_sync_events_idempotent(async_session, gamma_events_multi):
    adapter = PolymarketAdapter()
    events = [GammaEvent.model_validate(e) for e in gamma_events_multi]
    await adapter.sync_events(async_session, events, category="Crypto")
    await adapter.sync_events(async_session, events, category="Crypto")   # replay
    grps = (await async_session.execute(
        select(MarketGroup).where(MarketGroup.source_event_id == "538337"))).scalars().all()
    assert len(grps) == 1                                      # no duplicate group
```

### Curation + keep-last-good unit test (mock client, no DB)
```python
@pytest.mark.unit
async def test_poll_events_keeps_last_good_per_category():
    """One category's fetch raising must NOT abort the others (CAT-05)."""
    redis = AsyncMock(); redis.set = AsyncMock(return_value=True); redis.eval = AsyncMock(); redis.aclose = AsyncMock()
    mock_client = AsyncMock(); mock_client.close = AsyncMock()
    # Politics raises, Crypto succeeds → Crypto still syncs
    mock_client.fetch_events = AsyncMock(side_effect=[httpx.NetworkError("boom"), []])
    # ... patch GammaClient + adapter, assert sync_events called for Crypto, rollback for Politics ...

@pytest.mark.unit
def test_beat_schedule_swapped():
    from app.celery_app import celery_app
    sched = celery_app.conf.beat_schedule
    assert "poll-polymarket-top25" not in sched                # dropped
    assert sched["poll-polymarket-events"]["schedule"] == 300.0
    assert sched["poll-polymarket-events"]["task"] == "app.integrations.polymarket.tasks.poll_polymarket_events"
    assert sched["snapshot-odds"]["schedule"] == 300.0         # untouched
    assert sched["detect-polymarket-resolutions"]["schedule"] == 60.0  # untouched
```
⚠️ **Update the existing `test_tasks.py::test_beat_schedule_entries`** (lines 128-144) — it currently asserts `"poll-polymarket-top25" in schedule`. After the swap that assertion INVERTS. The plan must edit this test, not just add a new one.

## State of the Art

| Old Approach (top-25 global) | Current Approach (this phase) | When Changed | Impact |
|------------------------------|-------------------------------|--------------|--------|
| `GET /markets?order=volume24hr&limit=25` | `GET /events?tag_id=...&order=volume24hr&limit=10` per category | Phase 14 | Curated, categorized, grouped; `Market.category` finally populated |
| Flat list, no grouping | `market_groups` parent + stamped children | Phase 13 schema + Phase 14 writer | Multi-outcome events represented |
| `poll_polymarket_top25` @30s | `poll_polymarket_events` @300s | Phase 14 | Slower, gentler on Gamma; odds poll stays separate |
| Single global call, no dedup | Per-category, cross-category event-id dedup, volume floor | Phase 14 | First-by-priority categories; no double-count |

**Deprecated/outdated in the codebase:**
- `client.py:7-8` docstring "Rate limit is 300 req/10s" — that's `/markets`; `/events` is 500/10s. Fix the comment.
- `poll_polymarket_top25` — removed from the beat schedule (kept as an importable function for tests/back-compat).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The 7 tag_ids remain valid at execute time (verified 2026-06-05, but execute may run days later) | Live API Findings | LOW — these are stable 2023-era top-level tags; the one-line re-verify command catches drift before pinning. Mitigated. |
| A2 | `groupItemTitle` should be added via a `GammaEventMarket(GammaMarket)` subclass rather than on `GammaMarket` itself | Pattern 1 | NONE — both compile; this is a style choice. Either is correct. |
| A3 | "First-by-priority" applies at the **event/category** grain (a dual-tagged event → highest-priority category), implemented via cycle-level event-id dedup in priority order | Pattern 3 / Pitfall 4 | LOW — CONTEXT says "when an event carries multiple allow-listed tags, the first by priority wins" → this is the literal reading. If the planner/discuss intended per-market category, revisit; but events (not markets) carry the `tags[]`, so event-grain is the only coherent interpretation. |
| A4 | `MarketGroup.slug` collisions are rare and a `generate_slug`-style suffix fallback is acceptable | Pitfall 6 | LOW — slugs are 100-char event titles; collision is unlikely but possible. The fallback is the same pattern markets already use. |
| A5 | A beat restart is acceptable as the mechanism to reload the redbeat schedule | Runtime State / Pitfall 5 | LOW — standard redbeat operational practice; the existing deploy already restarts services. |

**All tag_id values and the entire parser design were VERIFIED against the live API this session — they are NOT in this assumptions table.** Only the items above carry residual risk, all LOW.

## Open Questions (RESOLVED)

1. **Should the volume floor use `event.volume24hr` or `event.volume` (total)?** — **RESOLVED: floor on `volume24hr` (operator decision, CONTEXT 2026-06-05; all 4 plans implement it).**
   - What we know: CONTEXT says "Volume floor = $10,000 **total** volume per event" but ALSO "rank by **volume24hr**". Live data: `event.volume` (total) is much larger than `event.volume24hr` (e.g. Iran event total=48.5M vs 24hr=582k).
   - What's unclear: "total volume per event" literally reads as `event.volume` (lifetime), but the ranking metric is `volume24hr`. A $10k floor on lifetime `volume` is trivially passed by almost everything; a $10k floor on `volume24hr` is the meaningful credibility gate.
   - Recommendation: **Floor on `volume24hr`** (consistent with the ranking metric and the "credible/fresh" intent; live-verified that top-N-by-volume24hr events comfortably clear $10k while thin categories won't). Flag for the planner to confirm against the locked wording. Expose both `volume_24hr_decimal` and `volume_total_decimal` on `GammaEvent` so the choice is a one-line change.

2. **`MarketGroup` has no `volume`/`deadline`/`status` columns — does sync need them?**
   - What we know: migration 0011 / `models.py` deliberately OMITS money + status columns from `MarketGroup` (EVT-06: status derived in Phase 15; no money column to keep `lint_money_columns.py` green).
   - What's unclear: nothing blocking — `sync_events` only writes `title`, `slug`, `source`, `source_event_id`, `category`. Event-level volume lives on the children + is re-derivable.
   - Recommendation: Write ONLY the columns that exist. Do not add columns (that's a schema change = Phase 13 territory, already shipped). Confirmed safe.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Gamma API (`gamma-api.polymarket.com`) | live sync at runtime; fixture capture | ✓ | n/a (public, no auth) | Fixtures already captured for tests; keep-last-good covers runtime outages |
| `uv` + Python 3.12 venv | running backend + tests | ✓ | 3.12 | — (verified: `uv run python` executed this session) |
| Docker / testcontainers | integration tests (`async_session` fixture) | ✓ on Linux CI; ⚠ flaky on this Windows worktree | Postgres 16-alpine | Run integration tests PER-MODULE locally; trust Linux CI for the full suite |
| Postgres 16 + `market_groups` table | sync writes | ✓ | 16 | — (Phase 13 migration 0011 shipped + merged) |
| Redis | redbeat schedule + SETNX lock | ✓ | (compose) | fakeredis for unit tests (`conftest.py:80`) |

**Missing dependencies with no fallback:** none — every dependency is present.
**Missing dependencies with fallback:** Windows-worktree testcontainers flake → per-module local runs + Linux CI (see Validation Architecture).

## Validation Architecture

> nyquist_validation is enabled (no `workflow.nyquist_validation: false` in config). Section included.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio + testcontainers (Postgres 16-alpine) + fakeredis |
| Config file | `backend/pyproject.toml` (pytest config) + `backend/tests/conftest.py` (fixtures) |
| Quick run command (unit, no Docker) | `cd backend && uv run pytest tests/polymarket/ -m unit -x` |
| Per-module integration (the reliable local gate) | `cd backend && uv run pytest tests/polymarket/test_adapter.py -x` |
| Full suite command (TRUST LINUX CI, do NOT gate locally) | `cd backend && uv run pytest tests/ -x` |

### ⚠️ Windows-worktree test policy (CRITICAL — from CONTEXT + memory)
This is a Windows git-worktree. The FULL `uv run pytest` suite **flakes here** (testcontainers connection contention across UNRELATED modules) and `ruff check`/`format` results flip-flop (file set flickers 148↔202). **Linux CI runs the full suite + ruff + mypy GREEN.** Therefore:
- **Local acceptance gate = PER-MODULE runs** (`tests/polymarket/test_schemas.py`, `test_adapter.py`, `test_tasks.py`, `test_client.py` individually).
- **Do NOT plan the full `pytest tests/` suite as a local acceptance gate.** Use it only on Linux CI.
- Unit tests (`-m unit`) need NO Docker and are always reliable locally — prefer them for the fast inner loop.
- See [[xprediction-backend-fullsuite-testcontainers-flake]] + STATE.md note.

### Phase Success Criterion → Test Map
| SC | Behavior | Test Type | Automated Command | File Exists? |
|----|----------|-----------|-------------------|-------------|
| SC#1 | `market_groups` + grouped children appear in DB from `/events`; `poll_polymarket_top25`→`poll_polymarket_events` in beat @300s | integration + unit | `pytest tests/polymarket/test_adapter.py::test_sync_events_groups_multi_outcome -x` ; `pytest tests/polymarket/test_tasks.py::test_beat_schedule_swapped -x` | ❌ Wave 0 (both new) |
| SC#2 | top-N-per-category vs allow-list; dedup by conditionId/event-id BEFORE floor; limit≤500 + short-page stop; unmapped tags logged | unit | `pytest tests/polymarket/test_tasks.py -m unit -x` (curation order, dedup, floor, short-page, drift-log) ; `pytest tests/polymarket/test_client.py::test_fetch_events_caps_limit -x` | ❌ Wave 0 |
| SC#3 | mirrored markets carry populated `category`; empty category suppressed at data layer | integration | `pytest tests/polymarket/test_adapter.py::test_sync_events_groups_multi_outcome -x` (asserts `category=="Crypto"` on group+children). Empty-suppression is a Phase-16 READ; here assert sync simply never writes a category with 0 events (no-op test). | ❌ Wave 0 |
| SC#4 | Gamma failure keeps last-good (never blanks); `len==1` stays standalone (no group) | unit + integration | `pytest tests/polymarket/test_tasks.py::test_poll_events_keeps_last_good_per_category -x` ; `pytest tests/polymarket/test_adapter.py::test_sync_events_single_market_no_group -x` | ❌ Wave 0 |
| (parser) | `GammaEvent`/`GammaTag`/`GammaEventMarket` parse; float→Decimal; inherited status/validators; first-by-priority category | unit | `pytest tests/polymarket/test_schemas.py -m unit -x` | ❌ Wave 0 (extend existing file) |

### Sampling Rate
- **Per task commit:** `cd backend && uv run pytest tests/polymarket/ -m unit -x` (fast, no Docker).
- **Per wave merge:** per-module integration — `uv run pytest tests/polymarket/test_adapter.py tests/polymarket/test_tasks.py -x` (Docker, one module set).
- **Phase gate:** Linux CI `backend` job green (full `pytest tests/` + ruff + mypy). **Not** the Windows worktree.

### Wave 0 Gaps
- [x] `backend/tests/fixtures/gamma/events_multi_outcome.json` — captured live (DONE this session)
- [x] `backend/tests/fixtures/gamma/events_single_market.json` — captured live (DONE this session)
- [x] `backend/tests/fixtures/gamma/tags_categories.json` — the 7 verified tag_ids (DONE this session)
- [ ] `tests/polymarket/conftest.py` — add `gamma_events_multi` / `gamma_events_single` / `gamma_tags_categories` fixtures (loader already exists)
- [ ] `tests/polymarket/test_schemas.py` — add `GammaEvent`/`GammaTag`/`GammaEventMarket` + first-by-priority tests (covers parser)
- [ ] `tests/polymarket/test_adapter.py` — add `sync_events` grouping / EVT-07 / category / dedup / idempotency tests (covers SC#1, SC#3, SC#4)
- [ ] `tests/polymarket/test_tasks.py` — add `poll_polymarket_events` lock + curation + keep-last-good + **edit `test_beat_schedule_entries`** (covers SC#2, SC#4, SC#1)
- [ ] `tests/polymarket/test_client.py` — add `fetch_events` params + limit-cap test
- No framework install needed (pytest infra already present).

## Security Domain

> `security_enforcement` not set to false → included. This is a backend ingestion phase with no auth/session/user-input surface (it consumes a public read-only API and writes internal rows), so most ASVS categories are N/A.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Gamma API is public, no auth (`client.py:7`); no user auth in this path |
| V3 Session Management | no | No sessions; Celery beat task |
| V4 Access Control | no | No user-facing endpoint; internal sync only |
| V5 Input Validation | **yes** | Pydantic v2 `GammaEvent`/`GammaTag` with `extra="ignore"` (dev) / `"allow"` (prod) — untrusted external JSON is parsed through validated models; stringified JSON via `json.loads` with try/except (never `eval`); `_safe_decimal` swallows malformed numerics. `model_config` rejects nothing into business logic (T-06-01). |
| V6 Cryptography | no | No crypto in this path (no secrets, no tokens) |

### Known Threat Patterns for {Gamma ingestion}
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malformed/oversized Gamma JSON crashes the task | Denial of Service | tenacity retry + bounded httpx pool (10 conns) + 15s timeout; per-category try/except keep-last-good (a poisoned category can't down the others) |
| Injected/unexpected API fields reach business logic | Tampering | `extra="ignore"`/`"allow"` policy — unknown fields never bind to model attrs (spike-002 T-06-01) |
| Stringified-JSON parse turning into code exec | Tampering / RCE | `json.loads` ONLY (never `eval`); the validator catches `JSONDecodeError`→`[]` |
| Decimal precision loss → wrong volume floor / payouts downstream | Tampering | string→`Decimal` via `_safe_decimal`; never `volumeNum` float (spike-002) |
| Slopsquatted dependency | Supply chain | N/A — zero new packages this phase |

## Sources

### Primary (HIGH confidence)
- **Live Gamma API, this session (2026-06-05):** `GET /tags/slug/{politics,sports,crypto,pop-culture,economy,tech,world}` (HTTP 200 each → 7 tag_ids pinned); `GET /events?tag_id={21,2,1401}` (nested `markets[]`+`tags[]` shape, float event volume, dual-tagged events, len==1 events, OPEN-event 1.0-strikes, short-page proof); `GET /tags?limit=400` (firehose noise confirmed).
- **Executed verification, this session:** prototype `GammaEvent`/`GammaTag`/`GammaEventMarket` run through `app.integrations.polymarket.schemas` against the captured fixtures via `uv run python` — parse + first-by-priority resolver confirmed.
- **Real backend code (read this session):** `client.py`, `adapter.py`, `schemas.py`, `tasks.py`, `celery_app.py`, `core/config.py`, `markets/models.py` (incl. `MarketGroup`), `markets/enums.py`, `db/types.py`, migration `0011_phase13_market_groups.py`, `tests/conftest.py`, `tests/polymarket/{conftest,test_adapter,test_schemas,test_tasks}.py`, existing `tests/fixtures/gamma/*.json`.
- **Milestone research (HIGH):** `research/SUMMARY.md` (Phase 2 Sync + Research Flags), `research/ARCHITECTURE.md` (Pattern 3 Reuse-the-Upsert, sync data flow, `/events` contract), `research/PITFALLS.md` (Pitfall 4 pagination/dedup, Pitfall 5 tag drift).
- **Spike findings:** `.claude/skills/spike-findings-xpredict/references/polymarket-integration.md` (spike-002 parser quirks, closed≠resolved).

### Secondary (MEDIUM confidence)
- `[CITED: agentbets.ai/guides/polymarket-gamma-api-guide]` — `/events` 500 req/10s, limit ceiling 500 (cross-checked with docs.polymarket.com).
- `[CITED: paradigm.xyz/2025/12/polymarket-volume-is-being-double-counted]` — event-level volume double-counting (motivates dedup-before-floor).
- `[CITED: docs.polymarket.com/developers/gamma-markets-api/get-events]` — `/events` params (tag_id, order, ascending, active, closed, limit, offset).

### Tertiary (LOW confidence)
- (none — every load-bearing claim is HIGH, verified live or in-code this session.)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new deps; every import verified present + the parser design executed.
- Live API (tag_ids, `/events` shape): HIGH — HTTP-200-confirmed this session, fixtures captured + parsed.
- Architecture (sync_events, upsert reuse): HIGH — anchored to read code + the shipped Phase-13 schema; the upsert pattern is already proven in `sync_top25`.
- Pitfalls: HIGH — each backed by live data or read code (mixed encoding, OPEN 1.0-strikes, len==1, dual-tag, redbeat reload).
- Test strategy: HIGH — mirrors existing `tests/polymarket/*` patterns; Windows-worktree policy from CONTEXT + memory.

**Research date:** 2026-06-05
**Valid until:** ~2026-07-05 for the tag_ids (stable top-level tags; re-verify command provided) / 2026-06-19 for the `/events` shape (fast-moving API surface, though core fields are long-stable). Re-run the tag_id verify loop at execute start regardless.
