# Phase 4: Markets Domain & HouseAdapter - Context

**Gathered:** 2026-05-27
**Status:** Ready for planning

<domain>
## Phase Boundary

**Establish the source-agnostic market domain (Market, Outcome, OddsSnapshot) and prove the `MarketSource` Protocol with a fully-controllable HouseAdapter — no external dependency, no Polymarket yet. Admin can author and operate house markets end-to-end.**

Phase 4 delivers MKT-07, MKT-08, ADM-01, ADM-02, ADM-03, ADM-04, ADM-07:

- `MarketSource` Python Protocol defined in `app/integrations/market_source.py` with `fetch_active_markets()`, `fetch_market()`, and `detect_resolution()`; `HouseAdapter` implements it and is registered in the source registry
- Admin CRUD for house markets: create binary (YES/NO) market with question, resolution criteria, deadline, initial odds (default 50/50), category; edit while zero bets; close early
- Paginated admin market list with filters for source, status, category
- Public read-only market list endpoint for player-facing consumption (Phase 5+ bet flow)
- `markets` and `outcomes` tables with `source` + `source_market_id` columns; binary-only enforced via CHECK constraint
- Resolution criteria locked after first bet (423 Locked on edit + API rejection)
- `odds_snapshots` table for price history (HouseAdapter writes on create/edit; Phase 6 adds Beat task)

**Out of this phase entirely:**
- Player-facing frontend pages (market cards, detail) → Phase 5/9
- Admin frontend UI for market management → Phase 8 (CRM)
- PolymarketAdapter → Phase 6
- Bet placement logic → Phase 5
- Market resolution logic → Phase 5 (house) / Phase 7 (Polymarket)
- WebSocket real-time updates → Phase 9

</domain>

<decisions>
## Implementation Decisions

### Protocol & Adapter Architecture
- Async protocol methods — codebase uses `AsyncSession` everywhere; both HouseAdapter (DB) and future PolymarketAdapter (HTTP) are async by nature
- Adapter methods return ORM models — adapters are internal; routers serialize to Pydantic. Avoids double-conversion and lets service layer use ORM relations
- Dict-based singleton registry: `REGISTRY: dict[MarketSourceEnum, MarketSource]` in `market_source.py` — simple, discoverable, testable. Phase 6 adds `REGISTRY[POLYMARKET] = PolymarketAdapter()`
- `detect_resolution()` in HouseAdapter returns `None` always — house markets resolve via explicit admin action (Phase 5), not auto-detection. Exists to satisfy Protocol contract

### Schema & Data Model
- Full lifecycle status enum: `DRAFT`, `OPEN`, `CLOSED`, `RESOLVED`, `CANCELLED` — Phase 4 uses OPEN/CLOSED, Phase 5 adds RESOLVED transitions. Defining all now avoids ALTER TYPE later
- Odds stored as Decimal probability 0–1 (`Numeric(8,6)`) — Polymarket uses 0–1, math is natural (`price * stake = payout`), no conversion in Phase 6. Display layer converts to percentage
- Auto-generated slug from question via `python-slugify` + UUID suffix for uniqueness (e.g., `will-bitcoin-hit-100k-a3f2`). Admin doesn't set slug manually
- `odds_snapshots` table created in Phase 4 migration — HouseAdapter writes snapshot on create/edit; Phase 6 adds Beat task for periodic snapshots

### Admin API Contract & Frontend Scope
- Offset-limit pagination (`?page=1&page_size=20`) — simple, matches shadcn DataTable pattern Phase 8 will use
- Endpoint prefix: `/api/v1/admin/markets` for admin CRUD; `/api/v1/markets` for public read-only list
- Backend API only (no admin frontend in Phase 4) — ROADMAP has no UI hint. API-first lets Phase 5 bet flow and Phase 8 CRM consume the same endpoints
- Public market list endpoint at `/api/v1/markets` — no auth required, returns open markets with odds. Admin endpoints require Bearer JWT

### Claude's Discretion
- Migration naming: `0003_phase4_markets.py` (follows `0001_phase1_foundations`, `0002_phase2_auth` pattern)
- Test organization: `backend/tests/markets/` directory matching the `app/markets/` module pattern
- Error handling conventions: follow Phase 2 patterns (HTTPException with detail dict)
- Audit events: `market.created`, `market.updated`, `market.closed` following D-40 convention from Phase 1

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app.db.base.Base` — DeclarativeBase for all models
- `app.db.types.Money` — `Annotated[Decimal, mapped_column(Numeric(18, 4), nullable=False)]`
- `app.core.audit.service.AuditService.record()` — append-only audit logging
- `app.core.config.get_settings()` — cached Settings singleton
- `app.auth.deps` — admin dependency injection (`current_active_superuser`)
- structlog for logging; Sentry for error tracking

### Established Patterns
- UUID PK: `id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4, server_default=func.gen_random_uuid())`
- tenant_id ghost column: `Mapped[PyUUID | None]` with `default=lambda: get_settings().TENANT_ID_DEFAULT`
- Timestamps: `DateTime(timezone=True)` with `server_default=func.now()`
- Router pattern: module-level `APIRouter()` with prefix, tags, dependencies
- Rate limiting via `@limiter.limit()` decorator (slowapi)
- Alembic migration pattern: `NNNN_phaseX_domain.py`, FK-bearing tables dropped first in downgrade

### Integration Points
- `app/integrations/__init__.py` — stub with "Phase 6 owns this" comment; Phase 4 creates `market_source.py` here
- `app/markets/__init__.py` — empty stub ready for models, router, schemas, service
- `app/main.py` — include router for new endpoints
- Admin auth dependency from Phase 2 for protecting admin endpoints

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches following established codebase patterns.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>
