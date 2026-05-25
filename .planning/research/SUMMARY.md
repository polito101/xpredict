# XPredict -- Research Synthesis

**Synthesized:** 2026-05-25
**Source files:** STACK.md, FEATURES.md, ARCHITECTURE.md, PITFALLS.md
**Consumer:** gsd-roadmapper + per-phase planning agents
---

## Executive Summary

XPredict is a white-label B2B2C prediction market platform. The buyer is an operator who licenses a turnkey product to offer prediction markets under their brand; the end-users are players who browse markets, place play-money bets, and watch resolutions. The core value proposition is a credible, production-grade platform -- Polymarket-mirrored catalog, house market CRUD, CRM panel, double-entry wallet accounting, configurable branding -- that an operator can license without touching code. v1 is play money only, sidestepping licensing and allowing sales validation before committing to fiat/crypto infrastructure.

The recommended architecture is a modular monolith: FastAPI + Celery deployed as three processes (api, worker, beat) against one Postgres 16 and one Redis. A MarketSource Protocol adapter is the central design decision -- it isolates Polymarket-specific logic so house markets, and later live-bets, plug in without rewriting the bet/settlement engine. The double-entry ledger (accounts + entries tables, append-only, ACID-bound) is the financial backbone; built before bet placement and never using floats. The frontend is Next.js 15 with two route groups (/app for players, /admin for operators), consuming the FastAPI backend over REST + JWT.

The highest risks are operational correctness (wallet race conditions, double settlement, settling Polymarket markets on closed before the 2h UMA dispute window closes) and regulatory posture (play tokens must be strictly non-transferable and non-redeemable to stay outside Spain Ley 13/2011). The demo trap -- cutting corners because it is only a demo -- is the main confirmed killer: a buyer engineer will inspect the code and credentials, and any shortcut is a lost sale.
---

## Recommended Stack

Load-bearing decisions only. Full versions and rationale in STACK.md.

- **Python 3.12** -- stable sweet spot; avoids 3.13 GIL friction and Celery 5.6 immaturity on 3.14
- **FastAPI 0.115.x + Pydantic 2.10+** -- pin the 0.115 minor; 0.x means minor bumps can break
- **SQLAlchemy 2.0 async (Mapped[], AsyncSession) + asyncpg** -- modern API only; never 1.4-style query(Model).filter(); asyncpg returns Decimal natively for NUMERIC columns
- **Alembic 1.14 (sync engine via psycopg2-binary)** -- migrations always run sync even though the app is async
- **fastapi-users v14 (Argon2 default, maintenance mode)** -- dual auth backends: HTTP-only cookie for the player SPA, Bearer JWT for admin; do NOT pull in passlib
- **Celery 5.5 + celery-redbeat + Redis 7** -- matches live-bets stack; pin 5.5 (5.6 too fresh Mar 2026); RedBeat survives Beat restarts; APScheduler not viable for multi-worker deployments
- **Custom httpx + tenacity Polymarket client (~150 lines)** -- full control over the audit-critical replication path; polymarket-apis PyPI brings too much surface for read-only Gamma use
- **Postgres NUMERIC(18,4) for all money columns; Python Decimal everywhere** -- never FLOAT, REAL, or Postgres MONEY
- **Next.js 15 App Router + React 19 + Tailwind 4 + shadcn/ui v3** -- cookies()/headers() are now async; fetch is not cached by default; all-in on App Router
- **TanStack Query v5 (client data) + Zustand v5 (UI state) + react-hook-form + zod** -- skip Redux / Jotai / SWR
- **Railway for v1 staging** -- managed Postgres + Redis plugins; simple service model matching docker-compose; re-evaluate Fly.io when multi-region or cost exceeds $100/mo
- **structlog + sentry-sdk[fastapi,celery,sqlalchemy]** -- not loguru (no OpenTelemetry integration)
---

## Table Stakes Features

Features that MUST be in v1.0. Missing any fails the demo or the operator says incomplete. Full analysis in FEATURES.md.

**End-user:**
- Register / login / logout / password reset / email verification (production-grade, Argon2)
- Market list / browse home -- top-25 Polymarket mirrors + house markets, sorted by volume
- Market detail page -- question, resolution criteria, price chart, order entry, recent activity
- Buy YES / Buy NO at current price (no order book, no cash-out before resolution)
- Real-time price updates via WebSocket (polling-only UX reads as broken in 2026)
- Wallet balance display + full transaction history
- Portfolio page -- open positions, settled positions, P&L per bet
- Bet confirmation with receipt (stake, expected payout, outcome)
- Resolution display -- outcome, source (oracle or admin), settlement timestamp, user payout
- Responsive mobile web
- Sign-up bonus (configurable amount, awarded on email verify)

**Operator / admin:**
- Admin login with separate role and route guards (not shared with player login surface)
- User list + search + detail view
- Manual balance recharge with reason field (audit-logged)
- Ban / unban user (audit-logged state machine)
- House market create / edit / close
- House market manual resolution with justification text + two-step confirm
- Market list covering all sources and statuses
- KPI dashboard -- volume, DAU, active markets, pending resolutions, house P&L
- Audit log viewer (read-only, immutable)
- Force-settle / manual override for stuck markets (two-step confirm + mandatory log)
- CSV export for users, transactions, bets

**Platform:**
- Double-entry ledger (accounts + transfers + entries tables, append-only, ACID-bound)
- Immutable audit log (trigger blocking UPDATE/DELETE)
- ACID transactions wrapping bet placement and settlement (single transaction each, no split commits)
- Rate limiting on auth and bet endpoints via slowapi + Redis
- Configurable branding (logo, palette, brand name) loaded from single-row settings table
- Polymarket Gamma API sync via Celery Beat (30s poll + 60s resolution scan)
- Transactional email (verification, password reset) via Celery task
- tenant_id ghost column on every player-owned and market table (nullable, default constant)
- Stripe stub interface -- disabled UI button + WalletService.recharge(payment_provider=) method ready
- Feature flags scaffold (single table, prep for per-tenant config in v2)
---

## Anti-Features

Do NOT build these in v1. Full list with rationale in FEATURES.md.

| What | Why not in v1 |
|------|---------------|
| Order book / limit orders | 5-10x complexity; play-money users do not need it |
| Sell position before resolution (cash-out) | Requires AMM or bid/ask spread; explicitly excluded in PROJECT.md |
| Real money / fiat / crypto | Licensing (DGOJ Spain), KYC, AML -- months of legal work; validate first |
| Multi-tenant runtime (RLS, per-tenant routing) | Single tenant in v1; tenant_id ghost column is the preparation |
| Native mobile apps (iOS/Android) | Extra codebases + app store reviews; responsive web sufficient for demo |
| Full Polymarket catalog (10,000+ markets) | Triggers search/filters/pagination that add no demo value |
| User-created markets | Moderation, spam, abuse; B2B2C model requires operator-curated catalog |
| Push notifications | Service workers, FCM/APNS; distraction from core |
| Marketing / drip email | GDPR compliance, email reputation -- not needed for sales demo |
| Token purchase (users buy with fiat) | Adds consideration element -- Spain Ley 13/2011 gambling definition |
| Token transfers between users | Creates secondary market; hard-block at DB level is non-negotiable |
| Leaderboard prizes with monetary value | Adds prize element -- gambling definition; glory-only leaderboard fine in v1.5 |
| Real-time dispute system (UMA replica) | UMA is on-chain and complex; admin manual override is the v1 path |
| Comment threads | Moderation cost; not what sells XPredict to operators |
---

## Architecture Decisions

The 6 most consequential decisions. Full patterns, flows, and schema in ARCHITECTURE.md.

### 1. Modular Monolith (not microservices)

One deployable codebase split into bounded-context modules (auth, wallet, markets, bets, settlement, admin, branding). Cross-module calls go through service interfaces only -- never direct repo access across boundaries. SettlementService is the sole cross-cutting orchestrator. This preserves full ACID across modules, eliminates distributed-transaction complexity, and makes a future service split mechanical rather than architectural. Two developers have no operational appetite for a service mesh.

### 2. MarketSource Protocol adapter

A Python Protocol defines fetch_active_markets(), fetch_market(), and detect_resolution(). PolymarketAdapter and HouseAdapter implement it. app/integrations/ is the only code that knows Polymarket HTTP quirks (stringified-JSON fields, closed vs resolved distinction, UMA timing). All settlement, bet, and market-display code is source-agnostic. Adding live-bets later equals one new file and one registry entry. This is the most important decision for long-term maintainability.

### 3. Custom double-entry ledger (Postgres-native)

Three tables: accounts (where money sits: user_wallet, market_liability, house_revenue, house_expense), transfers (one row per business event with idempotency_key UNIQUE), entries (debit/credit pairs summing to zero, APPEND-ONLY via trigger). Balance columns on accounts are denormalized caches reconciled nightly; truth is in entries. All money columns NUMERIC(18,4). Built in Phase 3, before any bet code exists. TigerBeetle is overkill; pgledger gives up schema ownership.

### 4. tenant_id ghost column on all player-owned tables

Every tenant-scoped table has a nullable tenant_id UUID column defaulting to a fixed constant. Repository interfaces accept tenant_id but use the default in v1. Auth middleware sets SET LOCAL app.tenant_id per request, which becomes load-bearing in v2. Migration to multi-tenant in v2: alter columns to NOT NULL + add Postgres RLS + subdomain-to-tenant middleware. Backfilling tenant_id retroactively is a multi-month rewrite -- never acceptable.

### 5. House-first, Polymarket-second build order

Phase 4 builds house markets and HouseAdapter WITHOUT touching Polymarket. This proves the MarketSource interface with fully-controllable data, delivers a demoable end-to-end happy path in Phase 5 (bet + settlement on house markets), and means the Polymarket adapter in Phase 6 is the second validated implementation of an existing interface.

### 6. NUMERIC(18,4) + Python Decimal everywhere (never float)

Financial amounts use NUMERIC(18,4) in Postgres and Decimal in Python, constructed from strings not floats. Locked in at schema design in Phase 1 and not renegotiable. Rounding drift in play-money is invisible until the nightly reconciliation fails and a buyer engineer notices.
---

## Critical Pitfalls

Top 7 from PITFALLS.md. Full analysis, warning signs, and recovery strategies are in PITFALLS.md.

| # | Pitfall | Severity | Mitigation |
|---|---------|----------|------------|
| 1 | Wallet race condition -- double-spend or negative balance | CRITICAL | SELECT ... FOR UPDATE on wallet row inside the same transaction as ledger insert; CHECK (balance >= 0) DB constraint as final guard |
| 2 | Settling on closed instead of confirmed resolved (Polymarket UMA 2h dispute window) | CRITICAL | Never settle on closed: true; settle only after UMA confirms final outcome + internal grace period; build reversal path from day one |
| 3 | Play tokens cross the gambling line (Spain Ley 13/2011) | CRITICAL | Hard-code non-transferability at DB level; zero redemption paths; no monetary-value prizes; operator signs binding policy before any demo |
| 4 | Non-idempotent settlement pays twice (Celery at-least-once delivery) | CRITICAL | WHERE settled_at IS NULL guard on every settlement query; (bet_id, event_type) unique constraint on ledger entries; Redis lock via celery-once keyed on market_id |
| 5 | No transaction boundary between bet placement and ledger insert | CRITICAL | Single DB transaction wraps: lock wallet row + check balance + insert bet + insert ledger entries + update balance cache + commit; no split commits |
| 6 | Decimal/float rounding drift corrupts the ledger | HIGH | NUMERIC(18,4) on every money column; Python Decimal from strings everywhere; nightly reconciliation Celery task alerts on any drift |
| 7 | House market resolved without audit trail or rollback | HIGH | Resolution criteria locked at market creation; two-step confirm flow; full audit event with proposer + confirmer + evidence text; reversals via compensating entries, never DELETE |

Demo trap corollary: float money, hardcoded secrets, settling on closed, skipping wallet locks, weak passwords, no audit log, no auth rate-limiting are NEVER acceptable even in demo. A buyer engineer will find every one of them and the sale is over.
---

## Suggested Phase Order

Reconciles ARCHITECTURE.md 12-phase plan, STACK.md 9-phase plan, and PITFALLS.md phase mappings. Output: 10 phases, each independently shippable and demoable. No timeline -- quality over velocity.

| # | Phase | Primary Goal | Key Dependencies |
|---|-------|--------------|-----------------|
| 1 | Project Scaffold + Infra | Docker compose (api, worker, beat, db, redis, frontend, mailpit), Postgres 16, Redis 7, FastAPI + Next.js hello-world, Alembic, CI, money column type standards locked, tenant_id pattern established, structlog + Sentry wired | Root -- no dependencies |
| 2 | Auth + Users | Registration, login, sessions (cookie + JWT dual-backend), Argon2, email verification, password reset, admin role flag, refresh token table, rate-limiting on all auth endpoints | Phase 1 |
| 3 | Wallet + Double-Entry Ledger | accounts + transfers + entries schema, wallet created on user registration, balance derivation, CHECK (balance >= 0), idempotency key on transfers, admin recharge endpoint, nightly reconciliation task skeleton | Phase 2 (users must exist) |
| 4 | Markets Domain + House Adapter | Market, Outcome, OddsSnapshot models, MarketSource Protocol defined, HouseAdapter implemented, admin CRUD for house markets (create/edit/set-odds/close), market list + detail pages (no bets yet), tenant_id on all market tables | Phase 1 |
| 5 | Bets + Settlement (house markets only) | Place bet, wallet lock via BET_LOCK ledger entry, admin resolves house market (two-step confirm + justification), SettlementService payout/loss entries, portfolio page with P&L | Phase 3 (ledger) + Phase 4 (markets); PITFALLS #1 #5 #7 are verification gates |
| 6 | Polymarket Adapter + Sync | PolymarketClient (httpx, tenacity, Redis dedupe lock), PolymarketAdapter implements MarketSource, MarketSyncService, Celery Beat schedule (30s poll + 5min odds snapshot), top-25 mirrored in DB, closed vs resolved distinction enforced | Phase 4 (MarketSource must exist), Phase 1 (Celery + Redis); PITFALL #2 is a hard verification gate |
| 7 | Polymarket Resolution Detection + Auto-Settlement | detect_resolutions Beat task (60s), UMA grace period logic, SettlementService.resolve_market() triggered (same code as Phase 5), audit log of resolution events, idempotent settlement tests | Phase 5 (SettlementService must exist), Phase 6 (sync running) |
| 8 | Admin Panel + CRM | Next.js /admin routes: user list/search/detail, ban/unban, recharge form, market list (all sources), house market create/edit/resolve UI, audit log viewer, force-settle override, CSV export | Phases 2-7 provide the backend; Phase 8 is UI on top |
| 9 | User App Polish | Market list home (cards with odds/deadline/volume), market detail (price chart, order entry, recent activity), buy YES/NO flow with confirmation modal, wallet history, portfolio page, WebSocket price feed, responsive mobile, empty/loading/error states, sign-up bonus | Phases 2-7 all needed |
| 10 | Admin Dashboard + Branding + Hardening | KPI dashboard with Recharts, TenantConfig CRUD (logo/palette/brand name), frontend reads config at runtime, rate-limit tuning, Sentry alert rules, Looks Done But Isnt checklist execution, prod-migration dry-run | All previous phases; this is the gate before any operator demo |

Hard dependencies (cannot reorder):
- 1 -> 2 -> 3 -> 5 (scaffold -> auth -> ledger -> settlement)
- 1 -> 4 -> 5 (scaffold -> market domain -> bets)
- 4 -> 6 (MarketSource interface before PolymarketAdapter)
- 5 -> 7 (SettlementService before resolution detection)
- 6 -> 7 (sync running before resolution detection)

Phases that benefit from --research-phase during planning:
- Phase 3 (Wallet + Ledger) -- concurrent locking patterns in SQLAlchemy async are non-obvious; recommend spike if Cuco has not implemented double-entry before
- Phase 6 (Polymarket integration) -- Gamma API schema quirks (stringified JSON, closed vs resolved, UMA timing) justify a spike; STACK.md section 2 and PITFALLS.md pitfalls #2 and #9 are the primary reference

Phases with well-documented patterns (skip research):
- Phases 1, 2, 4, 8, 9, 10 -- scaffold, fastapi-users, standard CRUD domain, admin UI, Next.js UI, config/hardening
---

## Open Questions

Must be resolved during requirements definition or early phase planning.

1. **Email provider for production** -- Mailpit for dev; Resend/Postmark/SES for staging/prod with verified domain + SPF/DKIM/DMARC. Decision needed before Phase 2 ships to staging.
2. **House markets: binary-only (YES/NO) or multi-outcome in v1?** Schema supports both (outcomes is one-to-many). Recommend binary-only v1, extend in v1.5.
3. **Configurable bet limits per user / per market?** Industry standard; not in PROJECT.md. Recommend global default with per-user override stored in TenantConfig.
4. **Email verification gate: block betting only, or all activity?** Recommend browse-allowed, bet-blocked until verified.
5. **What happens to a banned user balance?** Recommend frozen (visible, cannot bet) + admin can issue manual adjustment with audit reason. No silent zeroing.
6. **Mirrored Polymarket market visual treatment** -- Synced from Polymarket badge + link to source? Recommend yes: adds credibility, differentiates from house markets.
7. **Resolution justification on house markets: public to players or internal only?** Recommend public. Transparency is the primary trust signal.
8. **Admin role: boolean is_admin flag or separate RBAC table?** Recommend boolean flag in v1; RBAC table in v1.5 if needed.
9. **Leaderboard in v1.0 or v1.5?** Recommend v1.5 -- requires settled bets to be interesting; not demoable on launch day.
10. **Regulatory review timing** -- Spanish legal counsel must review ToS and token policy before any demo to an operator. Not deferrable.
---

## Confidence Assessment

| Area | Confidence | Basis |
|------|------------|-------|
| Stack versions and library choices | HIGH | Context7 + PyPI + official docs mid-2026; few speculative choices |
| Feature set (table stakes vs differentiators) | HIGH | Multi-source: Polymarket, Kalshi, Manifold, white-label SaaS references |
| Architecture patterns and build order | HIGH | Standard patterns (modular monolith, double-entry, adapter); build order has clear dependency rationale |
| Polymarket Gamma API integration specifics | MEDIUM-HIGH | Schema verified; closed vs resolved confirmed in docs + community writeups; no live integration test yet |
| Regulatory posture (Spain Ley 13/2011) | MEDIUM-HIGH | Official law + ICLG + Chambers sources; jurisdiction-specific advice must come from a lawyer before any operator deal |
| Multi-tenant migration path | HIGH | Well-documented pattern (Bytebase, Clerk, AWS RLS); tenant_id ghost column is industry standard |
---

## Sources (aggregated)

Full source lists with URLs are in each individual research file.

- **STACK.md** -- Context7 verified docs, PyPI, official FastAPI / SQLAlchemy / Celery / Next.js / shadcn docs, Railway vs Fly comparison
- **FEATURES.md** -- Polymarket, Kalshi, Manifold Markets, white-label SaaS industry references, sportsbook UX guides, iGaming KPI references
- **ARCHITECTURE.md** -- Polymarket Gamma API docs, FastAPI architecture guides, Modern Treasury ledger series, Bytebase/Clerk multi-tenancy guides
- **PITFALLS.md** -- Official Polymarket + UMA Oracle docs, Spain BOE Ley 13/2011, ICLG Gambling Spain 2026, OWASP auth recommendations, Modern Treasury concurrency control, Fenwick/Venable virtual currency law
---

*Synthesis of: STACK.md + FEATURES.md + ARCHITECTURE.md + PITFALLS.md*
*Project: XPredict -- white-label play-money prediction market platform*
*Synthesized: 2026-05-25*
