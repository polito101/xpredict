# Phase 6: Polymarket Sync (Catalog Replication) - Research

**Researched:** 2026-05-28
**Domain:** External API integration (Polymarket Gamma), Celery Beat scheduling, Pydantic v2 parsing, frontend market list
**Confidence:** HIGH

## Summary

Phase 6 integrates the Polymarket Gamma REST API into XPredict by implementing a `PolymarketAdapter` that conforms to the existing `MarketSource` Protocol from Phase 4, adds two Celery Beat tasks (poll every 30s, snapshot every 5min), and delivers the first player-facing market list on the home page. The spike (002) already validated the core parser, state machine, and VCR fixtures -- this phase productionizes those patterns into the established codebase architecture.

The Gamma API at `https://gamma-api.polymarket.com/markets` is public (no auth), returns JSON with 50+ fields per market, and has a verified rate limit of 300 req/10s on the `/markets` endpoint [CITED: docs.polymarket.com/quickstart/introduction/rate-limits]. Our top-25 poll fires 2 req/min, well under that limit. The critical integration risk is schema drift: Gamma API fields use stringified JSON for arrays (`outcomes`, `outcomePrices`, `clobTokenIds`), mixed string/float encoding for numeric values, and the `umaResolutionStatus` field is absent (not null) when no UMA process has started. All of these quirks are already handled by the spike-validated Pydantic parser.

The frontend work replaces the Phase 1 scaffold placeholder on the home page with a responsive grid of `MarketCard` components using shadcn/ui Card + Badge + Skeleton primitives. A UI-SPEC (`06-UI-SPEC.md`) already exists with the full visual contract.

**Primary recommendation:** Port the spike-002 `GammaMarket` parser and `_derive_status` state machine directly into `app/integrations/polymarket/schemas.py`, wrap Gamma HTTP calls in an `httpx.AsyncClient` singleton with `tenacity` retry, and register `PolymarketAdapter` in the existing `REGISTRY`. Add `volume` and `volume_24hr` columns to the `markets` table via migration 0004. The frontend is a straightforward Server Component consuming the existing `/api/v1/markets` endpoint (modified to return mixed house+mirrored results with house-first sorting).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01: House markets first, then Polymarket by volume** -- The home page list shows all open house markets first (sorted by `created_at` desc), followed by the current top-25 Polymarket mirrored markets sorted by 24h volume desc. This ensures the operator's own markets always have prominence over mirrored content.
- **D-02: Badge discreto** -- Small chip positioned bottom-right of each market card. Polymarket markets show "Polymarket" text with a link to the original market on polymarket.com. House markets show "House" without link. The badge should not distract from the main card content (question, odds, volume).
- **D-03: Top-25 rotation with DB persistence** -- Each 30s poll fetches the current top-25 from Polymarket and upserts them into our DB. The player home page list shows only the current top-25 active mirrored markets (whatever the latest poll returned). Markets that fall out of the top-25 remain in DB (they may have bets from Phase 5+) but do not appear on the home page.
- **D-04: Portfolio visibility for dropped markets** -- Markets with active bets remain accessible via the player's portfolio (Phase 5+) and via direct URL to the market detail page (Phase 9), even if they no longer appear on the home page. No market data is ever deleted.

### Claude's Discretion
- Gamma client architecture: httpx.AsyncClient lifecycle, tenacity retry policy (backoff, jitter, max retries), timeout values, connection pooling strategy
- Redis dedupe lock: TTL, key pattern, auto-expiry for crashed tasks
- Pydantic parser configuration: `extra='forbid'` in dev vs `extra='allow'` + warning log in staging -- toggled by `ENVIRONMENT` env var (follows Phase 2 D-06 pattern)
- Market card layout: follow shadcn/ui Card component conventions, display question, YES/NO odds, deadline, volume, source badge
- Slug generation for mirrored markets: follow Phase 4's `generate_slug()` pattern from question text
- Migration naming: `0004_phase6_polymarket_sync.py` or appropriate sequence number
- Test organization: `backend/tests/polymarket/` and/or `backend/tests/integrations/` following existing patterns
- VCR fixture strategy for testing against Gamma API responses (spike 002 fixtures available)

### Deferred Ideas (OUT OF SCOPE)
- **Market search and categories** -- player can search/filter beyond top-25 visible on home. Future phase (possibly Phase 9 UX Polish or a dedicated phase).
- **Full Polymarket catalog copy with in-house bets** -- user wants all bets internal, not depending on Polymarket economy. Requires data model redesign. v2.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MKT-01 | Player sees market list on home page: top-25 active Polymarket-mirrored markets + all open house markets, sorted by 24h volume | Modified public market list endpoint + new frontend `MarketList` Server Component; house-first sorting per D-01 |
| MKT-02 | Each market card displays question, current YES/NO odds, deadline, total volume, and source badge | `MarketCard` component per UI-SPEC; new `volume`, `volume_24hr` columns on `markets` table; `source_url` for badge link |
| MKT-05 | System polls Polymarket Gamma API every 30s for top-25 active markets via Celery Beat; deduped with Redis distributed lock | `poll_polymarket_top25` Beat task + Redis SETNX lock; httpx + tenacity Gamma client |
| MKT-06 | System snapshots odds for all open markets every 5 minutes for price history chart | `snapshot_odds` Beat task; writes `OddsSnapshot` rows per Outcome for all open markets (both house + mirrored) |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Gamma API polling | API / Backend (Celery worker) | -- | Server-side periodic task; never call external APIs from the browser |
| Market upsert + dedup | API / Backend | Database / Storage | UPSERT logic in service layer; `(source, source_market_id)` uniqueness at DB level |
| Odds snapshot capture | API / Backend (Celery worker) | Database / Storage | Periodic Celery task writes to `odds_snapshots` table |
| Market list (home page) | Frontend Server (SSR) | API / Backend | Next.js Server Component fetches from internal API at render time |
| Market card UI | Browser / Client | -- | Static rendering from server data; no client-side interactivity in this phase |
| Redis dedupe lock | API / Backend | -- | SETNX in task execution context; prevents overlapping polls |
| Status state machine (closed vs resolved) | API / Backend | -- | Parser-level logic in `PolymarketAdapter`; domain model stores derived status |

## Standard Stack

### Core (already installed)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `httpx` | `>=0.28,<0.29` | Async HTTP client for Gamma API | Already in `pyproject.toml`; native `asyncio` support, `httpx.AsyncClient` connection pooling [ASSUMED] |
| `tenacity` | `>=9.0,<10.0` | Retry with exponential backoff + jitter | Already in `pyproject.toml`; decorator-based, integrates cleanly with async [ASSUMED] |
| `celery` | `>=5.5,<5.6` | Beat scheduler for periodic tasks | Already in `pyproject.toml`; proven in Phase 1 [VERIFIED: existing codebase] |
| `celery-redbeat` | `>=2.2,<3.0` | Redis-backed Beat schedule + distributed lock | Already in `pyproject.toml`; configured in `celery_app.py` [VERIFIED: existing codebase] |
| `redis` | `>=5.0,<6.0` | SETNX dedupe lock, pub/sub (Phase 9) | Already in `pyproject.toml`; async client via `redis.asyncio` [VERIFIED: existing codebase] |
| `pydantic` | `>=2.10,<3.0` | Gamma API response parsing + validation | Already in `pyproject.toml`; v2 `field_validator` + `model_validator` patterns validated in spike-002 [VERIFIED: existing codebase + spike] |
| `python-slugify` | `>=8.0,<9.0` | Slug generation for mirrored markets | Already in `pyproject.toml`; `generate_slug()` in `app/markets/models.py` [VERIFIED: existing codebase] |

### Frontend (already installed)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `next` | `^15.5.18` | Server Components, SSR | Already installed; RSC renders market list [VERIFIED: existing codebase] |
| shadcn/ui `Card` | -- | MarketCard base | Already installed at `frontend/src/components/ui/card.tsx` [VERIFIED: existing codebase] |

### Frontend (to add)

| Library | Version | Purpose | Install Command |
|---------|---------|---------|-----------------|
| shadcn `Badge` | -- | Source badge chip | `pnpm dlx shadcn@latest add badge` |
| shadcn `Skeleton` | -- | Loading state placeholders | `pnpm dlx shadcn@latest add skeleton` |
| `lucide-react` | -- | Icon library (shadcn default) | `pnpm add lucide-react` (if not already) |

### No new PyPI packages required
All backend dependencies are already in `pyproject.toml`. No `pip install` needed.

**Installation (frontend only):**
```bash
cd frontend
pnpm dlx shadcn@latest add badge
pnpm dlx shadcn@latest add skeleton
pnpm add lucide-react  # if not present
```

## Package Legitimacy Audit

> slopcheck was unavailable at research time. All packages below are tagged `[ASSUMED]` where they were not verified against the existing codebase.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| httpx | PyPI | ~5 yrs | 30M+/wk | github.com/encode/httpx | N/A | Approved -- already in pyproject.toml [ASSUMED] |
| tenacity | PyPI | ~9 yrs | 20M+/wk | github.com/jd/tenacity | N/A | Approved -- already in pyproject.toml [ASSUMED] |
| celery-redbeat | PyPI | ~8 yrs | 500K+/wk | github.com/sibson/redbeat | N/A | Approved -- already in pyproject.toml [ASSUMED] |
| python-slugify | PyPI | ~11 yrs | 8M+/wk | github.com/un33k/python-slugify | N/A | Approved -- already in pyproject.toml [ASSUMED] |
| lucide-react | npm | ~3 yrs | 5M+/wk | github.com/lucide-icons/lucide | N/A | Approved -- shadcn default [ASSUMED] |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

*slopcheck was unavailable at research time. All packages above are tagged `[ASSUMED]`. However, since ALL backend packages are already pinned in `pyproject.toml` (installed in Phase 1), the practical risk is zero. The planner should still gate `lucide-react` (if new) behind a verification step.*

## Architecture Patterns

### System Architecture Diagram

```
                          Celery Beat (30s / 5min)
                                  |
                  +---------------+----------------+
                  |                                |
      poll_polymarket_top25              snapshot_odds
          (every 30s)                    (every 5min)
                  |                                |
          Redis SETNX lock                         |
          (dedupe guard)                           |
                  |                                |
    httpx.AsyncClient GET                          |
    gamma-api.polymarket.com/markets               |
    ?active=true&closed=false                      |
    &order=volume24hr&limit=25                     |
                  |                                |
    GammaMarket Pydantic parser                    |
    (stringified JSON decode,                      |
     Decimal from strings,                         |
     _derive_status state machine)                 |
                  |                                |
    PolymarketAdapter.sync_top25()                 |
    UPSERT on (source, source_market_id)           |
                  |                                |
                  +-->  markets table  <-----------+
                        outcomes table       (read all OPEN markets,
                        odds_snapshots       write OddsSnapshot per outcome)
                             |
                    /api/v1/markets
                    (house-first, then PM by volume)
                             |
                    Next.js Server Component
                    MarketList -> MarketCard grid
                    (SSR at page render)
```

### Recommended Project Structure

```
backend/app/integrations/
    __init__.py
    market_source.py          # existing: Protocol, Registry, HouseAdapter
    polymarket/
        __init__.py           # register_source(POLYMARKET, PolymarketAdapter())
        client.py             # GammaClient: httpx.AsyncClient + tenacity retry
        schemas.py            # GammaMarket, GammaOutcome, _derive_status (from spike-002)
        adapter.py            # PolymarketAdapter(MarketSource)
        tasks.py              # poll_polymarket_top25, snapshot_odds Celery tasks

backend/tests/
    polymarket/
        __init__.py
        conftest.py           # VCR fixtures, mock GammaClient
        test_schemas.py       # GammaMarket parser + state machine
        test_client.py        # Retry behavior, error handling
        test_adapter.py       # Protocol conformance, upsert idempotency
        test_tasks.py         # Beat task execution, Redis lock
    fixtures/
        gamma/                # VCR fixture JSON files (from spike-002)
            active_market.json
            closed_not_resolved.json
            disputed_market.json
            resolved_market.json

frontend/src/
    components/
        market-card.tsx       # MarketCard: question, odds bar, metadata, badge
        source-badge.tsx      # SourceBadge: "Polymarket" (link) or "House"
        odds-display.tsx      # YES/NO percentage display with color
        market-list.tsx       # Server Component: fetch + render grid
        market-list-skeleton.tsx  # Loading skeleton grid
    app/
        page.tsx              # Replace scaffold with MarketList
```

### Pattern 1: Gamma API Client with Retry

**What:** httpx.AsyncClient wrapped with tenacity retry for transient failures.
**When to use:** Every HTTP call to the Gamma API.

```python
# Source: spike-002 + httpx docs + tenacity docs [ASSUMED]
import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.core.config import get_settings

log = structlog.get_logger()

class GammaClient:
    BASE_URL = "https://gamma-api.polymarket.com"

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                timeout=httpx.Timeout(15.0, connect=5.0),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )
        return self._client

    @retry(
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=10, jitter=2),
        reraise=True,
    )
    async def fetch_top_markets(self, *, limit: int = 25) -> list[dict]:
        client = await self._get_client()
        resp = await client.get(
            "/markets",
            params={
                "active": "true",
                "closed": "false",
                "order": "volume24hr",
                "limit": str(limit),
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
```

### Pattern 2: Redis SETNX Dedupe Lock

**What:** Prevent overlapping poll executions when two Beat instances fire simultaneously.
**When to use:** `poll_polymarket_top25` task preamble.

```python
# Source: redis-py docs + CONTEXT.md SC#2 [ASSUMED]
import redis.asyncio as aioredis

LOCK_KEY = "xpredict:poll:polymarket:lock"
LOCK_TTL_SECONDS = 25  # < 30s interval; auto-expires if task crashes

async def acquire_poll_lock(redis: aioredis.Redis) -> bool:
    """SETNX-based lock. Returns True if acquired, False if another worker holds it."""
    acquired = await redis.set(LOCK_KEY, "1", nx=True, ex=LOCK_TTL_SECONDS)
    return bool(acquired)

async def release_poll_lock(redis: aioredis.Redis) -> None:
    await redis.delete(LOCK_KEY)
```

### Pattern 3: Upsert on (source, source_market_id)

**What:** Idempotent insert-or-update for mirrored markets.
**When to use:** `PolymarketAdapter.sync_top25()`.

```python
# Source: SQLAlchemy 2.0 docs + existing MarketService patterns [ASSUMED]
from sqlalchemy.dialects.postgresql import insert as pg_insert

async def upsert_market(session: AsyncSession, data: dict) -> Market:
    stmt = pg_insert(Market).values(**data)
    stmt = stmt.on_conflict_do_update(
        index_elements=["source", "source_market_id"],
        set_={
            "question": stmt.excluded.question,
            "status": stmt.excluded.status,
            "volume": stmt.excluded.volume,
            "volume_24hr": stmt.excluded.volume_24hr,
            "updated_at": func.now(),
            # Do NOT overwrite slug, created_at, bet_count
        },
    )
    result = await session.execute(stmt)
    # ...
```

### Pattern 4: Pydantic extra Toggle by ENVIRONMENT

**What:** `extra='forbid'` in dev to catch schema drift early; `extra='allow'` + structured warning in staging/prod.
**When to use:** `GammaMarket` model config.

```python
# Source: CONTEXT.md Claude's Discretion + Phase 2 D-06 ENVIRONMENT pattern [VERIFIED: existing codebase]
from app.core.config import get_settings

def _gamma_model_config() -> dict:
    settings = get_settings()
    if settings.ENVIRONMENT == "dev":
        return {"extra": "forbid"}
    return {"extra": "allow"}

class GammaMarket(BaseModel):
    model_config = _gamma_model_config()
    # ... fields ...
```

Note: The spike-002 used `extra="allow"` unconditionally. In production code, toggle per ENVIRONMENT to detect schema drift in dev while remaining resilient in staging/prod.

### Pattern 5: Market List Query (House-First Sort)

**What:** Combined query returning house markets first, then Polymarket by volume.
**When to use:** Modified public `/api/v1/markets` endpoint.

```python
# Source: D-01 locked decision + existing MarketService.list_markets() [VERIFIED: existing codebase]
# Strategy: Two separate queries, concatenated in application layer.
# This avoids complex SQL CASE ordering and keeps each query efficient.

async def list_home_markets(session: AsyncSession) -> list[Market]:
    # 1. All open house markets, newest first
    house_stmt = (
        select(Market)
        .where(Market.source == MarketSourceEnum.HOUSE.value)
        .where(Market.status == MarketStatus.OPEN.value)
        .options(selectinload(Market.outcomes))
        .order_by(Market.created_at.desc())
    )
    house = (await session.execute(house_stmt)).scalars().all()

    # 2. Top-25 active Polymarket, by 24h volume desc
    pm_stmt = (
        select(Market)
        .where(Market.source == MarketSourceEnum.POLYMARKET.value)
        .where(Market.status == MarketStatus.OPEN.value)
        .options(selectinload(Market.outcomes))
        .order_by(Market.volume_24hr.desc())
        .limit(25)
    )
    pm = (await session.execute(pm_stmt)).scalars().all()

    return list(house) + list(pm)
```

### Anti-Patterns to Avoid

- **Per-market API calls:** NEVER fetch each market individually. The Gamma API returns top-25 in a single batch request. Per-market loops would burn 25x the rate budget and add 25x latency. [VERIFIED: ROADMAP PITFALL #9]
- **Using `volumeNum`/`liquidityNum` float fields:** NEVER use the float variants from the Gamma API. Always parse string fields (`volume`, `liquidity`) to `Decimal`. Float precision loss is cumulative. [VERIFIED: spike-002 findings]
- **Settling on `closed=true` alone:** NEVER map `closed=true` to `RESOLVED` status. The `_derive_status` state machine requires `closed=true + umaResolutionStatus="resolved" + clear winner` for RESOLVED. This is the most dangerous pitfall in the entire integration. [VERIFIED: spike-002 findings + ROADMAP PITFALL #2]
- **Assuming `umaResolutionStatus` exists:** The field is ABSENT (not null) when no UMA process has started. Always default to `None` and check explicitly. [VERIFIED: spike-002 findings]
- **Hardcoding Gamma field list:** Use `extra='allow'` (in staging/prod) because the API has 50+ fields and new ones appear without notice. [VERIFIED: spike-002 findings]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP retry with backoff | Custom retry loop with `asyncio.sleep` | `tenacity` decorator on `httpx.AsyncClient` calls | Handles jitter, exponential backoff, exception filtering, logging; 10 lines vs 50+ |
| Distributed task lock | Custom Redis Lua script for lock acquisition | `redis.set(key, value, nx=True, ex=TTL)` (SETNX with TTL) | SETNX is atomic; TTL auto-expires on crash; no Lua complexity |
| JSON stringified field parsing | Manual `if isinstance(v, str): json.loads(v)` in every field | Pydantic `field_validator` with `mode="before"` on all stringified list fields | Centralized, tested once, handles all edge cases (null, pre-parsed, invalid) |
| Market status state machine | Ad-hoc if/else in multiple locations | Single `_derive_status()` function called in `model_validator(mode="after")` | Spike-validated truth table; single function to test and audit |
| Slug dedup | Manual UUID suffix generation | Existing `generate_slug()` from `app/markets/models.py` | Already tested in Phase 4; UUID hex suffix guarantees uniqueness |

**Key insight:** The spike-002 already solved the hard parsing problems. The production code should port those solutions directly, not reinvent them.

## Common Pitfalls

### Pitfall 1: closed vs resolved Confusion (CRITICAL)
**What goes wrong:** Mapping Polymarket `closed=true` directly to `RESOLVED` status causes premature settlement in Phase 7. Polymarket uses `closed` to mean "no longer accepting orders" -- but the market might still be in UMA dispute.
**Why it happens:** The word "closed" intuitively suggests "done." Polymarket's lifecycle is: OPEN -> CLOSED (no orders) -> PROPOSED (UMA) -> DISPUTED (optional) -> RESOLVED (final).
**How to avoid:** The `_derive_status()` state machine from spike-002 encodes the full truth table. Only `closed=true AND umaResolutionStatus="resolved" AND has_winner` maps to RESOLVED. Unit test with the `closed_not_resolved.json` fixture is mandatory.
**Warning signs:** Any `Market.status = RESOLVED` where `closed_at` is set but `resolved_at` is not.

### Pitfall 2: Rate Limit Overshoot
**What goes wrong:** Fetching per-market details or retrying aggressively burns through the 300 req/10s limit on `/markets`.
**Why it happens:** Naive retry policies or per-market detail fetches multiply request count.
**How to avoid:** Single batch call (`limit=25`) every 30s = 2 req/min. tenacity stops after 3 attempts with jitter. Redis SETNX prevents double-fetching. Monitor latency as a throttle warning signal. [CITED: docs.polymarket.com/quickstart/introduction/rate-limits]
**Warning signs:** HTTP 429 responses; response latency > 5s (Cloudflare throttling kicks in before rejection).

### Pitfall 3: Float Precision in Volume/Liquidity
**What goes wrong:** Using Gamma's float fields (`volumeNum`, `liquidityNum`) or Python `float()` for volume loses precision. Sorting by volume breaks when `57367327.83401454` rounds differently.
**Why it happens:** IEEE 754 double precision cannot exactly represent all decimal fractions.
**How to avoid:** Always parse from string fields (`volume`, `liquidity`) using `Decimal(str(value))`. Store as `Numeric(18,4)` in Postgres. [VERIFIED: spike-002 + existing Money convention WAL-05]
**Warning signs:** Volume display shows scientific notation or trailing noise digits.

### Pitfall 4: Overlapping Beat Executions
**What goes wrong:** Two Beat instances (e.g., docker restart during deploy) fire `poll_polymarket_top25` simultaneously, causing double-upserts or race conditions.
**Why it happens:** RedBeat's distributed lock prevents duplicate Beat schedulers, but at-least-once delivery means a task could be dispatched twice if the worker restarts mid-execution.
**How to avoid:** Redis SETNX lock with TTL < poll interval (25s TTL for 30s interval). Task acquires lock before fetching; releases on completion or lets TTL auto-expire on crash.
**Warning signs:** Duplicate log entries for the same poll cycle; lock TTL >= poll interval (causes permanent lockout).

### Pitfall 5: Schema Drift Detection
**What goes wrong:** Polymarket adds or renames a field in their API response. In `extra='forbid'` mode, this silently crashes all polls. In `extra='allow'` mode without logging, drift goes unnoticed and Phase 7 auto-resolution may break.
**Why it happens:** External APIs evolve without versioning or notification.
**How to avoid:** Use `extra='forbid'` in dev (immediate crash), `extra='allow'` + structured warning log in staging/prod. Log the set of unknown field names so Sentry catches drift events. [VERIFIED: spike-002 "What to Avoid" rule #5]
**Warning signs:** Sentry events with `event_type=gamma_schema_drift` (or absence of them when they should exist).

### Pitfall 6: Missing volume/volume_24hr Columns
**What goes wrong:** Phase 4 `markets` table has no `volume` or `volume_24hr` columns. Attempting to store or sort by volume fails.
**Why it happens:** Phase 4 built the market domain for house markets only; house markets have no volume concept (admin-set odds).
**How to avoid:** Migration 0004 adds `volume Numeric(18,4) DEFAULT 0` and `volume_24hr Numeric(18,4) DEFAULT 0` and `source_url TEXT NULLABLE` to the `markets` table. House markets leave these at 0.
**Warning signs:** SQLAlchemy AttributeError on `Market.volume` or migration conflicts.

## Code Examples

Verified patterns from spike-002 and official sources:

### Gamma API Response Parsing (from spike-002 validated parser)
```python
# Source: .claude/skills/spike-findings-xpredict/sources/002-polymarket-gamma-parser/gamma_parser.py
# [VERIFIED: spike-002 fixtures pass all 4 test cases]

import json
from decimal import Decimal, InvalidOperation
from pydantic import BaseModel, Field, field_validator, model_validator

class GammaMarket(BaseModel):
    # Toggle extra per ENVIRONMENT (dev=forbid, staging/prod=allow)
    id: str
    question: str
    condition_id: str = Field(alias="conditionId", default="")
    slug: str = ""

    # Stringified JSON fields -- validator handles both string and pre-parsed
    outcomes_raw: list[str] = Field(alias="outcomes", default_factory=list)
    outcome_prices_raw: list[str] = Field(alias="outcomePrices", default_factory=list)
    clob_token_ids: list[str] = Field(alias="clobTokenIds", default_factory=list)

    # String numeric fields -- NEVER use volumeNum/liquidityNum
    volume_str: str = Field(alias="volume", default="0")
    liquidity_str: str = Field(alias="liquidity", default="0")
    volume_24hr: float | None = Field(alias="volume24hr", default=None)

    closed: bool = False
    uma_resolution_status: str | None = Field(alias="umaResolutionStatus", default=None)

    @field_validator("outcomes_raw", "outcome_prices_raw", "clob_token_ids", mode="before")
    @classmethod
    def parse_stringified_json_list(cls, v):
        if v is None: return []
        if isinstance(v, list): return v
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list): return parsed
            except (json.JSONDecodeError, TypeError): pass
            return []
        return []
```

### Status State Machine (from spike-002)
```python
# Source: .claude/skills/spike-findings-xpredict/sources/002-polymarket-gamma-parser/gamma_parser.py
# [VERIFIED: spike-002 fixtures -- closed_not_resolved.json does NOT enter RESOLVED]

def _derive_status(closed: bool, uma_status: str | None, outcome_prices: list[str]) -> MarketStatus:
    if not closed and uma_status is None:
        return MarketStatus.OPEN
    if not closed and uma_status == "proposed":
        return MarketStatus.OPEN  # map to OPEN internally (no PROPOSED in our enum)
    if not closed and uma_status == "disputed":
        return MarketStatus.OPEN  # still tradeable, map to OPEN
    if closed and uma_status == "resolved":
        has_winner = any(p in ("0", "1", "0.0", "1.0") for p in outcome_prices)
        if has_winner:
            return MarketStatus.RESOLVED
        return MarketStatus.CLOSED
    if closed and uma_status in ("proposed", "disputed", None):
        return MarketStatus.CLOSED  # closed but NOT resolved
    if not closed and uma_status == "resolved":
        return MarketStatus.RESOLVED
    return MarketStatus.OPEN
```

Note: The spike used `InternalMarketStatus` with PROPOSED/DISPUTED values. In production, map to the existing `MarketStatus` enum (`OPEN`, `CLOSED`, `RESOLVED`) since our codebase does not need the granular UMA states -- the Polymarket adapter stores `uma_resolution_status` raw for Phase 7 to use.

### Celery Beat Schedule Registration
```python
# Source: existing celery_app.py pattern [VERIFIED: existing codebase]
# Add to celery_app.py beat_schedule:
celery_app.conf.beat_schedule = {
    "poll-polymarket-top25": {
        "task": "app.integrations.polymarket.tasks.poll_polymarket_top25",
        "schedule": 30.0,  # seconds
    },
    "snapshot-odds": {
        "task": "app.integrations.polymarket.tasks.snapshot_odds",
        "schedule": 300.0,  # 5 minutes
    },
}
```

### Frontend MarketCard (per UI-SPEC)
```tsx
// Source: 06-UI-SPEC.md layout contract [VERIFIED: existing UI-SPEC]
// Key structure -- full implementation per UI-SPEC dimensions:
import { Card, CardHeader, CardContent, CardFooter } from "@/components/ui/card";
import Link from "next/link";

export function MarketCard({ market }: { market: MarketItem }) {
  const yesOdds = market.outcomes.find(o => o.label === "YES");
  const noOdds = market.outcomes.find(o => o.label === "NO");
  const yesPercent = Math.round((yesOdds?.current_odds ?? 0.5) * 100);
  const noPercent = 100 - yesPercent;

  return (
    <Link href={`/markets/${market.slug}`} className="group">
      <Card className="hover:shadow-md transition-shadow">
        <CardHeader className="p-6 pb-2">
          <h3 className="text-base font-semibold leading-snug line-clamp-3">
            {market.question}
          </h3>
        </CardHeader>
        <CardContent className="p-6 pt-0">
          <OddsDisplay yes={yesPercent} no={noPercent} />
        </CardContent>
        <CardFooter className="p-6 pt-0 flex justify-between items-end">
          <div className="text-sm text-zinc-500">
            <span>Vol: {formatVolume(market.volume)}</span>
            <span className="mx-2">|</span>
            <span>{formatDeadline(market.deadline)}</span>
          </div>
          <SourceBadge source={market.source} sourceUrl={market.source_url} />
        </CardFooter>
      </Card>
    </Link>
  );
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| requests + custom retry | httpx.AsyncClient + tenacity | httpx 0.20+ (2022) | Native async, connection pooling, timeout config |
| celery-beat + file scheduler | celery-redbeat (Redis-backed) | redbeat 2.0 (2020) | Distributed, persistent, no filesystem dependency |
| Pydantic v1 validators | Pydantic v2 `field_validator` + `model_validator` | Pydantic 2.0 (2023) | 5-50x faster, `mode="before"` for raw input |
| Manual JSON.parse in JS | Pydantic server-side parsing | N/A | Server validates; frontend trusts API contract |

**Deprecated/outdated:**
- `celery.schedules.crontab` with file-based celerybeat-schedule.db: Replaced by RedBeat Redis storage (already configured in Phase 1).
- `requests` library for async HTTP: `httpx` is the modern async-native replacement.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `httpx.AsyncClient` supports `limits=httpx.Limits(max_connections=10)` for connection pooling | Architecture Patterns / Pattern 1 | Would need manual pool management; httpx docs should confirm |
| A2 | `tenacity` `wait_exponential_jitter` accepts `jitter` parameter for random jitter addition | Architecture Patterns / Pattern 1 | Would fall back to `wait_exponential` + manual jitter |
| A3 | PostgreSQL `ON CONFLICT DO UPDATE` works with composite index `(source, source_market_id)` | Architecture Patterns / Pattern 3 | Would need unique constraint or composite primary key; standard Postgres feature |
| A4 | Gamma API `/markets` supports `order=volume24hr` query parameter | Architecture Diagram | Spike-002 did not test sorting; if not supported, sort client-side |
| A5 | `lucide-react` may need explicit install (could already be a shadcn transitive dep) | Standard Stack / Frontend | Minor; `pnpm add` is idempotent |
| A6 | Gamma API field `volume24hr` is always present on active markets | Architecture Patterns | If absent on some markets, fallback to 0 for sorting |

## Open Questions

1. **Gamma API `order` parameter validation**
   - What we know: The spike used `?active=true&closed=false&limit=10` but did not test `order=volume24hr`.
   - What's unclear: Whether the Gamma API supports `order` as a query parameter, or if ordering must be done client-side after fetching.
   - Recommendation: The implementation should fetch with `order=volume24hr` and fall back to client-side sort if the API ignores it. Either way, the result is the same -- just affects whether we fetch more than 25 and trim, or the API does it for us.

2. **Unique constraint on (source, source_market_id)**
   - What we know: The `markets` table has `source` and `source_market_id` columns but no explicit UNIQUE constraint on the pair.
   - What's unclear: Whether Phase 4 migration added a unique index.
   - Recommendation: Migration 0004 should add `CREATE UNIQUE INDEX IF NOT EXISTS ix_markets_source_source_market_id ON markets (source, source_market_id) WHERE source_market_id IS NOT NULL` to support the upsert pattern. The `WHERE` clause excludes house markets (which have `source_market_id = NULL`).

3. **`source_url` column for badge link**
   - What we know: The `MarketCard` source badge needs a link to the Polymarket source URL (e.g., `https://polymarket.com/event/{slug}`). The current `Market` model has no `source_url` field.
   - What's unclear: Whether to add a column or derive the URL from `source` + `slug`.
   - Recommendation: Derive it: `source === "POLYMARKET" ? \`https://polymarket.com/event/\${source_market_id}\` : null`. No new column needed. Add as a computed property in the API response schema.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.3+ / pytest-asyncio 0.24+ |
| Config file | `backend/pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `cd backend && uv run pytest tests/polymarket/ -x -q` |
| Full suite command | `cd backend && uv run pytest -x -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MKT-05 | poll_polymarket_top25 fetches and upserts top-25 | integration | `uv run pytest tests/polymarket/test_tasks.py::test_poll_upserts_markets -x` | Wave 0 |
| MKT-05 | Redis SETNX prevents double-fetch | unit | `uv run pytest tests/polymarket/test_tasks.py::test_redis_lock_prevents_overlap -x` | Wave 0 |
| MKT-05 | Rate: <=2 req/min sustained | unit | `uv run pytest tests/polymarket/test_client.py::test_single_batch_call -x` | Wave 0 |
| MKT-06 | snapshot_odds writes OddsSnapshot per open market outcome | integration | `uv run pytest tests/polymarket/test_tasks.py::test_snapshot_odds -x` | Wave 0 |
| MKT-01 | Public market list returns house-first + PM by volume | integration | `uv run pytest tests/polymarket/test_adapter.py::test_home_market_list_ordering -x` | Wave 0 |
| MKT-02 | MarketCard renders question/odds/volume/badge | -- | Frontend: `pnpm test` (Vitest) | Wave 0 |
| SC#3 | Upsert idempotency: double poll = zero duplicates | integration | `uv run pytest tests/polymarket/test_adapter.py::test_upsert_idempotent -x` | Wave 0 |
| SC#6 | Parser handles stringified JSON + Decimal from strings | unit | `uv run pytest tests/polymarket/test_schemas.py -x` | Wave 0 |
| SC#7 | closed=true + umaResolutionStatus=proposed != RESOLVED | unit | `uv run pytest tests/polymarket/test_schemas.py::test_closed_not_resolved -x` | Wave 0 |
| PROTO | PolymarketAdapter passes MarketSource Protocol conformance | unit | `uv run pytest tests/polymarket/test_adapter.py::test_protocol_conformance -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `cd backend && uv run pytest tests/polymarket/ -x -q`
- **Per wave merge:** `cd backend && uv run pytest -x -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `backend/tests/polymarket/__init__.py` -- module init
- [ ] `backend/tests/polymarket/conftest.py` -- VCR fixtures, mock GammaClient, sample Polymarket market fixture
- [ ] `backend/tests/polymarket/test_schemas.py` -- GammaMarket parser tests (4 VCR fixtures)
- [ ] `backend/tests/polymarket/test_client.py` -- GammaClient retry tests
- [ ] `backend/tests/polymarket/test_adapter.py` -- Protocol conformance + upsert idempotency
- [ ] `backend/tests/polymarket/test_tasks.py` -- Beat task execution + Redis lock
- [ ] `backend/tests/fixtures/gamma/` -- Copy VCR fixtures from spike-002

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Phase 6 adds no new auth surfaces |
| V3 Session Management | No | No session changes |
| V4 Access Control | No | Public market list is read-only; no new admin endpoints |
| V5 Input Validation | Yes | Pydantic `GammaMarket` validates all external API data; `extra='forbid'` in dev catches unexpected fields |
| V6 Cryptography | No | No new crypto operations |

### Known Threat Patterns for External API Integration

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malicious response injection from Gamma API | Tampering | Pydantic strict parsing; all fields validated; unknown fields rejected or logged |
| Rate limit abuse exhausting Gamma quota | Denial of Service | Single batch call (2 req/min); tenacity max 3 retries; Redis SETNX lock |
| SSRF via `source_url` in market cards | Information Disclosure | URL is derived from `source_market_id` (controlled format), not user input; no server-side fetch |
| Redis lock bypass via key collision | Elevation of Privilege | Fixed key pattern `xpredict:poll:polymarket:lock`; only the poll task uses it |

## Project Constraints (from CLAUDE.md)

- **Language:** Spanish for conversation, English for code and paths
- **Python env:** bare `python` is broken (Microsoft Store stub) -- use full path or venv
- **Phase tracking:** `PHASES.md` is source of truth for who is doing what
- **Branch strategy:** per-phase branches (`gsd/phase-6-polymarket-sync-catalog-replication`)
- **PR via GitHub MCP:** not `gh` CLI
- **Spike findings:** `Skill("spike-findings-xpredict")` -- CRITICAL for this phase
- **Execution approach:** use subagents for independent tasks; inline for sequential/shared-state

## Sources

### Primary (HIGH confidence)
- Spike-002 `gamma_parser.py` + 4 VCR fixtures -- validated parser, state machine, all edge cases
- `backend/app/integrations/market_source.py` -- existing Protocol, Registry, HouseAdapter
- `backend/app/markets/models.py` -- existing Market, Outcome, OddsSnapshot ORM
- `backend/app/celery_app.py` -- existing Celery factory with empty beat_schedule
- `backend/app/core/config.py` -- existing Settings pattern
- `06-UI-SPEC.md` -- full visual contract for frontend components

### Secondary (MEDIUM confidence)
- [Polymarket Rate Limits](https://docs.polymarket.com/quickstart/introduction/rate-limits) -- 300 req/10s on `/markets` endpoint [CITED]
- [Polymarket Gamma API Overview](https://docs.polymarket.com/developers/gamma-markets-api/overview) -- base URL, public access [CITED]
- [RedBeat documentation](https://redbeat.readthedocs.io/en/latest/intro.html) -- distributed lock, Redis-backed schedule [CITED]

### Tertiary (LOW confidence)
- httpx AsyncClient connection pooling parameters (training knowledge) [ASSUMED]
- tenacity `wait_exponential_jitter` API (training knowledge) [ASSUMED]
- Gamma API `order=volume24hr` query parameter support [ASSUMED]

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all packages already installed; no new deps
- Architecture: HIGH -- spike-002 validated the core parser and state machine; existing Protocol/Registry pattern proven in Phase 4
- Pitfalls: HIGH -- 6 pitfalls documented with verified mitigations from spike findings and official rate limit docs
- Frontend: HIGH -- UI-SPEC exists with full contract; shadcn Card already installed

**Research date:** 2026-05-28
**Valid until:** 2026-06-28 (stable -- Gamma API has no versioning; spike fixtures serve as schema anchor)
