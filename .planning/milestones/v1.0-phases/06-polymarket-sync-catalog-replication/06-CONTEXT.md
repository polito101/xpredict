# Phase 6: Polymarket Sync (Catalog Replication) - Context

**Gathered:** 2026-05-28
**Status:** Ready for planning

<domain>
## Phase Boundary

**Mirror the top-25 active Polymarket markets into our database via a custom httpx + tenacity Gamma client and a `PolymarketAdapter` that implements the `MarketSource` Protocol from Phase 4. Celery Beat polls every 30s, snapshots odds every 5min. First player-facing market list UI (home page). Sync only — no auto-resolution, no changes to bet engine.**

Phase 6 delivers MKT-01, MKT-02, MKT-05, MKT-06:

- `PolymarketAdapter` in `app/integrations/polymarket/` implements `MarketSource` Protocol; registered in the source registry as `REGISTRY[POLYMARKET]`
- Custom httpx + tenacity Gamma API client (`gamma-api.polymarket.com`) with retry/backoff
- Pydantic v2 parser for Gamma API responses (stringified JSON fields, Decimal from strings, closed/resolved state machine)
- `poll_polymarket_top25` Celery Beat task every 30s — upserts top-25 active markets; Redis SETNX dedupe lock
- `snapshot_odds` Celery Beat task every 5min — writes `odds_snapshots` rows for all open markets (both house and mirrored)
- Player home page showing market list: house markets first, then Polymarket by 24h volume
- Market cards with source badge, odds, deadline, volume
- `closed` vs `resolved` distinction enforced at parser/model layer (settlement safety for Phase 7)

**Out of this phase entirely:**
- Auto-resolution of mirrored markets → Phase 7
- Market detail page with price history chart → Phase 9
- Admin force-settle for stuck markets → Phase 7
- Bet placement on markets → Phase 5 (prerequisite)
- WebSocket real-time updates → Phase 9
- Market search, filters, categories → future
- Full Polymarket catalog beyond top-25 → future

</domain>

<decisions>
## Implementation Decisions

### Market List Sorting
- **D-01: House markets first, then Polymarket by volume** — The home page list shows all open house markets first (sorted by `created_at` desc), followed by the current top-25 Polymarket mirrored markets sorted by 24h volume desc. This ensures the operator's own markets always have prominence over mirrored content.

### Source Badge Design
- **D-02: Badge discreto** — Small chip positioned bottom-right of each market card. Polymarket markets show "Polymarket" text with a link to the original market on polymarket.com. House markets show "House" without link. The badge should not distract from the main card content (question, odds, volume).

### Market Disappearance & Lifecycle
- **D-03: Top-25 rotation with DB persistence** — Each 30s poll fetches the current top-25 from Polymarket and upserts them into our DB. The player home page list shows only the current top-25 active mirrored markets (whatever the latest poll returned). Markets that fall out of the top-25 remain in DB (they may have bets from Phase 5+) but do not appear on the home page.
- **D-04: Portfolio visibility for dropped markets** — Markets with active bets remain accessible via the player's portfolio (Phase 5+) and via direct URL to the market detail page (Phase 9), even if they no longer appear on the home page. No market data is ever deleted.

### Claude's Discretion
- Gamma client architecture: httpx.AsyncClient lifecycle, tenacity retry policy (backoff, jitter, max retries), timeout values, connection pooling strategy
- Redis dedupe lock: TTL, key pattern, auto-expiry for crashed tasks
- Pydantic parser configuration: `extra='forbid'` in dev vs `extra='allow'` + warning log in staging — toggled by `ENVIRONMENT` env var (follows Phase 2 D-06 pattern)
- Market card layout: follow shadcn/ui Card component conventions, display question, YES/NO odds, deadline, volume, source badge
- Slug generation for mirrored markets: follow Phase 4's `generate_slug()` pattern from question text
- Migration naming: `0004_phase6_polymarket_sync.py` or appropriate sequence number
- Test organization: `backend/tests/polymarket/` and/or `backend/tests/integrations/` following existing patterns
- VCR fixture strategy for testing against Gamma API responses (spike 002 fixtures available)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & Roadmap
- `.planning/REQUIREMENTS.md` §Markets — Browsing & Sync (MKT-01, MKT-02, MKT-05, MKT-06)
- `.planning/ROADMAP.md` §Phase 6 — goal, 7 success criteria, pitfalls #2 and #9

### Spike Findings (CRITICAL)
- `.claude/skills/spike-findings-xpredict/SKILL.md` — master index of all spike findings
- `.claude/skills/spike-findings-xpredict/references/polymarket-integration.md` — Pydantic v2 parser, state machine, Decimal handling, Gamma API schema reference, VCR fixtures, "What to Avoid" section (6 critical rules)

### Prior Phase Context
- `.planning/phases/04-markets-domain-houseadapter/04-CONTEXT.md` — MarketSource Protocol, Registry pattern, async adapters, ORM model patterns, odds as Decimal 0-1, slug generation, pagination pattern
- `.planning/phases/02-auth-identity/02-CONTEXT.md` — Settings pattern for env vars, ENVIRONMENT toggle pattern (D-06)

### Existing Code (Phase 4 foundations)
- `backend/app/integrations/market_source.py` — `MarketSource` Protocol, `REGISTRY`, `register_source()`, `HouseAdapter` implementation
- `backend/app/markets/models.py` — `Market`, `Outcome`, `OddsSnapshot` ORM models with `source`, `source_market_id`, `condition_id` columns
- `backend/app/markets/enums.py` — `MarketSourceEnum`, `MarketStatus`
- `backend/app/celery_app.py` — Celery factory with `beat_schedule = {}` ready for Phase 6 tasks, RedBeat scheduler configured

### Project Constraints
- `.planning/PROJECT.md` §Constraints — Gamma API REST pública, polling vía Celery, no on-chain
- `.planning/PROJECT.md` §Key Decisions — "Top 25 mercados de Polymarket al inicio"

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/integrations/market_source.py` — `MarketSource` Protocol + `REGISTRY` + `register_source()` — Phase 6 adds `PolymarketAdapter` and calls `register_source(POLYMARKET, PolymarketAdapter())`
- `app/markets/models.py` — `Market` model already has `source`, `source_market_id`, `condition_id`, `status` columns ready for Polymarket data
- `app/markets/service.py` — `MarketService` for DB operations on markets (CRUD, queries)
- `app/markets/schemas.py` — Pydantic response schemas for market API
- `app/markets/router.py` — existing `/api/v1/markets` public endpoint and `/api/v1/admin/markets` admin endpoints
- `app/celery_app.py` — `beat_schedule = {}` ready for `poll_polymarket_top25` and `snapshot_odds` tasks
- `app/core/config.py` — `Settings(BaseSettings)` for new env vars (Gamma API base URL, poll intervals, lock TTL)
- `app/core/audit/service.py` — `AuditService.record()` for audit logging sync events
- `app/db/types.py` — `Money` alias for `Decimal` + `Numeric(18, 4)`

### Established Patterns
- Async throughout: `AsyncSession`, async adapter methods, async httpx client
- UUID PK with `default=uuid4` + `server_default=func.gen_random_uuid()`
- `tenant_id` ghost column on all models
- structlog for logging + Sentry for error tracking
- Offset-limit pagination (`?page=1&page_size=20`)
- Feature folder structure: `app/integrations/polymarket/` with `__init__.py`, `client.py`, `adapter.py`, `schemas.py`

### Integration Points
- `app/integrations/polymarket/` — new module for Gamma client + PolymarketAdapter
- `app/celery_app.py` `beat_schedule` — add `poll_polymarket_top25` (30s) and `snapshot_odds` (5min)
- `app/markets/router.py` — modify public market list to return mixed house + mirrored, with house-first sorting
- `frontend/app/` — new home page with market list cards (first player-facing market UI)
- `app/main.py` — no changes expected (router already included from Phase 4)

</code_context>

<specifics>
## Specific Ideas

- El operador quiere sus house markets siempre arriba en la lista — house first, Polymarket después. Esto es una decisión de producto, no técnica.
- La lista del player muestra el "top-25 vivo" — lo que Polymarket devuelve en el último poll. No se acumula catálogo más allá de lo que está activo.
- Los mercados caídos del top-25 persisten en DB por apuestas futuras (Phase 5+) pero no aparecen en la home.
- En el futuro se añadirán búsqueda y categorías para que el player encuentre mercados que no están en la home.
- Visión futura: copiar mercados de Polymarket pero que todas las apuestas sean in-house (no participar en la economía on-chain de Polymarket).

</specifics>

<deferred>
## Deferred Ideas

- **Búsqueda y categorías de mercados** — el player podrá buscar y filtrar mercados más allá del top-25 visible en la home. Pertenece a una fase futura (posiblemente Phase 9 UX Polish o un phase dedicado).
- **Copia completa de mercados Polymarket con apuestas in-house** — el usuario quiere que en el futuro los mercados se copien y todas las apuestas se realicen internamente, sin depender de Polymarket para la economía. Requiere rediseño del modelo de datos y settlement. Pertenece a v2.

</deferred>

---

*Phase: 6-Polymarket Sync (Catalog Replication)*
*Context gathered: 2026-05-28*
