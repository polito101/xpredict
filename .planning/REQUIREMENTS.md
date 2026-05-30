# Requirements: XPredict

**Defined:** 2026-05-25
**Core Value:** El operador puede ofrecer un catálogo creíble de mercados de predicción (mezcla de Polymarket y house) con liquidación correcta y CRM para gestionar usuarios, todo bajo su marca — sin construir ni operar la pieza técnica.

**Defaults applied to research's 10 open questions:**
1. Email provider — deferred to Phase 2 planning (not a v1 requirement decision)
2. House markets — binary-only (YES/NO) in v1; multi-outcome in v2
3. Bet limits — configurable per market via operator settings; global default in v1
4. Email verification gate — browse allowed without verify; betting blocked until verified
5. Banned user balance — frozen (visible, immutable); no silent zeroing
6. Polymarket source badge — yes, "Synced from Polymarket" with link to source
7. Resolution justification — public to players (primary trust signal)
8. Admin role — boolean `is_admin` flag in v1; full RBAC in v2 if needed
9. Leaderboard — deferred to v2; not demoable without months of bet history
10. Regulatory review — process gate before any operator demo; not a code requirement

## v1 Requirements

All requirements satisfy the "production-grade architecture, play-money UX" mandate.

### Authentication & Identity (AUTH)

- [x] **AUTH-01**: Player can register with email + password (Argon2id hashed, server-side validation, password strength enforced)
- [x] **AUTH-02**: Player receives email verification message after signup (Mailpit in dev; real SMTP in staging — provider decided Phase 2 planning)
- [x] **AUTH-03**: Player can verify email by clicking single-use, time-limited link
- [x] **AUTH-04**: Player can log in with email + password; session persists across browser refresh
- [x] **AUTH-05**: Player can log out from any page (server-side session/token revoked)
- [x] **AUTH-06**: Player can reset password via email link (single-use token; password_reset bumps token_version invalidating prior sessions)
- [x] **AUTH-07**: Admin uses separate login route and `is_admin` flag; admin auth surface is distinct from player auth surface
- [x] **AUTH-08**: All auth endpoints (register, login, password reset, email verify) are rate-limited per IP and per email via slowapi + Redis
- [x] **AUTH-09**: Refresh token rotation with reuse detection; HTTP-only Secure cookies for player session, Bearer JWT for admin API access

### Wallet & Double-Entry Ledger (WAL)

- [x] **WAL-01**: Each player has one wallet account (currency `PLAY_USD`) created automatically on registration
- [ ] **WAL-02**: Player receives configurable sign-up bonus credited automatically after email verification (default 1000 PLAY_USD; operator-configurable via TenantConfig)
- [x] **WAL-03**: Player can view current wallet balance on any page (cached in session header)
- [x] **WAL-04**: Player can view full transaction history (deposits, bets, settlements, adjustments) with timestamps and reasons
- [x] **WAL-05**: All money columns use `NUMERIC(18,4)`; all Python money values use `Decimal` constructed from strings — never float, never Postgres MONEY (Phase 1 ships: Money alias + AST lint + 17 lint tests + CI workflow step; full schema enforcement when Phase 3 ships money columns)
- [x] **WAL-06**: All wallet mutations are recorded in append-only double-entry ledger (accounts + transfers + entries tables); balance column on accounts is a denormalized cache reconciled nightly
- [x] **WAL-07**: All wallet writes use `SELECT ... FOR UPDATE` inside a single transaction with `idempotency_key UNIQUE`; race conditions and double-spend blocked at DB level
- [x] **WAL-08**: `CHECK (balance >= 0)` constraint on every wallet account; negative balance impossible
- [x] **WAL-09**: Tokens are strictly non-transferable between users at DB schema level; no UI path and no API endpoint exists for player-to-player transfers (regulatory firewall)

### Markets — Browsing & Sync (MKT)

- [ ] **MKT-01**: Player sees market list on home page: top-25 active Polymarket-mirrored markets + all open house markets, sorted by 24h volume
- [ ] **MKT-02**: Each market card displays question, current YES/NO odds, deadline, total volume, and source badge ("Synced from Polymarket" with link to source, or "House market")
- [x] **MKT-03**: Player can open market detail page with question, resolution criteria, price history chart, order entry form, and recent activity feed
- [x] **MKT-04**: Market prices update in real time via WebSocket (mirrored prices update on each poll; house market prices update when admin edits)
- [ ] **MKT-05**: System polls Polymarket Gamma API every 30 seconds for top-25 active markets via Celery Beat; deduped with Redis distributed lock to prevent overlapping runs
- [ ] **MKT-06**: System snapshots odds for all open markets every 5 minutes for price history chart
- [ ] **MKT-07**: Mirrored markets are stored with Polymarket `condition_id` + `market_id` for reverse lookup at resolution time
- [ ] **MKT-08**: v1 supports binary outcomes only (YES/NO); multi-outcome markets explicitly deferred to v2

### Bets (BET)

- [ ] **BET-01**: Authenticated, email-verified player with positive balance can place a bet on any open market by selecting outcome (YES or NO) and stake
- [ ] **BET-02**: Unverified-email player can browse all markets but cannot place bets (clear UI message + 403 on API)
- [ ] **BET-03**: Bet placement is a single ACID transaction: lock wallet row → check balance → insert bet → insert ledger entries (debit wallet, credit market liability) → update balance cache → commit
- [ ] **BET-04**: Player sees bet confirmation modal with stake, current odds, expected payout, and explicit confirm step before bet is created
- [ ] **BET-05**: Player cannot sell a position before resolution (no cash-out in v1; locked at API level)
- [ ] **BET-06**: Configurable bet limits per market — global minimum and maximum stake (operator-set via TenantConfig); UI rejects below/above the range
- [ ] **BET-07**: Player can view portfolio with open positions (stake, current odds, unrealized P&L) and settled positions (stake, outcome, realized P&L)

### Settlement & Resolution (STL)

- [ ] **STL-01**: When a Polymarket market reaches confirmed-resolved status (not just `closed`) PLUS internal grace period (UMA dispute window safety margin), system auto-settles the mirrored market via SettlementService
- [ ] **STL-02**: Admin can manually resolve a house market by selecting winning outcome with mandatory justification text and a two-step confirm flow
- [ ] **STL-03**: Settlement is idempotent: re-running settlement on a settled market is a no-op (`WHERE settled_at IS NULL` guard + `(bet_id, event_type)` UNIQUE on ledger entries)
- [ ] **STL-04**: Settlement credits winners' wallets and debits market liability in a single ACID transaction (no split commits, no orphan ledger entries)
- [ ] **STL-05**: Settlement writes audit log entry with: market_id, source, resolver (admin_user_id or `polymarket-uma`), winning_outcome, total_payout, settlement_timestamp
- [ ] **STL-06**: Player sees resolution display on each settled market: winning outcome, resolution source ("Polymarket UMA" or "Operator: {admin_display_name}"), justification text (public), settlement timestamp, their own payout/loss
- [ ] **STL-07**: Admin can reverse a settlement via compensating ledger entries (never DELETE/UPDATE); reversal requires justification and writes audit log entry

### Admin — User CRM (ADU)

- [x] **ADU-01**: Admin can view paginated list of all users with search (email, display name) and filters (status, signup date, last activity)
- [x] **ADU-02**: Admin can open user detail page showing profile, wallet balance, full transaction history, all bets, ban status
- [ ] **ADU-03**: Admin can manually recharge a user's wallet with stake amount and mandatory reason text; recharge is audit-logged
- [x] **ADU-04**: Admin can ban a user (state machine: active → banned); banned user cannot log in or bet; balance is frozen (visible, immutable), never zeroed
- [x] **ADU-05**: Admin can unban a user; previously frozen balance is restored as-is
- [x] **ADU-06**: Admin can export users / transactions / bets to CSV from admin UI (not exposed to players)

### Admin — Markets (ADM)

- [ ] **ADM-01**: Admin can view paginated list of all markets across sources with filters (source, status, category)
- [ ] **ADM-02**: Admin can create a house market with question, resolution criteria text, deadline, initial odds (default 50/50), and optional category
- [ ] **ADM-03**: Admin can edit a house market's odds, deadline, and resolution criteria while it has zero bets
- [ ] **ADM-04**: Admin can close a house market early (stops accepting new bets) before resolving it
- [ ] **ADM-05**: Admin can resolve a house market manually (see STL-02)
- [ ] **ADM-06**: Admin can force-settle a stuck Polymarket-mirrored market via two-step confirm with mandatory justification (emergency override; audit-logged)
- [ ] **ADM-07**: After first bet is placed on a house market, resolution criteria are locked (UI disabled + API rejects) to prevent rule-changes mid-game

### Admin — Dashboard & Branding (ADD)

- [ ] **ADD-01**: Admin landing page after login is the KPI dashboard, not the user list
- [ ] **ADD-02**: KPI dashboard shows: 24h volume, daily active users, total active markets, pending resolutions count, house P&L (today + cumulative)
- [ ] **ADD-03**: KPI dashboard uses Recharts for volume-over-time visualization, with daily granularity for first 30 days
- [x] **ADD-04**: Admin can view audit log: chronological, filterable by event_type and actor, immutable (read-only UI; underlying table has UPDATE/DELETE trigger block)
- [ ] **ADD-05**: Admin can configure instance branding: brand name, logo image, primary/secondary palette colors — stored in single-row TenantConfig
- [ ] **ADD-06**: Player-facing UI reads branding config at runtime; changes apply on next page navigation (no rebuild required)

### Platform — Cross-cutting (PLT)

- [x] **PLT-01**: All tenant-scoped tables include nullable `tenant_id UUID` column with default constant for v1 (multi-tenant migration prep — flipping to NOT NULL + RLS is mechanical in v2)
- [x] **PLT-02**: All money mutations and admin actions go through the audit log: `actor_user_id`, `event_type`, `payload`, `timestamp`, `ip` — append-only enforced by Postgres trigger
- [x] **PLT-03**: All secrets via Pydantic BaseSettings reading from environment (`.env.local` in dev, Railway env in staging); never hardcoded
- [x] **PLT-04**: `gitleaks` runs in CI to block accidental secret commits
- [x] **PLT-05**: Stripe stub interface present: disabled "Add funds" button in player UI + `WalletService.recharge(payment_provider="stripe")` method signature ready for v2 wiring without refactor
- [x] **PLT-06**: Feature flags table exists with prep for per-tenant config in v2 (single-row default for v1)
- [ ] **PLT-07**: Player-facing UI is fully responsive on mobile browsers (≥360px width); admin UI desktop-only acceptable
- [x] **PLT-08**: Sentry receives errors from FastAPI + Celery + Next.js; alert rules wired for: settlement failures, Polymarket sync error-rate spikes, ledger reconciliation drift, auth abuse spikes (code complete; Sentry event round-trip is a manual-verify item for /gsd-verify-work — needs real SENTRY_DSN; alert rules deferred to Phase 11 polish)
- [x] **PLT-09**: Nightly Celery task reconciles materialized wallet balances against ledger entries; any drift logs CRITICAL and alerts
- [x] **PLT-10**: `docker-compose up` brings up the full stack locally (api, worker, beat, db, redis, frontend, mailpit) with one command (code complete; runtime acceptance is a manual-verify item for /gsd-verify-work — gated by host port conflicts)

## v2 / Deferred Requirements

Acknowledged but not in v1 scope. Tracked here so they're not "forgotten" later.

### Leaderboard & Social (LBD)

- **LBD-01**: Player can view leaderboard ranked by all-time P&L (no monetary prizes — glory only, to stay outside gambling definition)
- **LBD-02**: Player can view leaderboard of top-volume bettors over rolling 30 days
- **LBD-03**: Player can view another player's public profile (display name, badges, P&L)

### Multi-tenancy Runtime (MTN)

- **MTN-01**: System routes by subdomain (e.g., `operator-a.xpredict.com`) to set `tenant_id` at session level
- **MTN-02**: Postgres Row-Level Security enforces `tenant_id` isolation at DB level (defense in depth)
- **MTN-03**: Operator can self-serve their own branding, market catalog, user base, and KPI dashboard
- **MTN-04**: Operator billing / metering / quota enforcement

### Markets v2 (MKT2)

- **MKT2-01**: Multi-outcome markets (3+ outcomes) supported in schema and UI
- **MKT2-02**: Player can search markets by keyword + filter by category
- **MKT2-03**: Player can watchlist markets and receive in-app notification on resolution
- **MKT2-04**: Full Polymarket catalog (paginated, searchable) instead of top-25 only

### Real Money (RM)

- **RM-01**: Player can deposit via Stripe (PLT-05 stub wired up)
- **RM-02**: Player can request withdrawal with KYC checks
- **RM-03**: Operator has compliance dashboard (AML flags, large-bet alerts)
- **RM-04**: Operator can configure jurisdiction-specific limits / blocks

### Live-bets Integration (LB)

- **LB-01**: `LiveBetsAdapter` implements `MarketSource` Protocol against live-bets v3 API
- **LB-02**: Player browses live-bets markets alongside Polymarket and house markets

## Out of Scope

Explicitly excluded. Documented to prevent scope creep and to inform sales conversations.

| Feature | Reason |
|---------|--------|
| Order book / limit orders | 5–10x complexity; play money does not warrant it |
| Cash-out (sell position before resolution) | Requires AMM or bid/ask spread; explicit PROJECT.md exclusion |
| Real money / fiat / crypto in v1 | Licensing (Spain DGOJ), KYC, AML — months of legal; validate sales first (PLT-05 keeps door open) |
| Native mobile apps (iOS/Android) | Extra codebases + app store reviews; responsive web sufficient for demo |
| Full Polymarket catalog (10k+ markets) | Triggers UX overhead (search, filters, pagination) without sales value |
| User-created markets | Moderation + abuse vectors; off-message for B2B2C operator-curated model |
| Token purchase with fiat | Adds consideration → Spain Ley 13/2011 gambling definition risk |
| Token transfers between users | Secondary market → consideration → gambling regulation; hard-blocked at DB level (WAL-09) |
| Leaderboard with monetary prizes | Prize element → gambling definition; glory-only LBD-01 sufficient for v2 |
| Real-time dispute resolution (UMA replica) | On-chain + complex; admin manual override is the v1 path |
| Comment threads on markets | Moderation cost; not what sells XPredict to operators |
| Push notifications | Service workers + FCM/APNS; in-app + email sufficient |
| Drip marketing email | GDPR scope + email reputation work; out of scope for sales demo |
| Web3 sign-in / wallet connect | Out of scope while v1 is play-money only |
| Comments / chat / DMs | Moderation + abuse vectors; not core to the B2B2C sale |

## Traceability

Populated by gsd-roadmapper on 2026-05-25 (ROADMAP.md creation).

| Requirement | Phase | Status |
|-------------|-------|--------|
| AUTH-01 | Phase 2 | Complete |
| AUTH-02 | Phase 2 | Complete |
| AUTH-03 | Phase 2 | Complete |
| AUTH-04 | Phase 2 | Complete |
| AUTH-05 | Phase 2 | Complete |
| AUTH-06 | Phase 2 | Complete |
| AUTH-07 | Phase 2 | Complete |
| AUTH-08 | Phase 2 | Complete |
| AUTH-09 | Phase 2 | Complete |
| WAL-01 | Phase 3 | Complete |
| WAL-02 | Phase 5 | Pending |
| WAL-03 | Phase 3 | Complete |
| WAL-04 | Phase 3 | Complete |
| WAL-05 | Phase 1 | Done (01-01: Money alias + AST lint + 17 lint tests; 01-04: CI workflow money-lint step; full schema enforcement when Phase 3 ships money columns) |
| WAL-06 | Phase 3 | Complete |
| WAL-07 | Phase 3 | Complete |
| WAL-08 | Phase 3 | Complete |
| WAL-09 | Phase 3 | Complete |
| MKT-01 | Phase 6 | Pending |
| MKT-02 | Phase 6 | Pending |
| MKT-03 | Phase 9 | Complete |
| MKT-04 | Phase 9 | Complete |
| MKT-05 | Phase 6 | Pending |
| MKT-06 | Phase 6 | Pending |
| MKT-07 | Phase 4 | Pending |
| MKT-08 | Phase 4 | Pending |
| BET-01 | Phase 5 | Pending |
| BET-02 | Phase 5 | Pending |
| BET-03 | Phase 5 | Pending |
| BET-04 | Phase 5 | Pending |
| BET-05 | Phase 5 | Pending |
| BET-06 | Phase 5 | Pending |
| BET-07 | Phase 5 | Pending |
| STL-01 | Phase 7 | Pending |
| STL-02 | Phase 5 | Pending |
| STL-03 | Phase 5 | Pending |
| STL-04 | Phase 5 | Pending |
| STL-05 | Phase 5 | Pending |
| STL-06 | Phase 5 | Pending |
| STL-07 | Phase 5 | Pending |
| ADU-01 | Phase 8 | Complete |
| ADU-02 | Phase 8 | Complete |
| ADU-03 | Phase 5 | Pending |
| ADU-04 | Phase 8 | Complete |
| ADU-05 | Phase 8 | Complete |
| ADU-06 | Phase 8 | Complete |
| ADM-01 | Phase 4 | Pending |
| ADM-02 | Phase 4 | Pending |
| ADM-03 | Phase 4 | Pending |
| ADM-04 | Phase 4 | Pending |
| ADM-05 | Phase 5 | Pending |
| ADM-06 | Phase 7 | Pending |
| ADM-07 | Phase 4 | Pending |
| ADD-01 | Phase 10 | Pending |
| ADD-02 | Phase 10 | Pending |
| ADD-03 | Phase 10 | Pending |
| ADD-04 | Phase 8 | Complete |
| ADD-05 | Phase 10 | Pending |
| ADD-06 | Phase 10 | Pending |
| PLT-01 | Phase 1 | Done (01-03: audit_log + feature_flags both ship tenant_id UUID DEFAULT '00000000-0000-0000-0000-000000000001'; integration test test_tenant_id_default green) |
| PLT-02 | Phase 1 | Done (01-03: audit_log immutability trigger + REVOKE UPDATE, DELETE FROM PUBLIC; integration tests test_audit_log_update_blocked + test_audit_log_delete_blocked green; AuditService.record atomic with caller's session) |
| PLT-03 | Phase 1 | Done (01-01: Settings(BaseSettings) + scrub_secrets + structlog SCRUB_KEYS; 01-03: .env.example committed + .env.local gitignored; 01-04: gitleaks CI gate live) |
| PLT-04 | Phase 1 | Done (01-04: .gitleaks.toml + 2 custom rules + synthetic-secret negative test + pre-commit + 3 CI workflows; test_gitleaks_blocks_secret.py 2/2 green; clean repo scan 0 findings) |
| PLT-05 | Phase 3 | Complete |
| PLT-06 | Phase 1 | Done (01-03: feature_flags composite PK (key, tenant_id) + 3 seeded rows + FeatureFlagService.is_enabled with tenant fallback; 5 integration tests green) |
| PLT-07 | Phase 11 | Pending |
| PLT-08 | Phase 1 | Done with manual-verify pending (01-01: init_sentry + FastAPI + Celery worker/beat + tags + triple-trigger backend; 01-02: Next.js surface; 01-04: HTTP wiring verified, alert rules deferred to Phase 11; **manual-verify**: Sentry event round-trip needs real SENTRY_DSN — 10-min checklist in 01-04-SUMMARY.md) |
| PLT-09 | Phase 3 | Complete |
| PLT-10 | Phase 1 | Done with manual-verify pending (01-03: docker-compose.yml 8 services + healthchecks valid; 01-04: bin/dev + bin/dev.ps1 + Makefile + README shipped; **manual-verify**: `bin\dev.ps1` runtime acceptance gated by host port conflicts with crypto-casino — 5-min checklist in 01-03-SUMMARY.md) |

**Coverage:**
- v1 requirements: 69 total
- Mapped to phases: 69 (100%)
- Unmapped: 0
- Duplicates: 0

**Per-phase requirement counts:**

| Phase | Count | Requirements |
|-------|-------|--------------|
| 1 — Project Scaffold, Infra & Cross-Cutting Foundations | 8 | PLT-01, PLT-02, PLT-03, PLT-04, PLT-06, PLT-08, PLT-10, WAL-05 |
| 2 — Auth & Identity | 9 | AUTH-01..09 |
| 3 — Wallet & Double-Entry Ledger | 9 | WAL-01, WAL-03, WAL-04, WAL-06, WAL-07, WAL-08, WAL-09, PLT-05, PLT-09 |
| 4 — Markets Domain & HouseAdapter | 7 | MKT-07, MKT-08, ADM-01, ADM-02, ADM-03, ADM-04, ADM-07 |
| 5 — Bets, Settlement & First End-to-End Demo (House Markets Only) | 16 | BET-01..07, STL-02..07, ADM-05, WAL-02, ADU-03 |
| 6 — Polymarket Sync | 4 | MKT-01, MKT-02, MKT-05, MKT-06 |
| 7 — Polymarket Auto-Resolution & Admin Override | 2 | STL-01, ADM-06 |
| 8 — Admin CRM (User Management & Audit Log Viewer) | 6 | ADU-01, ADU-02, ADU-04, ADU-05, ADU-06, ADD-04 |
| 9 — User App UX Polish (Market Detail & Real-Time) | 2 | MKT-03, MKT-04 |
| 10 — Admin KPI Dashboard & Configurable Branding | 5 | ADD-01, ADD-02, ADD-03, ADD-05, ADD-06 |
| 11 — Hardening & Operator-Demo Gate | 1 | PLT-07 |
| **Total** | **69** | |

---
*Requirements defined: 2026-05-25*
*Traceability populated: 2026-05-25 by gsd-roadmapper (11 phases, fine granularity, Vertical MVP mode)*
*Last updated: 2026-05-26 — Phase 1 closeout (01-04 acceptance gate auto-approved per --auto mode; PLT-01..04+06+08+10 + WAL-05 marked Done; PLT-08 + PLT-10 retain manual-verify items for /gsd-verify-work)*
