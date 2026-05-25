# Architecture Research — XPredict

**Domain:** White-label play-money prediction market platform (Polymarket-mirrored + house markets)
**Researched:** 2026-05-25
**Confidence:** HIGH for stack/patterns (verified against official docs); MEDIUM for Polymarket-specific behavior (verified against Gamma API docs but no live integration test yet)

---

## 1. Executive Recommendation

**Build a modular monolith on a single FastAPI process + Celery workers, single Postgres 16, single Redis.**

Two developers do not need microservices. The cost of operating a distributed system (network failures, distributed transactions, deployment complexity, observability) dwarfs the benefit at this scale. What you DO need is **strict module boundaries inside the monolith** so that:

1. A future split into services is mechanical, not architectural
2. Multi-tenancy refactor in v2 touches one layer (data access), not every module
3. The MarketSource abstraction lets you add live-bets later without rewriting the bet/settlement engine

The monolith ships as **two Python processes deployed from the same codebase**:

- `api` — FastAPI, handles HTTP from user app + admin panel
- `worker` — Celery workers consuming from Redis (Polymarket poller, resolution detector, settlement)
- `beat` — Celery Beat scheduler (single instance, schedules periodic jobs)

Frontend is a separate Next.js 15 process. End-user app and admin panel can share one Next.js project with route segregation (`/app` vs `/admin`) — no separate deployment needed in v1.

---

## 2. System Overview

```
┌────────────────────────────────────────────────────────────────────┐
│                          CLIENT LAYER                              │
│  ┌──────────────────────┐         ┌──────────────────────────┐     │
│  │  Next.js 15 (User)   │         │  Next.js 15 (Admin/CRM)  │     │
│  │  /markets, /bet, /me │         │  /admin/users, /markets  │     │
│  └──────────┬───────────┘         └────────────┬─────────────┘     │
│             │                                  │                   │
└─────────────┼──────────────────────────────────┼───────────────────┘
              │ HTTPS (REST + JWT)               │
              ▼                                  ▼
┌────────────────────────────────────────────────────────────────────┐
│                       API LAYER (FastAPI)                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │  auth    │ │ markets  │ │   bets   │ │  wallet  │ │  admin   │ │
│  │  router  │ │  router  │ │  router  │ │  router  │ │  router  │ │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ │
│       │            │            │            │            │       │
├───────┴────────────┴────────────┴────────────┴────────────┴───────┤
│                      SERVICE LAYER                                 │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌────────────┐│
│  │ AuthService  │ │MarketService │ │  BetService  │ │WalletService││
│  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └──────┬─────┘│
│         │                │                │                │      │
│  ┌──────┴────────────────┴────────────────┴────────────────┴────┐ │
│  │       SettlementService (used by both bet & resolution)      │ │
│  └──────────────────────────────────────────────────────────────┘ │
├────────────────────────────────────────────────────────────────────┤
│                   REPOSITORY LAYER (SQLAlchemy)                    │
│   UserRepo · WalletRepo · LedgerRepo · MarketRepo · BetRepo · ...  │
├────────────────────────────────────────────────────────────────────┤
│                    MARKET SOURCE ADAPTERS                          │
│  ┌──────────────────────┐  ┌──────────────────────┐                │
│  │ PolymarketAdapter    │  │ HouseAdapter         │                │
│  │ (Gamma API HTTP)     │  │ (DB-native)          │                │
│  └──────────────────────┘  └──────────────────────┘                │
│        ▲ implements          ▲ implements                          │
│        └────── MarketSource (Protocol/ABC) ──────┘                 │
├────────────────────────────────────────────────────────────────────┤
│                       WORKER LAYER (Celery)                        │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐   │
│  │ poll_polymarket  │ │detect_resolutions│ │ settle_market    │   │
│  │ (Beat: every 30s)│ │ (Beat: every 60s)│ │ (triggered)      │   │
│  └──────────────────┘ └──────────────────┘ └──────────────────┘   │
├────────────────────────────────────────────────────────────────────┤
│                      INFRASTRUCTURE LAYER                          │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐ │
│  │  Postgres 16     │  │     Redis 7      │  │ Polymarket Gamma │ │
│  │  (data + ledger) │  │ (broker + cache) │  │  (external HTTP) │ │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘ │
└────────────────────────────────────────────────────────────────────┘
```

**Reading the diagram:**
- Routers do HTTP shape (request validation, status codes, auth check via dependency).
- Services do business logic and orchestrate transactions.
- Repositories do raw DB access (one repo per aggregate).
- Adapters implement the `MarketSource` interface — they are the ONLY place that knows about Polymarket's HTTP shape.
- Celery workers call the same Services as routers (via a small bootstrap script). No separate "background logic" duplicating service code.

---

## 3. Module Decomposition

The monolith is split into bounded contexts. Each context owns its tables, services, repos, and routers. **Inter-module communication goes through service interfaces, never direct repo access.**

### Module map

| Module | Owns | Tables |
|--------|------|--------|
| **auth** | User identity, sessions, password hashing, role check | `users`, `password_reset_tokens`, `admin_users` (or admin flag on users) |
| **wallet** | Balances, double-entry ledger, transaction log, recharges | `wallets`, `wallet_accounts`, `ledger_entries` |
| **markets** | Market catalog, sources, outcomes, sync state, polling cursor | `markets`, `outcomes`, `market_sources`, `market_sync_log`, `odds_snapshots` |
| **bets** | Bet placement, bet lifecycle (pending/active/settled/voided), bet log | `bets`, `bet_settlements` |
| **settlement** | Resolution logic, payout computation, ledger posting orchestration | (none — orchestrates across wallet + bets + markets) |
| **admin** | Admin actions (recharge user, ban, create/resolve house market, view CRM) | `admin_actions` (audit table) |
| **branding** | Tenant config, logo, palette (single row in v1, prepares multi-tenant in v2) | `tenant_config` |
| **integrations** | External adapter implementations (PolymarketAdapter, future LiveBetsAdapter) | (stateless — uses markets tables via service) |

### Inter-module rules

1. **Routers can only call services in their own module** OR services exposed via a public `__init__.py`. No reaching into another module's repositories.
2. **`SettlementService` is the only cross-module orchestrator.** It calls `BetService`, `WalletService`, and `MarketService` to settle. This is acceptable because settlement is inherently cross-cutting.
3. **Adapters never touch the DB directly.** They return DTOs (pydantic models). Persistence happens in `MarketSyncService`.
4. **Celery tasks live in `app/tasks/`** but contain almost no logic — they call services.

### Project structure (recommended)

```
backend/
├── app/
│   ├── main.py                    # FastAPI app, mounts routers
│   ├── celery_app.py              # Celery instance + Beat schedule
│   ├── config.py                  # Pydantic Settings, env vars
│   ├── db/
│   │   ├── base.py                # SQLAlchemy Base, declarative
│   │   ├── session.py             # async session factory
│   │   └── migrations/            # Alembic
│   ├── core/
│   │   ├── security.py            # Argon2 hashing, JWT encode/decode
│   │   ├── dependencies.py        # FastAPI deps (current_user, admin_only)
│   │   ├── exceptions.py          # custom errors → HTTP mapping
│   │   └── logging.py             # structured logging setup
│   ├── modules/
│   │   ├── auth/
│   │   │   ├── models.py          # SQLAlchemy
│   │   │   ├── schemas.py         # Pydantic
│   │   │   ├── repository.py
│   │   │   ├── service.py
│   │   │   └── router.py
│   │   ├── wallet/
│   │   │   ├── models.py          # Wallet, LedgerEntry
│   │   │   ├── schemas.py
│   │   │   ├── repository.py
│   │   │   ├── service.py         # credit/debit primitives + atomic transfer
│   │   │   ├── ledger.py          # double-entry helpers
│   │   │   └── router.py          # GET /me/wallet, GET /me/transactions
│   │   ├── markets/
│   │   │   ├── models.py          # Market, Outcome, MarketSource enum
│   │   │   ├── schemas.py
│   │   │   ├── repository.py
│   │   │   ├── service.py         # MarketService, MarketSyncService
│   │   │   └── router.py          # GET /markets, GET /markets/{id}
│   │   ├── bets/
│   │   │   ├── models.py          # Bet, BetStatus enum
│   │   │   ├── schemas.py
│   │   │   ├── repository.py
│   │   │   ├── service.py         # BetService (place, void, list)
│   │   │   └── router.py
│   │   ├── settlement/
│   │   │   ├── service.py         # SettlementService — cross-module
│   │   │   └── payout.py          # pure payout math
│   │   ├── admin/
│   │   │   ├── service.py         # AdminService — recharge, ban, resolve house mkt
│   │   │   └── router.py          # /admin/* endpoints
│   │   └── branding/
│   │       ├── models.py          # TenantConfig
│   │       └── service.py
│   ├── integrations/
│   │   ├── market_source.py       # MarketSource Protocol + DTO types
│   │   ├── polymarket/
│   │   │   ├── adapter.py         # PolymarketAdapter implements MarketSource
│   │   │   ├── client.py          # httpx wrapper, retries, rate-limit
│   │   │   └── mappers.py         # Gamma JSON → internal DTO
│   │   └── house/
│   │       └── adapter.py         # HouseAdapter implements MarketSource
│   └── tasks/
│       ├── polling.py             # poll_polymarket, detect_resolutions
│       └── settlement.py          # settle_market task
├── tests/
│   ├── unit/                      # service-level tests with fakes
│   ├── integration/               # DB + Redis with testcontainers
│   └── e2e/                       # HTTP tests via httpx + TestClient
├── alembic.ini
├── pyproject.toml
└── Dockerfile

frontend/
├── app/
│   ├── (public)/                  # public marketing + login pages
│   ├── (user)/                    # authenticated user app
│   │   ├── markets/
│   │   ├── me/
│   │   └── bet/
│   └── admin/                     # admin panel (role-gated)
│       ├── users/
│       ├── markets/
│       └── dashboard/
├── components/
├── lib/                           # API client, auth helpers
└── ...

docker-compose.yml                 # api + worker + beat + postgres + redis
```

**Why this structure:**
- One folder per bounded context = cognitively scoped changes
- `integrations/` is separate from `modules/` because adapters are infrastructure, not domain
- `tasks/` is thin — workers reuse services from `modules/`
- Frontend has two route groups under one Next.js app — simpler than two Vercel projects, role check via middleware

---

## 4. Domain Model

### Entity relationship sketch (textual ER)

```
User (1) ──── (1) Wallet ──── (1..N) WalletAccount
                  │
                  └─── (1..N) LedgerEntry (double-entry rows)

User (1) ──── (0..N) Bet
                  │
                  └─── (1) Market ──── (1..N) Outcome
                  │           │
                  │           └─── (1) MarketSource (enum: POLYMARKET, HOUSE)
                  │           └─── (1..N) OddsSnapshot
                  │
                  └─── (0..1) BetSettlement ──── (1..N) LedgerEntry [via tx_ref]

Market (1) ──── (0..1) Resolution ──── (1) Outcome (winning)

AdminUser (or User.is_admin) ──── (0..N) AdminAction (audit log)

TenantConfig (single row in v1, FK from many tables in v2)
```

### Core entities — primary attributes

#### User
- `id` (UUID, PK)
- `email` (unique, citext)
- `password_hash` (Argon2id)
- `created_at`, `updated_at`
- `is_active`, `is_admin`, `is_banned` (bool)
- `email_verified_at` (nullable)
- `tenant_id` (UUID, FK tenants, **nullable in v1, NOT NULL in v2**)

#### Wallet
- `id` (UUID, PK)
- `user_id` (UUID, FK users, unique — 1 wallet per user)
- `currency_code` (CHAR(3), default `'PMC'` for "Play Money Credits")
- `created_at`
- `tenant_id` (FK, nullable v1)

#### WalletAccount (the "account" in double-entry)
- `id` (UUID, PK)
- `wallet_id` (UUID, FK wallets)
- `account_type` (enum: `CASH`, `LOCKED_IN_BET`, `HOUSE_INCOME`, `HOUSE_EXPENSE`, `SUSPENSE`)
- `balance` (BIGINT, stored in minor units — cents — to avoid float)

> Rationale: a wallet is a "book" containing multiple accounts. Standard double-entry. `CASH` is what the user sees as balance. `LOCKED_IN_BET` holds funds while bets are pending. `HOUSE_INCOME`/`HOUSE_EXPENSE` are operator-side accounts for unbet/lost money.

#### LedgerEntry (the immutable journal)
- `id` (UUID, PK)
- `tx_ref` (UUID — same value across paired debit/credit rows in one transaction)
- `posted_at` (timestamp, immutable)
- `from_account_id` (FK wallet_accounts)
- `to_account_id` (FK wallet_accounts)
- `amount` (BIGINT, positive integer, minor units)
- `entry_type` (enum: `RECHARGE`, `BET_LOCK`, `BET_PAYOUT`, `BET_REFUND`, `BET_LOSS`, `ADJUSTMENT`)
- `reference_type` + `reference_id` (polymorphic — e.g., `BET`/`<bet_id>`)
- `metadata` (JSONB, free-form audit info)

> Critical invariant: ledger is **append-only**. No UPDATE, no DELETE, ever. Corrections happen via reversal entries.

#### Market
- `id` (UUID, PK)
- `source` (enum: `POLYMARKET`, `HOUSE`)
- `source_market_id` (TEXT, the external ID — Polymarket's `conditionId` or NULL for house)
- `slug` (TEXT, unique within tenant — used in URLs)
- `question` (TEXT)
- `description` (TEXT, nullable)
- `category` (TEXT, nullable — politics/sports/etc.)
- `status` (enum: `OPEN`, `CLOSED`, `RESOLVED`, `VOIDED`)
- `opens_at`, `closes_at` (timestamps — closes_at = no more bets accepted)
- `resolved_at` (timestamp, nullable)
- `created_at`, `updated_at`
- `created_by_admin_id` (FK, nullable — only for HOUSE markets)
- `tenant_id` (FK, nullable v1)

#### Outcome (binary or multi-outcome)
- `id` (UUID, PK)
- `market_id` (FK)
- `label` (TEXT — e.g., "Yes", "No", "Trump", "Harris")
- `current_odds` (NUMERIC(10,6) — implied probability 0..1, updated by sync job)
- `is_winning` (bool, nullable — set on resolution)
- `display_order` (int)

#### OddsSnapshot (historical odds)
- `id` (BIGSERIAL, PK)
- `outcome_id` (FK)
- `odds` (NUMERIC(10,6))
- `captured_at` (timestamp, indexed)

> Used for charts. Append-only. Can be aggressively pruned (>30 days = downsample).

#### Bet
- `id` (UUID, PK)
- `user_id` (FK)
- `market_id` (FK)
- `outcome_id` (FK — the outcome the user bet on)
- `stake` (BIGINT, minor units)
- `odds_at_placement` (NUMERIC(10,6) — locked at bet time)
- `potential_payout` (BIGINT — stake / odds_at_placement, locked at bet time)
- `status` (enum: `PENDING`, `SETTLED_WON`, `SETTLED_LOST`, `VOIDED`)
- `placed_at`, `settled_at`
- `lock_ledger_tx_ref` (UUID — points to the ledger entry that locked the stake)
- `tenant_id` (FK, nullable v1)

> Rationale: odds locked at placement — this is the simple "bet at current price" model, no orderbook. Out-of-scope explicitly excludes secondary trading.

#### BetSettlement
- `id` (UUID, PK)
- `bet_id` (FK)
- `result` (enum: `WON`, `LOST`, `VOID`)
- `payout_amount` (BIGINT, 0 for lost)
- `settled_at`
- `settlement_ledger_tx_ref` (UUID — ties to ledger entries)
- `resolved_by` (enum: `POLYMARKET_ORACLE`, `ADMIN_MANUAL`)
- `admin_user_id` (FK, nullable — only set for manual resolutions)

#### AdminAction (audit trail for admin operations)
- `id` (UUID, PK)
- `admin_user_id` (FK)
- `action` (TEXT — e.g., `RECHARGE_USER`, `BAN_USER`, `CREATE_MARKET`, `RESOLVE_MARKET`)
- `target_type`, `target_id` (polymorphic)
- `payload` (JSONB — full request body)
- `created_at`

#### TenantConfig (single row in v1)
- `id` (UUID, PK)
- `name` (TEXT)
- `logo_url`, `primary_color`, `secondary_color`
- `created_at`, `updated_at`

#### MarketSyncLog (operational — for poller observability)
- `id` (BIGSERIAL, PK)
- `source` (enum)
- `started_at`, `finished_at`
- `markets_seen`, `markets_created`, `markets_updated`, `resolutions_detected`
- `error` (TEXT, nullable)

---

## 5. Critical Data Flows

### Flow A — Polymarket sync (poller → market upsert → odds update)

```
[Celery Beat: every 30s]
      │
      ▼
poll_polymarket task
      │
      ▼
PolymarketAdapter.fetch_top_markets(limit=25)
      │  (httpx GET gamma-api.polymarket.com/markets?active=true&closed=false
      │   &order=volume24hr&ascending=false&limit=25)
      │
      ▼
[List of MarketDTO]
      │
      ▼
MarketSyncService.sync_markets(dtos, source=POLYMARKET)
      │
      ├─► For each DTO:
      │     │
      │     ├─► MarketRepo.upsert_by_source(source, source_market_id)
      │     │     (Postgres ON CONFLICT — atomic)
      │     │
      │     ├─► OutcomeRepo.upsert_by_market_and_label()
      │     │
      │     ├─► If odds changed: OddsSnapshotRepo.insert()
      │     │
      │     └─► If DTO.closed=true and our market.status=OPEN:
      │           → enqueue detect_resolution task (separate worker job)
      │
      ▼
MarketSyncLogRepo.insert(stats)
```

**Idempotency:** the entire job is safe to re-run. Upsert by `(source, source_market_id)` unique constraint. Same DTOs in → same DB state out.

### Flow B — Polymarket resolution → settlement → wallet credit

```
[Celery Beat: every 60s]
      │
      ▼
detect_resolutions task
      │
      ▼
PolymarketAdapter.fetch_market_resolution(source_market_id)
      │  (Uses umaResolutionStatus + outcomePrices: a resolved market has
      │   one outcome at price 1.0 and others at 0.0)
      │
      ▼
[ResolutionDTO with winning_outcome_label]
      │
      ▼
SettlementService.resolve_market(market_id, winning_outcome_id, source=ORACLE)
      │
      │  [SINGLE DB TRANSACTION begins]
      │
      ├─► MarketRepo.update_status(market_id, RESOLVED, winning_outcome_id)
      │
      ├─► For each Bet WHERE market_id=X AND status=PENDING:
      │     │
      │     ├─► If bet.outcome_id == winning_outcome_id:
      │     │     ├─► BetRepo.update_status(SETTLED_WON, payout_amount)
      │     │     ├─► WalletService.credit(
      │     │     │       user.wallet,
      │     │     │       amount=potential_payout,
      │     │     │       entry_type=BET_PAYOUT,
      │     │     │       reference=bet)
      │     │     │     → 2 ledger entries (HOUSE_EXPENSE → user CASH)
      │     │     └─► BetSettlementRepo.insert(WON, payout)
      │     │
      │     └─► Else (loser):
      │           ├─► BetRepo.update_status(SETTLED_LOST, 0)
      │           ├─► WalletService.realize_loss(
      │           │       user.wallet,
      │           │       amount=stake,
      │           │       reference=bet)
      │           │     → 2 ledger entries (user LOCKED_IN_BET → HOUSE_INCOME)
      │           └─► BetSettlementRepo.insert(LOST, 0)
      │
      │  [TRANSACTION commits — all-or-nothing]
      │
      ▼
AdminActionRepo.insert(if manual) / log if oracle
```

**Why one DB transaction:** payouts must be atomic across all bets on the market. Partial settlement is unacceptable.

**Idempotency:** `SettlementService.resolve_market` checks `market.status != RESOLVED` as guard. Re-running is a no-op.

### Flow C — User registration → wallet creation → admin recharge → bet → loss

```
[Frontend POST /auth/register]
      │
      ▼
AuthService.register(email, password)
      │
      ├─► User created (is_active=true, email_verified_at=NULL)
      ├─► Send verification email (Celery task — fire-and-forget)
      └─► [Same transaction] WalletService.create_wallet(user_id)
              ├─► Wallet row
              └─► WalletAccounts: CASH (balance=0), LOCKED_IN_BET (balance=0)
      │
      ▼
[user verifies email → email_verified_at set]
      │
      ▼
[Admin: POST /admin/users/{id}/recharge {amount: 100000}]
      │
      ▼
AdminService.recharge(admin_id, user_id, amount)
      │
      │  [TRANSACTION]
      │
      ├─► WalletService.credit(
      │       user.wallet,
      │       amount=100000,
      │       entry_type=RECHARGE,
      │       reference=admin_action)
      │     → ledger entries (TENANT_FUND_SOURCE → user CASH)
      │     → updates wallet_accounts.balance via trigger or service
      │
      └─► AdminActionRepo.insert(RECHARGE_USER, payload)
      │
      ▼
[User: POST /bets {market_id, outcome_id, stake: 5000}]
      │
      ▼
BetService.place_bet(user_id, market_id, outcome_id, stake)
      │
      │  [TRANSACTION]
      │
      ├─► Validate: market.status == OPEN, outcome belongs to market,
      │            current_time < market.closes_at, stake > 0
      │
      ├─► Lock current_odds (SELECT outcome FOR SHARE — read committed is fine)
      │
      ├─► WalletService.lock_funds(
      │       user.wallet,
      │       amount=5000,
      │       reference=bet_id_about_to_be)
      │     → if insufficient CASH balance: raise InsufficientFunds
      │     → ledger entries (user CASH → user LOCKED_IN_BET)
      │     → wallet_accounts balances updated
      │
      └─► BetRepo.insert(
              status=PENDING,
              odds_at_placement=current_odds,
              potential_payout=stake / current_odds)
      │
      ▼
[... market resolves losing for user — Flow B runs ...]
      │
      ▼
At settlement (inside Flow B transaction):
      WalletService.realize_loss(wallet, amount=stake, reference=bet)
        → ledger entries (user LOCKED_IN_BET → HOUSE_INCOME)
        → user's LOCKED_IN_BET balance returns to 0
        → user's CASH balance is unchanged (was already debited at lock time)
```

**Key invariant:** at any time, `sum(user.wallet.accounts.balance) + sum(active bets stakes already moved)` is conserved. The ledger is the source of truth — balances are derived (and cached for performance).

### Flow D — House market creation → admin set odds → user bets → admin resolves

```
[Admin: POST /admin/markets { question, outcomes, opens_at, closes_at, initial_odds }]
      │
      ▼
AdminService.create_house_market(admin_id, payload)
      │
      ├─► MarketRepo.insert(source=HOUSE, status=OPEN, ...)
      ├─► OutcomeRepo.bulk_insert(outcomes with initial_odds)
      └─► AdminActionRepo.insert(CREATE_MARKET)
      │
      ▼
[Admin can edit odds: PATCH /admin/markets/{id}/odds]
      │
      ▼
AdminService.update_odds(admin_id, market_id, outcomes)
      │
      ├─► For each: OutcomeRepo.update(odds)
      ├─► OddsSnapshotRepo.insert (for charts)
      └─► AdminActionRepo.insert(UPDATE_ODDS)
      │
      ▼
[Users place bets — Flow C bet portion]
      │
      ▼
[Admin: POST /admin/markets/{id}/resolve { winning_outcome_id }]
      │
      ▼
AdminService.resolve_house_market(admin_id, market_id, outcome_id)
      │
      └─► SettlementService.resolve_market(
              market_id,
              winning_outcome_id,
              source=ADMIN_MANUAL,
              admin_user_id=admin_id)
            → same as Flow B from "[TRANSACTION begins]" onward
```

> **Insight:** Polymarket-sourced and house-sourced markets settle through the SAME `SettlementService`. The only difference is the trigger (oracle detection vs. admin click) and the `resolved_by` field on `BetSettlement`. This is the architectural payoff of the `MarketSource` abstraction.

---

## 6. MarketSource Abstraction (Plug-in Design)

This is the single most important architectural decision for future-proofing.

### The Protocol

```python
# app/integrations/market_source.py

from typing import Protocol, runtime_checkable
from datetime import datetime
from pydantic import BaseModel

class OutcomeDTO(BaseModel):
    label: str
    current_odds: float          # 0..1, implied probability
    is_winning: bool | None      # only set on resolution

class MarketDTO(BaseModel):
    source: str                  # "POLYMARKET", "HOUSE", "LIVE_BETS"
    source_market_id: str        # External ID
    question: str
    description: str | None
    category: str | None
    closes_at: datetime
    status: str                  # "OPEN" | "CLOSED" | "RESOLVED"
    outcomes: list[OutcomeDTO]
    raw: dict                    # Full upstream payload (for debugging)

class ResolutionDTO(BaseModel):
    source_market_id: str
    winning_outcome_label: str
    resolved_at: datetime
    voided: bool = False         # If the upstream voided the market

@runtime_checkable
class MarketSource(Protocol):
    """A source of prediction markets. Implementations are the ONLY
    place that knows about external API shapes."""

    source_id: str               # e.g., "POLYMARKET"

    async def fetch_active_markets(self, limit: int = 25) -> list[MarketDTO]:
        """Return currently active markets ordered by relevance."""
        ...

    async def fetch_market(self, source_market_id: str) -> MarketDTO | None:
        """Fetch a single market by its source ID."""
        ...

    async def detect_resolution(
        self, source_market_id: str
    ) -> ResolutionDTO | None:
        """Return resolution info if market has resolved, else None."""
        ...
```

### Concrete adapters

```python
# app/integrations/polymarket/adapter.py
class PolymarketAdapter:
    source_id = "POLYMARKET"

    def __init__(self, client: PolymarketClient):
        self.client = client

    async def fetch_active_markets(self, limit=25):
        raw = await self.client.get("/markets", params={
            "active": "true", "closed": "false",
            "order": "volume24hr", "ascending": "false",
            "limit": limit,
        })
        return [map_polymarket_to_dto(m) for m in raw]

    async def detect_resolution(self, source_market_id):
        raw = await self.client.get(f"/markets/{source_market_id}")
        if not raw["closed"]:
            return None
        # Polymarket signals resolution via outcomePrices: winner is 1.0
        prices = raw["outcomePrices"]  # JSON-encoded list
        outcomes = raw["outcomes"]
        winner_idx = next((i for i, p in enumerate(prices) if float(p) >= 0.99), None)
        if winner_idx is None:
            return None
        return ResolutionDTO(
            source_market_id=source_market_id,
            winning_outcome_label=outcomes[winner_idx],
            resolved_at=parse_datetime(raw["closedTime"]),
        )

# app/integrations/house/adapter.py
class HouseAdapter:
    source_id = "HOUSE"

    def __init__(self, market_repo: MarketRepository):
        self.repo = market_repo

    async def fetch_active_markets(self, limit=25):
        markets = await self.repo.list_house_markets(status="OPEN", limit=limit)
        return [market_to_dto(m) for m in markets]

    async def detect_resolution(self, source_market_id):
        # House markets resolve via admin action, not detection.
        return None
```

### Registry + dependency injection

```python
# app/integrations/registry.py
def get_market_source(source_id: str) -> MarketSource:
    return {
        "POLYMARKET": PolymarketAdapter(client=get_polymarket_client()),
        "HOUSE": HouseAdapter(market_repo=get_market_repo()),
    }[source_id]

# Adding LIVE_BETS later = one new file + one dict entry. Zero changes to BetService,
# SettlementService, or any router. THIS is plug-and-play.
```

### Why a Protocol, not an ABC?

- Protocol = structural typing, no inheritance required. Mocks in tests are easier.
- `@runtime_checkable` lets you do `isinstance(adapter, MarketSource)` in dev for assertions.
- Different sources can be implemented by very different classes without forcing a common base.

---

## 7. Multi-Tenancy Seams (Single-Tenant Now, Multi-Tenant Ready in v2)

The principle: **add `tenant_id` columns NOW (nullable, default a fixed UUID), build the access layer to filter by it from day one. In v2, you flip the column to NOT NULL and add row-level security; no app code changes.**

### What to do in v1 (single-tenant)

1. **Every tenant-scoped table has a `tenant_id UUID` column**, nullable, defaulting to a fixed constant (e.g., `'00000000-0000-0000-0000-000000000001'`) or NULL.
2. **Repositories accept `tenant_id` in their interface** but you can pass a default in v1.
   ```python
   class UserRepository:
       async def get_by_email(self, email: str, tenant_id: UUID = DEFAULT_TENANT) -> User | None:
   ```
3. **`branding` module already exists** with `TenantConfig` model (single row in v1).
4. **Auth middleware sets `request.state.tenant_id`** (constant in v1, resolved from subdomain/header in v2).
5. **A session-level Postgres setting** (`SET LOCAL app.tenant_id`) is set on every request — preparation for v2 row-level security.

### Which tables get `tenant_id`

| Table | Has tenant_id? |
|-------|----------------|
| users | YES |
| wallets, wallet_accounts | YES |
| ledger_entries | YES |
| markets | YES (even Polymarket-sourced — a tenant can choose which to display) |
| outcomes | inherited via market |
| bets | YES |
| bet_settlements | inherited via bet |
| admin_actions | YES |
| tenant_config | tenant_id IS the PK |
| odds_snapshots | inherited via outcome (no column — denormalize on read) |
| market_sync_log | NO (operational, system-wide) |

### Migration path to v2 (multi-tenant)

When the first operator signs:

1. **Create `tenants` table.** Migrate the constant tenant_id row in.
2. **Alter `tenant_id` columns to NOT NULL** (data already populated).
3. **Add subdomain/header → tenant_id resolution** in auth middleware (Next.js middleware reads host header, backend receives `X-Tenant-Slug`).
4. **Add Postgres Row-Level Security policies** on tenant-scoped tables: `USING (tenant_id = current_setting('app.tenant_id')::uuid)`.
5. **Backend sets `SET LOCAL app.tenant_id = ?` per request** — this was already wired in v1, just becomes load-bearing.
6. **Polymarket sync runs once globally** (markets table can store markets without tenant_id, OR each tenant has its own market rows — pick based on customization needs).

**Confidence: HIGH.** This is a well-trodden pattern documented by Microsoft Azure, Bytebase, Clerk, and Modern Treasury. The discriminator-column approach with Postgres RLS as the safety net is the industry standard.

### Trap to avoid

> **Do not use `BIGSERIAL` for any tenant-scoped table's PK.** Use `UUID`. With BIGSERIAL, IDs are globally sequential and could leak tenant volume info, plus they collide across tenant copies in any cross-tenant export. UUID v4 (or UUIDv7 for sorted indexing) is the standard.

---

## 8. Background Jobs (Celery)

### What runs and when

| Job | Schedule | Type | Frequency rationale |
|-----|----------|------|---------------------|
| `poll_polymarket_markets` | Celery Beat | Periodic | Every **30s** — Polymarket rate-limits at ~60 req/min, and odds shift meaningfully on 30s timescale. With 25 markets fetched in one `/markets` call (paginated), this is 2 req/min. Plenty of headroom. |
| `detect_polymarket_resolutions` | Celery Beat | Periodic | Every **60s** — resolutions are not time-critical (UMA has 2h dispute window anyway). Lower frequency lowers API load. |
| `snapshot_odds` | Celery Beat | Periodic | Every **5min** — for historical charts. More granular than this is overkill for the v1 demo. |
| `send_email` | ad-hoc | Triggered | Verification, password reset. Fired by auth service. |
| `settle_market` | ad-hoc | Triggered | Called by `detect_resolutions` when a resolution is detected. Separated to keep transaction scope small per task. |
| `cleanup_expired_tokens` | Celery Beat | Periodic | Daily — password reset tokens, dead sessions. |

### Beat schedule (sketch)

```python
# app/celery_app.py
celery_app.conf.beat_schedule = {
    "poll-polymarket": {
        "task": "app.tasks.polling.poll_polymarket_markets",
        "schedule": 30.0,
    },
    "detect-polymarket-resolutions": {
        "task": "app.tasks.polling.detect_polymarket_resolutions",
        "schedule": 60.0,
    },
    "snapshot-odds": {
        "task": "app.tasks.polling.snapshot_odds",
        "schedule": 300.0,
    },
    "cleanup-tokens": {
        "task": "app.tasks.maintenance.cleanup_expired_tokens",
        "schedule": crontab(hour=3, minute=0),
    },
}
```

### Idempotency contract for every task

Every Celery task must satisfy: **running it N times in a row with the same input produces the same final state.**

Patterns to enforce this:

1. **Distributed lock via Redis** for tasks that must not overlap (the poller):
   ```python
   @celery_app.task(bind=True)
   def poll_polymarket_markets(self):
       with redis_lock("lock:poll_polymarket", timeout=25):
           # if another instance holds the lock, this exits immediately
           run_poll()
   ```
2. **DB-level unique constraints** as the ultimate idempotency guard:
   ```sql
   CREATE UNIQUE INDEX uq_markets_source_ext_id
       ON markets (source, source_market_id);
   CREATE UNIQUE INDEX uq_bet_settlement_per_bet
       ON bet_settlements (bet_id);  -- a bet is settled at most once
   ```
3. **Status guards** on every settlement call:
   ```python
   if market.status == "RESOLVED":
       return  # already settled, no-op
   ```
4. **Stop on first error and let Celery retry** with exponential backoff:
   ```python
   @celery_app.task(bind=True, autoretry_for=(httpx.HTTPError,),
                    retry_backoff=True, max_retries=5)
   def poll_polymarket_markets(self):
       ...
   ```

### Why Celery (not RQ, not Arq)

- **Mature, battle-tested** (10+ years). Less worry.
- **Beat scheduler built in**, so no separate cron infrastructure.
- **Compatible with live-bets stack** (Pol's other project) — same Redis, same patterns, knowledge transfer.
- Trade-off: more config than RQ/Arq. Acceptable.

> Honest caveat: Celery on Windows is finicky for dev — workers should be run via Docker on Pol's machine, or under WSL. Production is Linux containers, no issue there.

### What NOT to put in Celery

- **HTTP request → response work.** Anything where the user is waiting. Use FastAPI `BackgroundTasks` for trivial fire-and-forget (e.g., write an audit log row), Celery only for true async work.
- **Authentication checks.** Those are middleware, not tasks.
- **Anything that needs response in <100ms.** Celery's overhead is 5-50ms per task.

---

## 9. Build Order — Phase Dependencies

The roadmap should have ~8-12 phases. Each phase maps to one architectural slice that is independently shippable and demoable.

**Recommended ordering with dependency rationale:**

| # | Phase | What it ships | Why this order |
|---|-------|---------------|----------------|
| 1 | **Project scaffold + infra** | Docker compose, Postgres, Redis, FastAPI hello-world, Next.js hello-world, Alembic, CI | Everything else needs this. Don't skip Docker. |
| 2 | **Auth + Users** | Registration, login, sessions/JWT, password hashing, email verification flow, role flags | Wallet is per-user. Bet is per-user. Auth must come first. |
| 3 | **Wallet + Ledger** | Wallet creation on user registration, double-entry ledger, balance derivation, admin recharge | Bets cannot exist without wallets. Build the ledger BEFORE building bets — refactoring bets later to retrofit double-entry is brutal. |
| 4 | **Markets domain + House Adapter** | Market & Outcome models, OPEN/CLOSED/RESOLVED state machine, admin creates a house market, lists markets via the HouseAdapter implementation of MarketSource. **No Polymarket yet.** | House markets prove the domain shape WITHOUT external dependencies. Polymarket is a complication on top, not the foundation. The MarketSource abstraction is designed before the second source exists. |
| 5 | **Bets + Settlement** | Place bet on a house market, lock funds, admin resolves, settlement runs, ledger updated, P&L visible | End-to-end happy path works on house markets only. This is a usable demo by itself. |
| 6 | **Polymarket Adapter + Sync** | PolymarketClient (httpx, rate-limiting, retries), PolymarketAdapter, MarketSyncService, Celery Beat schedule, top-25 sync every 30s | The MarketSource interface from phase 4 is now exercised by a second implementation. Sync only — no resolution yet. |
| 7 | **Polymarket Resolution Detection** | Detect resolved Polymarket markets, trigger SettlementService (same code as house). Audit log of detections. | Reuses phase 5 settlement code. Proves the abstraction worked. |
| 8 | **Admin Panel (CRM)** | Admin Next.js routes: list users, search, ban/unban, recharge form, view user activity (bets, ledger), market list with create/edit/resolve | UI on top of services already built. Most of the backend exists. |
| 9 | **User App polish** | Market list/detail pages, place bet form with odds preview, "my bets" page, "my wallet" with transaction history, basic dashboard | Same — UI consumers of existing APIs. |
| 10 | **Admin Dashboard + Metrics** | Total volume, active users, house P&L (sum HOUSE_INCOME − HOUSE_EXPENSE accounts), simple charts | Aggregate queries on the ledger. Last because the demo needs data to be interesting. |
| 11 | **Branding config** | TenantConfig CRUD, frontend reads logo/colors at runtime, theming via CSS variables | Easy to defer; necessary for the white-label pitch. |
| 12 | **Hardening + Observability** | Rate limiting, structured logs, error tracking (Sentry), audit log review UI, security review, perf baseline | Final polish before the demo. |

**Hard dependencies (cannot reorder):**
- 1 → 2 (need scaffold)
- 2 → 3 (need users for wallets)
- 3 → 5 (need ledger for settlement)
- 4 → 5 (need market domain for bets)
- 4 → 6 (need MarketSource interface for Polymarket adapter)
- 5 → 7 (need settlement service for resolution)
- 6 → 7 (need sync running to detect resolutions)

**Soft dependencies (can reorder if needed):**
- 8 can run partially in parallel with 9 if you have frontend bandwidth.
- 10 can be deferred to post-demo.
- 11 can land anywhere after 1, but it adds value when there's something to brand.

**The phase 4 trick.** This is the unintuitive one: build the HouseAdapter BEFORE the PolymarketAdapter, even though Polymarket is the headline feature. Reasons:
1. You have full control over house data, so you can test the domain shape without flaky external dependencies.
2. The MarketSource interface gets designed with TWO concrete implementations in mind from day one (you mentally check: "would HouseAdapter and PolymarketAdapter both fit this?")
3. End-to-end happy path (phase 5) is reachable without any external integration, which means you have a demo-able product at phase 5.

---

## 10. Architectural Patterns Used

### Pattern 1: Modular Monolith with Bounded Contexts

**What:** One deployable unit, but code organized into hard-walled modules (`modules/auth/`, `modules/wallet/`, ...) that communicate only via service interfaces.
**When to use:** Small team (1-5 devs), domain still evolving, no operational appetite for microservices.
**Trade-offs:** + simpler ops, faster iteration, full ACID across modules. − requires discipline (linter rules to forbid cross-module imports beyond service interfaces).

### Pattern 2: Repository Pattern + Service Layer (3-tier)

**What:** Routers → Services → Repositories → DB. Routers are dumb. Services hold logic. Repos hold queries.
**When to use:** Always, for any backend with non-trivial business logic.
**Trade-offs:** + testability, refactoring isolation. − some boilerplate per CRUD entity.

### Pattern 3: Double-Entry Ledger with Append-Only Journal

**What:** Money movements are journal entries (debit one account, credit another). Balances are derived. No UPDATE on the journal table.
**When to use:** Any system handling money/credits. Even play money — it's the same shape and you'll regret not having it the first time someone disputes a balance.
**Trade-offs:** + perfect audit trail, mathematical guarantees, zero "where did this $5 go?" debugging. − slightly more rows per transaction.

```python
# Example: lock funds for a bet
def lock_funds(wallet_id, amount, bet_id):
    tx_ref = uuid4()
    cash_account = repo.get_account(wallet_id, type=CASH)
    locked_account = repo.get_account(wallet_id, type=LOCKED_IN_BET)
    if cash_account.balance < amount:
        raise InsufficientFunds()
    # Two rows, same tx_ref, one transaction
    repo.insert_entry(tx_ref, from=cash_account.id, to=locked_account.id,
                      amount=amount, type=BET_LOCK, ref=("BET", bet_id))
    # Update materialized balances (or compute on read)
    repo.adjust_balance(cash_account.id, -amount)
    repo.adjust_balance(locked_account.id, +amount)
```

### Pattern 4: Adapter Pattern for External Sources

**What:** Define a domain-shaped interface (`MarketSource`) and put external API specifics in adapter classes that implement it.
**When to use:** Any time you depend on a third-party API or plan to support multiple providers.
**Trade-offs:** + swappable, testable (fake adapter for tests), domain code doesn't know API quirks. − one extra layer of mapping code.

### Pattern 5: Event-Sourcing-Lite Audit Trail

**What:** Append-only `admin_actions` and `ledger_entries` tables. Never UPDATE, never DELETE. The current state is derivable from the log, but you also keep materialized current state for speed.
**When to use:** Any system with audit/compliance/dispute requirements. Play-money platforms still need it if you ever want to convert to real money.
**Trade-offs:** + full forensic trail, time-travel debugging, regulatory readiness. − tables grow forever (acceptable; partition by month if needed).

### Pattern 6: CQRS-Lite (read vs. write paths)

**What:** Writes go through services and validate. Reads can be denormalized — e.g., wallet.cash_balance can be a cached materialized value updated by triggers/service code, instead of a SUM(ledger) every page load.
**When to use:** When read patterns differ from write patterns enough that joining at read-time is too slow.
**Trade-offs:** + faster reads. − slight risk of materialized state drifting from journal. Mitigate with periodic reconciliation jobs (`reconcile_balances` Celery task, daily).

---

## 11. Anti-Patterns to Avoid

### Anti-Pattern 1: Storing money as floats

**What people do:** `balance = 100.50` in a `NUMERIC` or worse `FLOAT` column.
**Why it's wrong:** Floating-point arithmetic is not associative. `(0.1 + 0.2) ≠ 0.3`. Multiplying odds × stake will drift. Sum-of-ledger ≠ balance.
**Do this instead:** Store money in minor units as `BIGINT` (cents, or your platform's smallest unit). Format for display at the edges only.

### Anti-Pattern 2: Single "balance" column on the wallet

**What people do:** `wallet.balance` updated by `UPDATE wallet SET balance = balance - 5000 WHERE id = ?` on every bet.
**Why it's wrong:** No audit trail. Race conditions between concurrent bets need explicit row locks. Reconciling "where did the money go" requires log archaeology.
**Do this instead:** Double-entry ledger. Balance derived from journal, optionally materialized for read speed.

### Anti-Pattern 3: Polymarket-specific fields on the Market table

**What people do:** Add `polymarket_condition_id`, `umaResolutionStatus`, etc. as columns on `markets`.
**Why it's wrong:** Couples the domain to one provider. When live-bets shows up, you either NULL-out half the columns or duplicate the table.
**Do this instead:** Generic `source` + `source_market_id` + optional `raw_payload` JSONB. Adapter parses raw payload into domain-shape DTOs.

### Anti-Pattern 4: Updating odds in-place without snapshotting

**What people do:** Poll Polymarket, `UPDATE outcomes SET odds = new_value`.
**Why it's wrong:** No history. Charts impossible. "Why did my bet pay this much?" becomes "lol, dunno."
**Do this instead:** Update `outcomes.current_odds` AND insert into `odds_snapshots`. Snapshots can be aggressively pruned later (downsample to 1/hour after 30 days), but you need them at the time the bet is placed.

### Anti-Pattern 5: Async resolution detection inside the HTTP request

**What people do:** When user opens a market page, fetch from Polymarket synchronously, check if resolved, settle.
**Why it's wrong:** Settlement is a write operation triggered by reads = data races + 30s page loads + duplicated settlement attempts.
**Do this instead:** Background job (Celery Beat) is the single source of truth for "has this resolved?". User requests are read-only.

### Anti-Pattern 6: One database per module ("DB-per-service in a monolith")

**What people do:** Try to be future-proof by splitting tables across separate Postgres schemas/instances.
**Why it's wrong:** Now you can't do cross-module transactions (settlement spans wallet + bets + markets). You re-invent distributed transactions inside one process. Worst of both worlds.
**Do this instead:** One Postgres. One database. Multiple schemas optional but not required. ACID inside the monolith is a feature, not a smell.

### Anti-Pattern 7: Skipping `tenant_id` "because it's single-tenant for now"

**What people do:** No tenant column in v1, "we'll add it in v2."
**Why it's wrong:** Backfilling tenant_id across millions of historical rows + every query in the codebase + every test is a rewrite, not a refactor.
**Do this instead:** Add nullable tenant_id with a default constant in v1. Cost: one extra column per table. Benefit: v2 is a migration script + middleware change, not a project.

### Anti-Pattern 8: Letting the Polymarket adapter touch the DB

**What people do:** `PolymarketAdapter.sync()` does `for market in fetched: db.session.merge(market)`.
**Why it's wrong:** Couples external-API concerns with persistence. Hard to test. Hard to swap.
**Do this instead:** Adapters return DTOs. `MarketSyncService` is the only thing that translates DTOs to DB writes.

---

## 12. Scaling Considerations

| Scale | What breaks first | Fix |
|-------|-------------------|-----|
| 0-100 users (demo) | Nothing. SQLite-on-Docker could handle it. | Just ship Postgres + Redis. |
| 100-10k users | (a) Settlement loop on big markets if 1000s of bets per market. (b) Polymarket polling redundancy. | (a) Settlement transaction can batch in chunks of N bets, or move per-bet payout to a fan-out of small Celery tasks. (b) Cache Polymarket responses in Redis with short TTL. |
| 10k-100k users | (a) Ledger table size for live reads. (b) Concurrent bet placement on hot markets (lock contention on wallet rows). | (a) Materialized balance columns + reconciliation job. (b) Wallet account row locks → SKIP LOCKED queuing, or sharded user-level Redis locks. |
| 100k+ users | DB write throughput on hot markets. | Real options at this scale: read replicas, partitioning ledger by month, considering a real ledger DB like TigerBeetle for the journal. |

**v1 focus:** all of the above is theoretical. For the demo, you'll have <100 concurrent users. Optimize for code clarity, not throughput.

**The first thing that will actually bite you in production-as-demo:** Polymarket API flakiness. Build retries + circuit breaker + last-known-good fallback into `PolymarketClient` from day one.

---

## 13. Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Polymarket Gamma API | HTTP (httpx), polled via Celery, adapter pattern | No auth required. Rate limit ~60 req/min. Cache responses 15-60s. Treat as unreliable — wrap every call in retry + timeout. |
| Email (SendGrid/Postmark/SMTP) | SMTP or HTTP via Celery task | Used only for verification + password reset in v1. Async/fire-and-forget. Failure must not block user registration. |
| (Future) Stripe | Webhook + REST | Out of scope v1. Schema is ready (wallet model maps cleanly). |
| (Future) live-bets | New `LiveBetsAdapter` implementing `MarketSource` | Plug-in via the existing abstraction. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Next.js ↔ FastAPI | REST + JWT in Authorization header | Same-origin via reverse proxy in prod, CORS in dev. |
| FastAPI ↔ Celery | Celery dispatches via Redis broker | Trigger jobs from services with `task.delay()`. Never `await` for a task result in HTTP path. |
| Celery worker ↔ Postgres | SQLAlchemy session per task (NOT shared with API) | Each task gets a fresh session. Always commit or rollback explicitly. |
| Services ↔ Repositories | Direct method call (in-process) | All inside the monolith. No network. |
| `SettlementService` ↔ other services | Direct in-process calls within one DB transaction | The acceptable cross-module orchestrator. |

---

## 14. Open Questions / Decisions Needed in Roadmap

1. **Email provider in v1?** SMTP via dev-friendly Mailhog locally, then Postmark or SendGrid in prod. Defer the decision until phase 2 — both are 1-hour swaps via the FastAPI-Users email backend.
2. **House markets binary-only or multi-outcome?** Polymarket has both. House market UX for multi-outcome is more work. Recommend binary-only in v1 to match the demo timeline, extend later. **Both are storable in the schema either way** — `outcomes` table is one-to-many.
3. **Concurrency model for bet placement on the same market.** If two users hit "bet on Yes" simultaneously and the odds shifted between the two requests, what guarantee do they get? Recommended: `odds_at_placement` is captured from the outcome row read inside the bet transaction. Users see the price at the moment their transaction ran. No optimistic locking on outcomes — bets don't change odds in v1 (we're mirroring Polymarket, not making a market).
4. **Should `users.is_admin` be a boolean flag or a separate `admin_users` table?** Boolean flag is simpler in v1, sufficient for one-or-two admin accounts. If you need granular roles later (read-only support staff, super-admin), add a `roles` table. Start with the boolean.
5. **What's the retention policy for ledger and odds snapshots?** Ledger: forever (it's the source of truth). Odds snapshots: keep raw for 30 days, then downsample. Out of scope for v1, but document.

---

## Sources

### Polymarket
- [Polymarket Gamma API Overview](https://docs.polymarket.com/developers/gamma-markets-api/overview)
- [Polymarket /markets endpoint reference](https://docs.polymarket.com/api-reference/markets/list-markets)
- [Polymarket API Architecture (Medium)](https://medium.com/@gwrx2005/the-polymarket-api-architecture-endpoints-and-use-cases-f1d88fa6c1bf)
- [Polymarket API Guide 2026 (Chainstack)](https://chainstack.com/polymarket-api-for-developers/)

### FastAPI architecture
- [FastAPI Project Structure: Production Guide 2026](https://www.zestminds.com/blog/fastapi-project-structure/)
- [FastAPI Repository Pattern and Service Layer](https://medium.com/@kacperwlodarczyk/fast-api-repository-pattern-and-service-layer-dad43354f07a)
- [Modular Monolith FastAPI starter](https://github.com/arctikant/fastapi-modular-monolith-starter-kit)
- [Domain-driven design with Python and FastAPI](https://www.actidoo.com/en/blog/python-fastapi-domain-driven-design)

### Double-entry ledger
- [How to Build a Real-Time Ledger System with Double-Entry Accounting (Finlego)](https://finlego.com/blog/designing-a-real-time-ledger-system-with-double-entry-logic)
- [Double-entry accounting for software engineers (Balanced)](https://www.balanced.software/double-entry-bookkeeping-for-programmers/)
- [How to Scale a Ledger, Part III (Modern Treasury)](https://www.moderntreasury.com/journal/how-to-scale-a-ledger-part-iii)
- [Double Entry Accounting DB Design (ardhitama.com)](https://ardhitama.com/notes/double-entry-accounting-db-design)

### Multi-tenancy
- [Multi-Tenant Database Architecture Patterns (Bytebase)](https://www.bytebase.com/blog/multi-tenant-database-architecture-patterns-explained/)
- [How to Design a Multi-Tenant SaaS Architecture (Clerk)](https://clerk.com/blog/how-to-design-multitenant-saas-architecture)
- [Row-Level Security for Multi-Tenant Data (OneUptime)](https://oneuptime.com/blog/post/2026-02-16-how-to-design-a-multi-tenant-data-isolation-strategy-on-azure-sql-database-using-row-level-security/view)
- [Data Isolation in Multi-Tenant SaaS (Redis)](https://redis.io/blog/data-isolation-multi-tenant-saas/)

### Celery
- [FastAPI + Celery Work Queues: Idempotent Tasks and Retries](https://medium.com/@hjparmar1944/fastapi-celery-work-queues-idempotent-tasks-and-retries-that-dont-duplicate-d05e820c904b)
- [Production-Ready Background Task Processing with Celery](https://python.elitedev.in/python/production-ready-background-task-processing-celery-redis-and-fastapi-integration-guide-2024-80ddc2f9/)
- [How to Use Redis with Celery Beat for Periodic Tasks](https://oneuptime.com/blog/post/2026-03-31-redis-celery-beat-periodic-tasks/view)
- [Advanced Celery for Django: Fixing Unreliable Background Tasks](https://www.vintasoftware.com/blog/guide-django-celery-tasks)

### Event sourcing / audit logs
- [Building Robust Systems With Immutable Event Logs (DZone)](https://dzone.com/articles/event-sourcing-explained-building-robust-systems)
- [Event Sourcing Pattern (Microsoft Azure)](https://learn.microsoft.com/en-us/azure/architecture/patterns/event-sourcing)

### Adapter pattern
- [Adapter Pattern in Python (Codesarray)](https://codesarray.com/view/Adapter-Pattern-in-Python)
- [Adapter Pattern – A Must for Vendor & Service Integrations (Bocoup)](https://www.bocoup.com/blog/adapter-pattern-a-must-for-vendor-service-integrations)

---

*Architecture research for: XPredict (white-label play-money prediction market platform)*
*Researched: 2026-05-25*
*Author: GSD project researcher (architecture dimension)*
