# Roadmap: XPredict

**Mode:** mvp (Vertical MVP)
**Granularity:** fine (11 phases)
**Created:** 2026-05-25
**Total v1 requirements:** 69 (all mapped, no orphans)

## Overview

XPredict ships in 11 vertically-sliced phases, each independently shippable and demoable. The build order respects the architectural dependencies surfaced by research: foundation (scaffold, auth, ledger) is horizontal by necessity but kept atomic; from Phase 4 onward each phase adds one demoable capability on top of the prior stack.

The **first end-to-end demoable happy path** lands at **Phase 5**: a logged-in, email-verified player places a play-money bet on a house market, the admin resolves the market, the wallet is credited via the double-entry ledger, and the resolution audit trail is publicly visible — with zero dependency on Polymarket. From Phase 6 onward, Polymarket data and resolution are layered in by reusing the `MarketSource` Protocol and the `SettlementService` that already exist. The **operator-ready demo gate** is **Phase 11**, after KPI dashboard, branding, and the "Looks Done But Isn't" hardening checklist.

Phase numbering is sequential integers (1-11). Decimal phases (e.g., 2.1) are reserved for urgent insertions after planning starts. Dependencies are strict — no phase begins before its prerequisites have shipped.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

- [x] **Phase 1: Project Scaffold, Infra & Cross-Cutting Foundations** - Docker compose stack, FastAPI + Next.js hello-world, Postgres 16 + Redis 7, Alembic, money-column standards, `tenant_id` ghost column, audit-log trigger, Sentry, secrets hygiene, gitleaks in CI. **Executed + Verified 2026-05-26 (4/4 plans, ~83 min; 41/41 backend + 2/2 frontend tests green; 9/9 UAT complete — cold-start fix applied, code review 37 fixes merged).**
- [x] **Phase 2: Auth & Identity** - Player + admin authentication (Argon2id via fastapi-users v14, dual cookie/JWT backends), email verification, password reset, refresh-token rotation, rate-limiting on all auth endpoints.
 (completed 2026-05-27)

- [x] **Phase 3: Wallet & Double-Entry Ledger** - `accounts` + `transfers` + `entries` schema (append-only, immutable, ACID-bound), `NUMERIC(18,4)` everywhere, idempotent transfers, `CHECK (balance >= 0)`, admin recharge primitive, Stripe stub interface, nightly reconciliation. (completed 2026-05-27)
- [ ] **Phase 4: Markets Domain & HouseAdapter** - `MarketSource` Protocol, Market/Outcome/OddsSnapshot models, HouseAdapter implementation, admin CRUD for house markets (create/edit-while-zero-bets/close), criteria locked at first bet.
- [ ] **Phase 5: Bets, Settlement & First End-to-End Demo (House Markets Only)** - Place-bet flow (ACID-wrapped, idempotent), portfolio with P&L, sign-up bonus on email verify, admin two-step resolve with mandatory justification, idempotent SettlementService, reversal path. **First demoable happy path lands here.**
- [x] **Phase 6: Polymarket Sync (Catalog Replication)** - Custom httpx + tenacity Gamma client, PolymarketAdapter implements `MarketSource`, Celery Beat 30s top-25 poll + 5min odds snapshot, Redis distributed lock for dedupe, `closed` vs `resolved` distinction enforced. (completed 2026-05-28)
- [ ] **Phase 7: Polymarket Auto-Resolution & Admin Override** - `detect_resolutions` Beat task (60s) with UMA dispute-window + internal grace, reuses Phase 5 SettlementService, admin force-settle override for stuck mirrored markets.
- [ ] **Phase 8: Admin CRM (User Management & Audit Log Viewer)** - Paginated user list with search/filters, user detail page (profile + balance + history + bets), ban/unban state machine with frozen-balance semantics, CSV export, immutable audit-log viewer.
- [ ] **Phase 9: User App UX Polish (Market Detail & Real-Time)** - Market detail page with resolution criteria + price-history chart + activity feed, real-time WebSocket price updates for mirrored polls + house edits.
- [ ] **Phase 10: Admin KPI Dashboard & Configurable Branding** - Admin landing dashboard (24h volume, DAU, active markets, pending resolutions, house P&L) with Recharts, TenantConfig CRUD (brand name/logo/palette), runtime branding consumption in player UI.
- [ ] **Phase 11: Hardening & Operator-Demo Gate** - Mobile responsiveness validation (≥360px), Sentry alert rule tuning, rate-limit tuning, "Looks Done But Isn't" checklist execution, prod-migration dry-run, security scan (gitleaks/bandit/npm audit/OWASP ZAP). **Final gate before any operator demo.**

## Phase Details

### Phase 1: Project Scaffold, Infra & Cross-Cutting Foundations

**Goal**: Provide a one-command local stack and lock in the non-negotiable foundations (money types, tenant seam, audit immutability, secrets hygiene, observability) so every later phase inherits them for free.
**Depends on**: Nothing (first phase)
**Requirements**: PLT-01, PLT-02, PLT-03, PLT-04, PLT-06, PLT-08, PLT-10, WAL-05
**Success Criteria** (what must be TRUE):

  1. `docker-compose up` brings the full stack (api, worker, beat, db, redis, frontend, mailpit) online with one command and a healthcheck passes for each service.
  2. Alembic migration 0001 exists and includes the `tenant_id UUID` ghost column (nullable, defaulting to a fixed constant) on every player-owned and market table that will exist in v1.
  3. The `audit_log` table is created with a Postgres trigger that blocks `UPDATE` and `DELETE`; an integration test demonstrates both operations raise.
  4. Money-column coding standard is documented and enforced: a CI lint fails any new SQLAlchemy `Mapped` annotation for a money field that is not `Decimal` + `Numeric(18,4)`; no `FLOAT`/`REAL`/`MONEY` types appear in the schema.
  5. `gitleaks` runs in CI and blocks a test commit that contains a fake secret; Sentry receives a synthetic error from FastAPI, Celery worker, and Next.js (three separate test triggers) and the events appear in the configured Sentry project.

**Plans**: 4 plans
**Plan list**:

- [x] 01-01-PLAN.md — Backend Python scaffold: pyproject.toml + Settings + Money alias + structlog + Sentry helpers + FastAPI/Celery factories + money-column AST lint + Wave-0 unit tests (PLT-03, PLT-08, WAL-05) — **shipped 2026-05-26, 26 min, 30 tests passing**
- [x] 01-02-PLAN.md — Frontend Next.js 15 + Tailwind 4 + TypeScript scaffold with Sentry on server + client surfaces + /api/healthz + /api/sentry-test + Vitest (PLT-08, PLT-10) — **shipped 2026-05-26, 12 min, 2 Vitest tests green**
- [x] 01-03-PLAN.md — docker-compose.yml (8 services) + Alembic baseline 0001 (audit_log + feature_flags with ghost column + immutability trigger + seeded flags) + integration tests against testcontainers Postgres + docker-compose smoke (PLT-01, PLT-02, PLT-06, PLT-10) — **shipped 2026-05-26, 13 min, 9 integration tests green (39/39 total); Task 3 runtime acceptance manual-verify gated by host port conflicts**
- [x] 01-04-PLAN.md — gitleaks + pre-commit + GitHub Actions (backend-ci, frontend-ci, security) + bin/dev + README + Phase 1 acceptance gate (PLT-04, PLT-08, PLT-10) — **shipped 2026-05-26, ~32 min, 6 atomic commits; 41/41 backend + 2/2 frontend tests green; acceptance gate auto-approved per --auto mode (3.5/5 ROADMAP SC ✓ machine-verified; 1.5/5 manual-verify deferred to /gsd-verify-work)**

**Research/spike flags**: None — well-documented patterns.
**Critical pitfalls covered**: PITFALL #3 (regulatory — secrets/ToS posture begins here), PITFALL #4 (Decimal/NUMERIC locked at schema), PITFALL #7 (connection-pool / SET LOCAL discipline established).

### Phase 2: Auth & Identity

**Goal**: Players and admins can authenticate against a production-grade auth surface with verified email, persistent sessions, password reset, and rate-limited endpoints — distinct surfaces for player (cookie) and admin (Bearer).
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: AUTH-01, AUTH-02, AUTH-03, AUTH-04, AUTH-05, AUTH-06, AUTH-07, AUTH-08, AUTH-09
**Success Criteria** (what must be TRUE):

  1. A player can register with email + password; the password is stored as an Argon2id hash; server-side strength validation rejects weak passwords; a verification email lands in Mailpit.
  2. A player who clicks the (single-use, time-limited) verification link from the email transitions to `email_verified` and is redirected to a logged-in state that persists across browser refresh.
  3. A player can log out from any page; the refresh token is server-side revoked (verifiable in the `refresh_tokens` table) and the next API call with the prior cookie returns 401.
  4. A player can request a password reset; the reset link is single-use and time-limited; completing reset bumps `token_version` and invalidates all prior sessions across devices (verifiable: a request with a pre-reset access token returns 401).
  5. An admin authenticates via a distinct `/admin/login` route, receives a Bearer JWT (not a cookie), and the `is_admin` flag is enforced on every admin endpoint; a non-admin Bearer is 403 on `/admin/*`.
  6. The `/auth/login`, `/auth/register`, `/auth/forgot-password`, and `/auth/verify-email` endpoints are rate-limited per-IP and per-email via slowapi + Redis; the 6th login attempt within the configured window returns 429 with no information leak about whether the email exists.

**Plans**: 5 plans
**Plan list**:

- [x] 02-01-PLAN.md — Schema foundation: pyproject deps (fastapi-users v15.0.5 + resend + aiosmtplib) + Settings env-var expansion + User/RefreshToken ORM + Alembic migration 0002 (AUTH-01, AUTH-09)
- [x] 02-02-PLAN.md — Player auth surface: EmailService + custom DatabaseStrategy + UserManager + slowapi rate limiting + FastAPIUsers cookie backend + 8 integration tests (AUTH-01..06, 08, 09)
- [x] 02-03-PLAN.md — Admin auth surface: BearerTransport + cross-surface isolation tests + bin/create_admin.py idempotent seeding (AUTH-07, AUTH-08, AUTH-09)
- [x] 02-04-PLAN.md — Frontend player pages: shadcn/ui + zod + react-hook-form + 5 auth pages (/login, /register, /forgot-password, /reset-password, /verify-email) + 5 Server Actions (AUTH-01..04, AUTH-06)
- [x] 02-05-PLAN.md — Frontend admin: Edge middleware with jose HS256 verify + /admin/login + admin layout + placeholder /admin landing + adminLoginAction (AUTH-07, AUTH-09)

**Research/spike flags**: None — fastapi-users v15 has well-documented dual-backend pattern (researcher correction: CONTEXT D-01 said v14; v15.0.5 is API-compatible for our usage and is the current pinned version per RESEARCH §Standard Stack).
**Critical pitfalls covered**: PITFALL #8 (refresh-token rotation + revocation; Argon2id; rate-limit; email enumeration prevention; HTTP-only Secure SameSite cookies).

### Phase 3: Wallet & Double-Entry Ledger

**Goal**: Build the financial backbone before any bet code touches a balance integer: append-only ledger, race-condition-proof transfers, idempotency, and reconciliation — the engine that all later money-touching phases inherit.
**Mode:** mvp
**Depends on**: Phase 2 (need users for wallet ownership and admin flag for recharge)
**Requirements**: WAL-01, WAL-03, WAL-04, WAL-06, WAL-07, WAL-08, WAL-09, PLT-05, PLT-09
**Success Criteria** (what must be TRUE):

  1. When a verified player registers, exactly one `accounts` row of kind `user_wallet` (currency `PLAY_USD`, balance 0) is created in the same transaction as the user row; an integration test asserts the wallet exists.
  2. A concurrent test that fires 50 simultaneous "spend 50% of balance" transfers against the same wallet completes with the final balance exactly equal to expected and zero ledger drift; `CHECK (balance >= 0)` rejects any attempt to overdraw.
  3. Calling the admin recharge endpoint twice with the same `Idempotency-Key` produces exactly one transfer and one set of paired ledger entries (debit `house_promo` → credit `user_wallet`); the second call returns the same transfer ID with no double-credit.
  4. The player can fetch their current balance and a paginated transaction history showing every entry (kind, amount, timestamp, reason) with no money column ever exposed as a JSON float — all amounts are strings in the API response.
  5. No database path, REST endpoint, GraphQL resolver, or admin tool exists to transfer balance from one user to another; an automated negative test asserts every wallet-mutation API rejects a `dst_user_id` parameter, and the schema has no FK that would allow it.
  6. A disabled "Add funds" button is present in the player UI; `WalletService.recharge(payment_provider="stripe")` exists as a method signature that raises `NotImplementedError` (v2 wires it without refactor).
  7. The nightly Celery `reconcile_wallets` task runs against seed data, computes `SUM(entries)` per account, compares to `accounts.balance`, and the reconciliation log shows zero drift; if a synthetic drift is injected, the task logs CRITICAL and a Sentry alert fires.**Plans**: 6 plans

**Wave 1**

  - [x] 03-01-PLAN.md — Ledger schema + migration 0003 (accounts/transfers/entries, immutability, CHECK, seed) + Wave-0 scaffold [W1]

**Wave 2** *(blocked on Wave 1 completion)*

  - [x] 03-02-PLAN.md — WalletService engine (FOR UPDATE, atomic double-entry, idempotency, canonical lock order) + SC#2 concurrent gate [W2]

**Wave 3** *(blocked on Wave 2 completion)*

  - [x] 03-03-PLAN.md — Registration wallet auto-creation in one transaction (SC#1, UserManager.create override) [W3]
  - [x] 03-04-PLAN.md — Admin recharge endpoint + Idempotency-Key (SC#3) + no-user-to-user firewall (SC#5) [W3]
  - [x] 03-06-PLAN.md — Nightly reconcile_wallets Celery task: SUM(entries) vs balance, drift -> CRITICAL + Sentry (SC#7) [W3]

**Wave 4** *(blocked on Wave 3 completion)*

  - [x] 03-05-PLAN.md — Player reads (balance + paginated history, money-as-string SC#4) + Stripe stub + disabled Add funds button (SC#6) [W4]

**Research/spike flags**: **SPIKE COMPLETE** — concurrent locking resolved by Spikes 001-004 (FOR UPDATE chosen; see `.planning/spikes/LOCKING-ATOMICITY-ANALYSIS.md`). Original note: **SPIKE recommended** — concurrent locking patterns in SQLAlchemy 2.0 async (`SELECT ... FOR UPDATE` inside `AsyncSession.begin()`, deadlock ordering, retry-on-serialization-failure) are non-obvious; recommend a 1-2 hour spike via `/gsd-spike` before planning if Cuco hasn't implemented async double-entry before. PITFALLS.md §"Wallet / Ledger Correctness" is the primary reference.
**Critical pitfalls covered**: PITFALL #1 (wallet race conditions via `FOR UPDATE` + `CHECK (balance >= 0)`), PITFALL #4 (NUMERIC + Decimal end-to-end), PITFALL #10 (single-transaction discipline established; pattern that bet placement in Phase 5 will reuse).

### Phase 4: Markets Domain & HouseAdapter

**Goal**: Establish the source-agnostic market domain (Market, Outcome, OddsSnapshot) and prove the `MarketSource` Protocol with a fully-controllable HouseAdapter — no external dependency, no Polymarket yet. Admin can author and operate house markets end-to-end.
**Mode:** mvp
**Depends on**: Phase 1 (need scaffold + tenant_id), Phase 2 (need admin role for CRUD)
**Requirements**: MKT-07, MKT-08, ADM-01, ADM-02, ADM-03, ADM-04, ADM-07
**Success Criteria** (what must be TRUE):

  1. The `MarketSource` Python Protocol is defined in `app/integrations/market_source.py` with `fetch_active_markets()`, `fetch_market()`, and `detect_resolution()`; `HouseAdapter` implements it and is registered in the source registry.
  2. An admin can create a binary (YES/NO) house market via the admin API with question, resolution criteria, deadline, initial odds (default 50/50), and optional category; the market appears in the admin market list with `source = HOUSE` and `status = OPEN`.
  3. The admin market list endpoint returns paginated markets across sources (only HOUSE in this phase; PolymarketAdapter not yet present) with filters for source, status, and category working as documented.
  4. An admin can edit a house market's odds, deadline, and resolution criteria while it has zero bets; once the first bet lands (Phase 5 wiring is stubbed for this test via a fixture), the criteria field returns 423 Locked on edit and the UI disables it.
  5. An admin can close a house market early (status `OPEN` → `CLOSED`); a follow-up "place bet" attempt against a closed market is rejected at the API with a clear error, even before Phase 5 wires the user-facing bet flow.
  6. The `markets` and `outcomes` tables include `source` + `source_market_id` columns; the schema enforces v1 binary-only (2 outcomes per market) via a deferrable CHECK constraint or trigger, with multi-outcome explicitly flagged as v2.

**Plans**: TBD
**Research/spike flags**: None — Protocol design is straightforward; HouseAdapter is DB-native.
**Critical pitfalls covered**: PITFALL #6 (resolution criteria locked at first bet; foundation for two-step resolve in Phase 5). Sets the stage for PITFALL #2 by making `source` a first-class column — Polymarket-specific logic cannot leak into the domain in Phase 6.

### Phase 5: Bets, Settlement & First End-to-End Demo (House Markets Only)

**Goal**: Deliver the first demoable end-to-end happy path: a verified player with a balance places a bet on a house market, the admin resolves it with a two-step confirm + justification, the wallet is credited via the ledger, and the player sees realized P&L in their portfolio. The `SettlementService` built here is the same code that will be reused in Phase 7 for Polymarket auto-resolution.
**Mode:** mvp
**Depends on**: Phase 3 (ledger must exist before any bet), Phase 4 (market domain must exist), Phase 2 (email verification gate). **This phase is the first vertical demoable milestone of the project.**
**Requirements**: BET-01, BET-02, BET-03, BET-04, BET-05, BET-06, BET-07, STL-02, STL-03, STL-04, STL-05, STL-06, STL-07, ADM-05, WAL-02, ADU-03
**Success Criteria** (what must be TRUE):

  1. A verified player with positive balance can place a bet by selecting outcome (YES/NO) and stake; the bet placement is one ACID transaction (lock wallet row → check balance → insert bet → insert paired ledger entries debit `user_wallet` / credit `market_liability` → update balance cache → commit), and a kill-DB-mid-transaction integration test verifies neither bet nor ledger entries persist on failure.
  2. An unverified-email player can browse all markets but receives a clear UI message and a 403 from the bet API when attempting to place a bet; a separate test asserts the API rejects on both `email_verified_at IS NULL` and `is_banned = true`.
  3. The player sees a bet confirmation modal with stake, current odds, and expected payout before bet creation; configurable per-market min/max stake limits (operator-set via TenantConfig) are enforced both client- and server-side; selling a position before resolution returns 405 at the API.
  4. A new player receives the configured sign-up bonus (default 1000 `PLAY_USD`) credited to their wallet immediately after email verification, via a transfer with `kind = signup_bonus` and a unique `idempotency_key` of `bonus:{user_id}` so re-running verification never double-credits.
  5. An admin resolves a house market via a two-step confirm flow (propose outcome + mandatory justification text → confirm), and the `SettlementService.resolve_market()` call inside one ACID transaction: marks `markets.status = RESOLVED`, marks each bet `SETTLED_WON`/`SETTLED_LOST`, posts paired ledger entries (winners: market_liability → user_wallet; losers: market_liability → house_revenue), and writes one immutable audit_log entry with `market_id`, `resolver`, `winning_outcome`, `total_payout`, `justification`, `settlement_timestamp`.
  6. **Idempotent settlement**: re-invoking `SettlementService.resolve_market()` on the same market is a no-op (guarded by `WHERE markets.settled_at IS NULL` AND `(bet_id, event_type)` UNIQUE on entries); a settlement task replay test produces zero double-payouts.
  7. The player sees a resolution display on each settled market: winning outcome, resolver attribution (`Operator: {admin_display_name}` for house resolutions), public justification text, settlement timestamp, and their own payout/loss; the player portfolio shows open positions (stake, current odds, unrealized P&L) and settled positions (stake, outcome, realized P&L).
  8. An admin can reverse a settlement via compensating ledger entries (never `DELETE`/`UPDATE`); reversal requires a justification, writes an audit_log entry with `event_type = settlement_reversed`, and a reversal-of-reversal test produces a clean balanced ledger.
  9. An admin can manually recharge any user's wallet (separate from sign-up bonus) with a stake amount and mandatory reason; the recharge is audit-logged and uses the idempotent transfer primitive from Phase 3.

**Plans**: TBD
**Research/spike flags**: None — relies on patterns established in Phases 3 and 4.
**Critical pitfalls covered**: PITFALL #1 (re-validated under realistic bet+settle concurrency), PITFALL #5 (idempotent settlement gates verified here; same `SettlementService` reused by Phase 7), PITFALL #6 (two-step admin resolution + audit trail + reversal path), PITFALL #10 (single-transaction bet placement). **All settlement-critical correctness gates from PITFALLS.md "Looks Done But Isn't" must pass in this phase, not deferred to Phase 11.**

### Phase 6: Polymarket Sync (Catalog Replication)

**Goal**: Mirror the top-25 active Polymarket markets into our database via a custom httpx + tenacity Gamma client and a `PolymarketAdapter` that implements the `MarketSource` Protocol from Phase 4. Sync only — no auto-resolution yet, no changes to the bet engine.
**Mode:** mvp
**Depends on**: Phase 4 (MarketSource Protocol must exist), Phase 1 (Celery + Redis + Sentry must exist)
**Requirements**: MKT-01, MKT-02, MKT-05, MKT-06
**Success Criteria** (what must be TRUE):

  1. `PolymarketAdapter` (in `app/integrations/polymarket/`) implements `MarketSource` and passes the same Protocol conformance tests as `HouseAdapter`; the rest of the codebase consumes it via the registry, with no Polymarket-specific imports outside `app/integrations/polymarket/`.
  2. The Celery Beat schedule runs `poll_polymarket_top25` every 30 seconds; each run fetches the top 25 active markets via a single `/markets?active=true&closed=false&order=volume24hr&limit=25` call, dedup-locked via `redis-py` `SETNX` so two overlapping Beat instances cannot double-fetch; the polling log shows ≤2 req/min sustained against the `/markets` endpoint (well under the 300-req/10s limit).
  3. Mirrored markets are persisted with both `source = POLYMARKET`, `source_market_id`, and Polymarket's `condition_id` stored for reverse lookup; an upsert on `(source, source_market_id)` is idempotent; running the poll task twice in a row produces zero duplicate rows.
  4. The player home page market list now shows top-25 mirrored markets + all open house markets, sorted by 24h volume; each card shows question, current YES/NO odds, deadline, total volume, and a source badge ("Synced from Polymarket" with link to source, or "House market").
  5. The `snapshot_odds` task runs every 5 minutes and writes one `odds_snapshots` row per open market outcome (both house and mirrored); the snapshot table is populated for at least one full 30-minute test interval without errors.
  6. The Pydantic parser explicitly handles Polymarket's stringified-JSON fields (`outcomes`, `outcomePrices`, `clobTokenIds` are JSON-decoded; `volume`/`liquidity` parsed to `Decimal` from strings); the parser refuses (`extra='forbid'` in dev, `extra='allow'` + warning log in staging) on unknown fields and logs a structured event so schema drift is detected.
  7. **`closed` vs `resolved` distinction is enforced at the model layer**: the Polymarket mapper sets a market's internal `status` based on a function of `closed`, `umaResolutionStatus`, and `outcomePrices`, and a unit test asserts that a market with `closed=true` but `umaResolutionStatus` not in `{resolved}` does NOT enter our `RESOLVED` state — even though we are not yet auto-settling in this phase.
**Plans**: 3 plans
**Plan list**:
- [x] 06-01-PLAN.md — GammaClient + Pydantic v2 parser + PolymarketAdapter + migration 0004 + Protocol conformance + VCR fixture tests (MKT-05, MKT-06)
- [x] 06-02-PLAN.md — Celery Beat tasks (poll 30s + snapshot 5min) + Redis dedupe lock + house-first market list API (MKT-01, MKT-05, MKT-06)
- [x] 06-03-PLAN.md — Frontend market list: MarketCard + SourceBadge + OddsDisplay + responsive grid home page (MKT-01, MKT-02)
**Research/spike flags**: **SPIKE completed** — spike-002 validated Pydantic v2 parser, state machine, and VCR fixtures. 4 fixture files captured and proven correct.
**Critical pitfalls covered**: PITFALL #2 (closed vs resolved distinction; this phase puts the guard in code even though settlement is in Phase 7), PITFALL #9 (rate-limit math; batch single call instead of per-market loop; tenacity backoff with jitter; Redis dedupe lock; latency monitoring as throttle warning).

### Phase 7: Polymarket Auto-Resolution & Admin Override

**Goal**: Automatically settle mirrored Polymarket markets via the same `SettlementService` built in Phase 5, only after UMA confirms resolution + an internal grace period. Provide an admin force-settle override for stuck markets with a two-step confirm + mandatory justification.
**Mode:** mvp
**Depends on**: Phase 5 (`SettlementService` must exist and be idempotent), Phase 6 (sync must be running so mirrored markets are in our DB)
**Requirements**: STL-01, ADM-06
**Success Criteria** (what must be TRUE):

  1. A new Beat task `detect_polymarket_resolutions` runs every 60 seconds against mirrored markets whose internal status is `OPEN` or `CLOSED` and whose Polymarket `endDate` has passed; it queries `fetch_market(source_market_id)` and computes the resolution state from `umaResolutionStatus` + `outcomePrices` + a configurable internal grace period (default 30 minutes after UMA window close).
  2. When a mirrored market clears the UMA grace check, `SettlementService.resolve_market(market_id, winning_outcome_id, source='POLYMARKET_UMA')` is invoked — the same service from Phase 5 — and the resulting settlement passes the same idempotency, audit-log, and reversal contracts as house settlements. **The settlement service is unchanged; only the trigger differs.**
  3. **Never settle on `closed: true` alone**: an integration test feeds a mock Polymarket response with `closed=true, umaResolutionStatus='proposed'` and asserts no settlement is triggered; only `umaResolutionStatus='resolved'` + grace period satisfied results in `resolve_market()` being called.
  4. The player resolution display correctly attributes Polymarket-resolved markets to `Polymarket UMA` (vs `Operator: {admin_display_name}` for house markets), with a link to the Polymarket source market.
  5. An admin can force-settle a stuck Polymarket-mirrored market via a two-step confirm flow with a mandatory justification text; the force-settle path writes a distinct `event_type = polymarket_admin_override` audit_log entry that includes both the admin's chosen outcome and the Polymarket-reported `umaResolutionStatus` at override time.
  6. A reversal test: simulate a Polymarket resolution flip after our auto-settlement (Polymarket overturns the outcome 24h later); the admin uses the Phase 5 reversal flow; affected players' balances are returned to pre-settlement state via compensating entries; the new audit_log entry chains back to the reversed settlement event.

**Plans**: TBD
**Research/spike flags**: None — relies on patterns established and a fixture set from Phase 6.
**Critical pitfalls covered**: PITFALL #2 (UMA dispute window + grace period gating, never settle on `closed`), PITFALL #5 (idempotent settlement re-verified for the auto-triggered path, especially under Celery at-least-once delivery), PITFALL #6 (reversal mechanism exercised for the overturned-resolution scenario).

### Phase 8: Admin CRM (User Management & Audit Log Viewer)

**Goal**: Give the operator a usable CRM in the admin UI: search/inspect/recharge/ban users, view immutable audit log, and export to CSV — the operator demo's "I can manage my customers" surface.
**Mode:** mvp
**Depends on**: Phase 2 (admin role + auth), Phase 3 (wallet + ledger for recharge UI on top of the primitive), Phase 5 (audit log entries from settlements must exist to be viewable)
**Requirements**: ADU-01, ADU-02, ADU-04, ADU-05, ADU-06, ADD-04
**Success Criteria** (what must be TRUE):

  1. An admin sees a paginated user list at `/admin/users` with search by email and display name, filters for status (active/banned), signup date, and last activity; an admin can sort the list by any of those columns and pagination works for 1000+ test users without timing out (<500ms server-side).
  2. The admin user detail page at `/admin/users/{user_id}` shows profile fields, current wallet balance, full paginated transaction history (every entry from Phase 3), all bets (every entry from Phase 5), and ban status; the recharge form on this page calls the Phase 3 primitive and the result appears in the transaction history within one refresh.
  3. An admin can ban a user (state machine `active` → `banned`); the banned user's next login attempt returns 403; the banned user's wallet balance is visible and immutable (frozen — no silent zeroing); a follow-up bet attempt is rejected at the API; the admin can unban and the balance is restored as-is.
  4. The admin can export filtered subsets of users / transactions / bets to CSV via dedicated endpoints reachable only from the admin UI (not exposed in any public API surface); a CSV-injection-safety negative test (cells beginning with `=`, `+`, `-`, `@`) confirms outputs are escaped.
  5. The audit log viewer at `/admin/audit-log` is read-only, paginated, filterable by `event_type` and `actor_user_id`, and displays every audit entry from Phases 3, 5, and 7; an admin UI attempt to edit a row is blocked (no edit affordance) and a direct DB `UPDATE` test against the audit_log table fails because of the Phase 1 trigger.
  6. A negative auth test confirms every `/admin/*` endpoint added in this phase requires `is_admin = true`; a player-cookie request to `/admin/users` returns 403, and a missing-Bearer request returns 401.

**Plans**: TBD
**Research/spike flags**: None — TanStack Table v8 + shadcn primitives are well-documented for admin tables.
**Critical pitfalls covered**: PITFALL #6 (the audit log viewer makes the immutable trail visible to operators — the demo-trust signal), PITFALL #8 (admin auth surface separation re-verified).
**UI hint**: yes

### Phase 9: User App UX Polish (Market Detail & Real-Time)

**Goal**: Polish the player surface to "feels real" quality: market detail page with resolution criteria, price-history chart, recent-activity feed, and real-time WebSocket price updates that animate on every Polymarket poll and admin odds edit.
**Mode:** mvp
**Depends on**: Phase 6 (need Polymarket sync running so odds_snapshots have data), Phase 5 (need bets to populate the activity feed), Phase 4 (need the market detail structure)
**Requirements**: MKT-03, MKT-04
**Success Criteria** (what must be TRUE):

  1. A player can open the market detail page at `/markets/{slug}` and see question, full description, resolution criteria text (publicly visible — the transparency trust signal), a price history chart powered by `odds_snapshots` from Phase 6, an order entry form (reusing Phase 5's bet flow), and a recent activity feed showing the last N anonymized bets.
  2. The price history chart uses Recharts (matched react-is to React 19 per STACK.md §10) and renders cleanly across 30 days of snapshot data for both mirrored and house markets; a synthetic "30-day backfill" fixture verifies no rendering or performance regression at the 30-day cap.
  3. Market prices update in real-time on the player's open detail page via a backend WebSocket (no polling from the browser); a mirrored market's odds change when a Polymarket poll detects movement, and a house market's odds change when an admin edits them — both reflected in the player UI within 2 seconds without a page refresh.
  4. The WebSocket connection auto-reconnects on disconnect with exponential backoff and a visible "Live" indicator in the UI; a "stale > 30s" badge appears if no updates have arrived in 30s (per PITFALLS.md UX section: explicit staleness, never silent).
  5. Empty / loading / error states are present on the home page, market list, market detail, and portfolio pages (skeleton loaders, friendly empty states, explicit error messages — no generic "transaction failed" toasts on the bet flow per the UX pitfall table).

**Plans**: 4 plans (3 waves)
**Plan list**:

**Wave 1**

- [x] 09-01-PLAN.md — Real-time backend pipeline: lift spike 003 (ConnectionManager + redis.asyncio subscriber + WS /ws/markets/{id}) into app/realtime/, wire lifespan, + both producer hooks (admin odds edit post-commit, Polymarket poll on-change) (MKT-04) [W1]

**Wave 2** *(02 blocked on 01 — shared markets/ files; 03 blocked on 01 — needs the WS endpoint)*

- [x] 09-02-PLAN.md — Backend read surface: GET /{slug}/price-history (server-side 30d downsampling) + GET /{slug}/activity (anonymized last-20) + schemas (MKT-03) [W2]
- [x] 09-03-PLAN.md — Frontend foundation: install Recharts + react-is pin/pnpm-override + Radix dialog/select, PriceHistoryChart, use-market-socket hook (Live/Stale/Reconnecting), LiveIndicator, api.ts fetchers — NOT autonomous (blocking package-legitimacy checkpoint) (MKT-03, MKT-04) [W2] — **shipped 2026-05-29, ~33 min, 3 atomic commits; react-is collapsed to a single version + chart-not-blank smoke test green; chart 4 + hook 4 tests pass; pnpm build clean. Pre-existing orphan middleware.test.ts breaks repo-wide typecheck/full-suite (logged to deferred-items.md, out of scope)**

**Wave 3** *(blocked on 02 + 03)*

- [ ] 09-04-PLAN.md — Market detail page /markets/[slug]: SSR shell + two-column grid, order-entry form → confirm dialog → place_bet (inline error states), anonymized recent-activity feed, skeletons (MKT-03) [W3]

**Research/spike flags**: None — Recharts + WebSocket patterns are well-documented (WS pipeline lifts VALIDATED spike 003).
**Critical pitfalls covered**: UX trust pitfalls (hidden resolution criteria, stale-price masking, opaque error states).
**UI hint**: yes

### Phase 10: Admin KPI Dashboard & Configurable Branding

**Goal**: Replace the admin login landing page with a KPI dashboard (the "is this platform healthy?" 5-second pulse), and give the operator runtime-configurable branding (logo, palette, brand name) — the white-label sales wedge.
**Mode:** mvp
**Depends on**: Phases 2-8 (need the data sources that power the KPIs: users, bets, markets, ledger, audit log)
**Requirements**: ADD-01, ADD-02, ADD-03, ADD-05, ADD-06
**Success Criteria** (what must be TRUE):

  1. Logging in at `/admin/login` lands the admin on the KPI dashboard (`/admin/`) by default, not the user list; a session-storage default-route flag exists so the dashboard remains the landing page across sessions.
  2. The dashboard shows the five required cards: 24h bet volume, daily active users (configurable rolling window, default 24h), total active markets count, pending resolutions count (mirrored markets past `endDate` + house markets past their deadline awaiting admin action), and house P&L (today + cumulative — derived from `SUM(house_revenue) - SUM(house_expense)` across the ledger).
  3. The volume-over-time chart uses Recharts with daily granularity for the first 30 days of activity (and a 30-day-empty empty-state for a fresh deployment); a synthetic 30-day fixture verifies the chart renders correctly without slowdowns.
  4. An admin can configure instance branding (brand name, logo image, primary/secondary palette colors) via an admin form persisted to a single-row `tenant_config` table; the form rejects invalid hex colors and oversized logos with clear error messages.
  5. The player-facing UI reads branding config at runtime (Next.js Server Components `await` an API call to `/branding/current`); changing the palette in admin updates the player UI on next page navigation without any rebuild or redeploy step, verifiable by a manual test of swapping palette mid-session.
  6. A negative test confirms admin endpoints in this phase enforce `is_admin = true` (consistent with Phase 8); a player request to `/admin/tenant-config` returns 403.

**Plans**: TBD
**Research/spike flags**: None — Recharts + CSS variables theming via shadcn/ui are well-documented.
**Critical pitfalls covered**: Demo-trap branding (the trait that distinguishes "looks like a real product" from "another bootstrap demo" — see FEATURES.md trust signals).
**UI hint**: yes

### Phase 11: Hardening & Operator-Demo Gate

**Goal**: Final gate before any operator demo: validate mobile responsiveness end-to-end, tune rate limits and Sentry alert rules against realistic load, execute the "Looks Done But Isn't" checklist from PITFALLS.md, run prod-migration dry-run and security scan, and ship the regulatory ToS posture review.
**Mode:** mvp
**Depends on**: All previous phases. **This is the operator-ready demo milestone; nothing demos to a real operator until this phase passes.**
**Requirements**: PLT-07
**Success Criteria** (what must be TRUE):

  1. The player-facing UI passes a responsive QA pass on real mobile browsers at widths from 360px to 768px (iOS Safari, Android Chrome, plus desktop Firefox): home page, market detail, bet flow, portfolio, wallet history, and auth flows are all thumb-reachable and readable with no horizontal scroll on any tested width.
  2. The "Looks Done But Isn't" checklist from PITFALLS.md is executed in full and every box ticked (or a documented and approved deferral): wallet/ledger reconciliation, concurrent bet test, settlement idempotency, Polymarket schema drift, auth rate-limits and email enumeration prevention, audit log append-only enforcement, self-bet ban, CORS, secrets scan, tenant_id presence on every table, observability alerts triggered and verified, backup restore tested, Decimal serialization, timezone discipline.
  3. A `prod-migration-dry-run` script runs in CI that replaces every `localhost`, dev secret, and `DEBUG=True` with staging-style values, boots the stack, places a bet end-to-end, settles, and verifies nothing broke; the script catches hardcoded dev URLs or env-var assumptions and fails the build if found.
  4. Security scan suite passes on staging: `gitleaks` (zero findings on full history), `bandit` (no high-severity Python findings), `npm audit` (no high-severity frontend findings), and OWASP ZAP baseline against `/auth/*` and `/bets/*` (no high-severity findings).
  5. Sentry alert rules are configured and synthetically triggered for the four critical scenarios from PROJECT.md: settlement failures, Polymarket sync error-rate spikes, ledger reconciliation drift (Phase 3 task), and auth abuse spikes (failed-login burst); each alert lands in the configured Sentry project's notification channel.
  6. A Spanish-counsel-reviewed Terms of Service and token policy document are linked in the player and admin UI footers; the regulatory posture from PITFALLS.md §"The Regulatory Line" is documented in the repo's `docs/regulatory.md` and the operator-agreement template (operator signs binding policy before any demo) is checked into the repo.

**Plans**: TBD
**Research/spike flags**: None — execution of established checklists.
**Critical pitfalls covered**: PITFALL #3 (regulatory ToS gate before any operator demo), all demo-trap pitfalls (final pass).

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11.

**Vertical milestones:**

- **First demoable end-to-end happy path**: end of **Phase 5** (bet on house market → admin resolves → wallet credited → P&L visible).
- **Operator-ready demo**: end of **Phase 11** (after KPI dashboard, branding, hardening, and ToS gate).

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Project Scaffold, Infra & Cross-Cutting Foundations | 4/4 | Complete    | 2026-05-26 |
| 2. Auth & Identity | 5/5 | Complete    | 2026-05-27 |
| 3. Wallet & Double-Entry Ledger | 6/6 | Complete   | 2026-05-27 |
| 4. Markets Domain & HouseAdapter | 0/TBD | Not started | - |
| 5. Bets, Settlement & First End-to-End Demo (House Markets Only) | 0/TBD | Not started | - |
| 6. Polymarket Sync (Catalog Replication) | 3/3 | Complete   | 2026-05-28 |
| 7. Polymarket Auto-Resolution & Admin Override | 0/TBD | Not started | - |
| 8. Admin CRM (User Management & Audit Log Viewer) | 0/TBD | Not started | - |
| 9. User App UX Polish (Market Detail & Real-Time) | 2/4 | In Progress|  |
| 10. Admin KPI Dashboard & Configurable Branding | 0/TBD | Not started | - |
| 11. Hardening & Operator-Demo Gate | 0/TBD | Not started | - |

## Coverage

**v1 requirements mapped:** 69 / 69 (100%)
**Unmapped:** 0
**Duplicates:** 0

| Category | Reqs | Phase(s) |
|----------|------|----------|
| AUTH | 9 | Phase 2 |
| WAL | 9 | Phases 1 (WAL-05), 3 (WAL-01,03,04,06,07,08,09), 5 (WAL-02) |
| MKT | 8 | Phases 4 (MKT-07,08), 6 (MKT-01,02,05,06), 9 (MKT-03,04) |
| BET | 7 | Phase 5 |
| STL | 7 | Phases 5 (STL-02..07), 7 (STL-01) |
| ADU | 6 | Phases 5 (ADU-03), 8 (ADU-01,02,04,05,06) |
| ADM | 7 | Phases 4 (ADM-01..04, ADM-07), 5 (ADM-05), 7 (ADM-06) |
| ADD | 6 | Phases 8 (ADD-04), 10 (ADD-01,02,03,05,06) |
| PLT | 10 | Phases 1 (PLT-01,02,03,04,06,08,10), 3 (PLT-05,09), 11 (PLT-07) |

---
*Roadmap created: 2026-05-25 by gsd-roadmapper. Mode: Vertical MVP. Granularity: fine.*
