# Stack Research

**Domain:** White-label prediction market platform (Polymarket-replica catalog + house markets + play-money wallet, production-grade auth/audit)
**Researched:** 2026-05-25
**Confidence:** HIGH overall — versions verified against Context7, PyPI, and official docs as of mid-2026.

> **Greenfield scope reminder.** Backend (Python 3.12 + FastAPI + SQLAlchemy + Postgres 16 + Redis + Celery), Frontend (Next.js 15 + TS + Tailwind + shadcn/ui), Auth (FastAPI-users), Polymarket source (Gamma REST), and Deploy (Docker + Fly.io/Railway) are pre-decided. This document fills in **versions, complementary libraries, and the trickier subsystems**.

---

## 1. Backend — Core (Python 3.12)

### 1.1 Recommended versions

| Technology | Pinned version | Range to allow | Rationale | Confidence |
|------------|----------------|----------------|-----------|------------|
| Python | `3.12.x` (latest patch) | `>=3.12,<3.13` | 3.13 is stable but free-threaded GIL still experimental; some C-ext libs (Argon2, asyncpg) had minor friction. 3.12 is the long-term stable sweet spot. **Do NOT use 3.14** (Celery 5.6 only got initial support, no production track record yet). | HIGH |
| FastAPI | `0.115.x` (`>=0.115.7,<0.116.0`) | minor pin | 0.115 is the long-stable line all production tutorials/integrations target. Context7 lists 0.118/0.122/0.128 but they're shorter-lived and pull newer Starlette ranges. Pin the minor and bump deliberately — FastAPI is still 0.x so minor bumps can break. | HIGH |
| Uvicorn | `>=0.32,<0.36` | minor range | Standard ASGI server. Pair with `uvicorn[standard]` to get `uvloop` + `httptools`. | HIGH |
| Gunicorn | `>=23.0,<24.0` | minor pin | Process manager wrapping Uvicorn workers in prod (`-k uvicorn.workers.UvicornWorker`). Provides graceful reload, worker recycling. | HIGH |
| Pydantic | `>=2.10,<3.0` | major pin | v2 is current. v1 EOL. Settings split into `pydantic-settings`. | HIGH |
| pydantic-settings | `>=2.6,<3.0` | major pin | Provides `BaseSettings` (moved out of pydantic core in v2). Use `SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")`. Latest is 2.14.x. | HIGH |
| python-dotenv | `>=1.0,<2.0` | major pin | Required by pydantic-settings for `.env` loading. | HIGH |

```toml
# pyproject.toml — backend core
[project]
requires-python = ">=3.12,<3.13"
dependencies = [
  "fastapi[standard]>=0.115.7,<0.116.0",
  "uvicorn[standard]>=0.32,<0.36",
  "gunicorn>=23.0,<24.0",
  "pydantic>=2.10,<3.0",
  "pydantic-settings>=2.6,<3.0",
  "python-dotenv>=1.0,<2.0",
]
```

### 1.2 Database — SQLAlchemy 2.0 async + asyncpg + Alembic

| Library | Version | Purpose | Notes |
|---------|---------|---------|-------|
| SQLAlchemy | `>=2.0.43,<2.1` | ORM + Core | 2.0 is the modern async-first API (`AsyncSession`, `Mapped[]`, `mapped_column`). 2.1 is not yet released as stable. Latest 2.0.x as of Aug 2025 is 2.0.43. **Do NOT use 1.4-style queries** — use `select()` + `session.execute()` everywhere. |
| asyncpg | `>=0.30,<0.32` | Async Postgres driver | High-perf, used via `postgresql+asyncpg://`. Returns `Decimal` natively for `NUMERIC` — exactly what we want for the wallet. |
| psycopg2-binary | `>=2.9.10,<3.0` | Sync driver for Alembic | Alembic migrations run sync — keep psycopg2-binary alongside asyncpg. Or use psycopg3 (`>=3.2`) if you prefer one driver, but asyncpg is faster for app traffic. |
| Alembic | `>=1.14,<2.0` | Migrations | Standard. Configure `env.py` to use **sync engine** (psycopg2) even though app uses asyncpg — Alembic is synchronous by design. Autogenerate works but **always review diffs** before applying. |
| greenlet | `>=3.1` (transitive) | Required by SQLAlchemy async | Usually pulled in automatically. Pin if Docker build flakes. |

**PostgreSQL version: stay on 16.** PG 17 is the latest GA but ~17% of extensions still have integration issues per benchmarks. PG 16 has been GA over a year, the ecosystem is fully on board, and SQLAlchemy 2.0 has no known 16-specific bugs. Move to 17 in v2 once the extension ecosystem catches up.

**Money columns:** `Numeric(precision=18, scale=4)` for play-money balances/ledger entries. `asyncpg` returns these as `decimal.Decimal` natively. **Never use FLOAT/REAL for money.** **Never use Postgres `MONEY` type** (locale-dependent, returns strings).

```python
# example wallet column (see Wallet section below)
amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
```

### 1.3 Authentication — fastapi-users v14

| Library | Version | Purpose |
|---------|---------|---------|
| fastapi-users | `>=14.0.2,<15.0` | User registration, login, password reset, JWT/cookie auth |
| fastapi-users-db-sqlalchemy | `>=7.0,<8.0` | SQLAlchemy adapter for User model |
| pwdlib[argon2] | `>=0.2,<1.0` | Pulled in by fastapi-users; provides Argon2 hashing |

**Key facts (confidence: HIGH, verified via Context7 + fastapi-users releases):**
- v14.0.0 released **Nov 2024**, latest 14.0.2 (**Oct 2025**).
- **Argon2 is the default in v14** (was bcrypt in v13). Backward-compat: old bcrypt hashes still verify and auto-upgrade on next successful login.
- Project is now in **maintenance mode** — no new features, only security/dep updates. This is **fine for us**: the API is stable, security patches keep coming, and we don't need new features.
- Uses `pwdlib` (not the old `passlib`). `passlib` is effectively unmaintained — **do not pull it in directly**.

**Auth backend choice for XPredict:**
- **JWT via Bearer for the SPA-style admin** (`/admin/*` from Next.js) — stateless, easy to add API tokens later.
- **HTTP-only cookie session for the public-facing user app** — better security against XSS, plays well with Next.js Server Components (`cookies()` is async in 15+).
- Add **both backends** to one `AuthenticationBackend` list; fastapi-users supports multi-backend natively.

```python
# pseudo-snippet
bearer_transport = BearerTransport(tokenUrl="auth/jwt/login")
cookie_transport = CookieTransport(cookie_max_age=3600*24*7, cookie_secure=True, cookie_httponly=True, cookie_samesite="lax")

def get_jwt_strategy() -> JWTStrategy[UUID, UUID]:
    return JWTStrategy(secret=settings.JWT_SECRET, lifetime_seconds=3600)

jwt_backend = AuthenticationBackend(name="jwt", transport=bearer_transport, get_strategy=get_jwt_strategy)
cookie_backend = AuthenticationBackend(name="cookie", transport=cookie_transport, get_strategy=get_jwt_strategy)
```

**RS256 over HS256 for JWT** if you anticipate any service-to-service trust (e.g., future live-bets integration verifying tokens without sharing the secret). Same secret/algorithm pattern as in the Context7 docs above.

### 1.4 Background tasks & scheduling — Celery 5.5 + Beat (NOT APScheduler, NOT ARQ for this project)

| Library | Version | Purpose |
|---------|---------|---------|
| celery | `>=5.5,<5.6` | Distributed task queue. **Pin to 5.5, not 5.6** — 5.6 dropped Python 3.8 (fine), added 3.14 support (we don't need), and is too fresh for production (Mar 2026 release). |
| redis (python client) | `>=5.0,<6.0` | Required broker + result backend driver |
| celery-redbeat | `>=2.2,<3.0` | **Recommended Beat scheduler** instead of default file-based PersistentScheduler. Stores schedules in Redis — survives Beat container restarts, supports multiple Beat instances (HA), and admin UI can mutate schedules at runtime. |
| flower | `>=2.0,<3.0` | Read-only monitoring UI for Celery (worker health, task throughput, failures). Mount behind admin auth in staging/prod. |

**Why Celery (not APScheduler, not ARQ) for THIS project:**

| Need | Verdict |
|------|---------|
| Polymarket polling every N seconds (15–60s) for top-25 markets | Celery Beat scheduled task → publishes to a queue → worker fetches Gamma API + upserts DB. Survives FastAPI process restarts (decoupled). |
| Market resolution scheduler (fire at `endDate` to attempt settlement) | Either ETA-task per market (`apply_async(eta=...)`) **or** Beat task every 1m that scans for `endDate < now AND status='live'` (simpler, more robust to clock skew/restarts — recommend this). |
| Wallet settlement after market resolves | Synchronous DB transaction triggered from settlement task (NOT a long-running task — should complete in <1s). |
| Email delivery (verification, password reset) | Celery task with retry policy. |
| Future scaling: live-bets integration, webhooks, etc. | Celery scales horizontally with more workers; APScheduler doesn't. |

**ARQ** is a tempting modern async alternative (native asyncio, Redis-only, no Beat needed), but: (a) Pol's `live-bets` already uses Celery, so this keeps stacks identical → trivial future merge; (b) Celery's ecosystem (Flower, RedBeat, sentry integration, etc.) is more mature; (c) Beat's separation between scheduler and worker is cleaner for our "poll Polymarket + resolve markets + send emails" mix.

**APScheduler** is fine for a single-process app but breaks the moment you have >1 worker container (duplicate task fires). Skip.

```toml
celery>=5.5,<5.6
redis>=5.0,<6.0
celery-redbeat>=2.2,<3.0
flower>=2.0,<3.0
```

**Celery + asyncio gotcha (HIGH confidence):** As of 2026, Celery still has **no native async/await support** in task bodies. Workaround: write tasks as sync functions, use `asyncio.run(...)` inside them for the httpx call, or use a sync httpx client. **Do NOT** try to share the FastAPI async event loop with Celery workers.

### 1.5 HTTP client + retries (for Gamma API polling)

| Library | Version | Purpose |
|---------|---------|---------|
| httpx | `>=0.28,<0.29` | Modern async HTTP client. Pulled in by fastapi[standard]. Use one shared `AsyncClient` per app (created in lifespan), not a new client per request. |
| tenacity | `>=9.0,<10.0` | Retry policies (exponential backoff + jitter). Works with both sync and async. |

```python
# Gamma client retry decorator
from tenacity import retry, stop_after_attempt, wait_exponential_jitter, retry_if_exception_type
import httpx, asyncio

@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential_jitter(initial=1, max=30),
    retry=retry_if_exception_type((httpx.HTTPError, asyncio.TimeoutError)),
    reraise=True,
)
async def fetch_markets(client: httpx.AsyncClient, limit: int = 25) -> list[dict]:
    r = await client.get(
        "https://gamma-api.polymarket.com/markets",
        params={"active": "true", "closed": "false", "limit": limit, "order": "volume24hr", "ascending": "false"},
        timeout=10.0,
    )
    r.raise_for_status()
    return r.json()
```

### 1.6 Observability — structlog (NOT loguru)

| Library | Version | Purpose |
|---------|---------|---------|
| structlog | `>=24.4,<26.0` | Structured JSON logging. Best OpenTelemetry interop, threadsafe + asyncio-safe context propagation (`contextvars`-based), routes through stdlib logging so Uvicorn/Celery logs are unified. |
| sentry-sdk[fastapi,celery,sqlalchemy] | `>=2.18,<3.0` | Error reporting in staging/prod. Auto-instruments FastAPI request errors, Celery task failures, SQLAlchemy slow queries. Free tier is plenty for the demo. |
| opentelemetry-instrumentation-fastapi | `>=0.49b0` | Optional. Add when staging needs traces. Don't bother in v1 dev. |

**Skip loguru.** It's nicer for hobby scripts but: (a) no first-party OpenTelemetry integration (trace IDs won't propagate into log lines automatically), (b) replaces stdlib logging in a way that fights FastAPI/Uvicorn's internals. structlog is the production answer.

### 1.7 Security & hardening extras

| Library | Version | Purpose |
|---------|---------|---------|
| slowapi | `>=0.1.9,<0.2` | Rate limiting middleware for FastAPI. Use Redis storage so all FastAPI replicas share counters. Strict limits on `/auth/login`, `/auth/register`, `/auth/forgot-password`. |
| python-jose[cryptography] | (transitive of fastapi-users) | JWT signing. Already pulled in. |
| pyhumps | `>=3.8` | Optional. Convert snake_case ↔ camelCase if you want JSON responses to use camelCase for the JS frontend (or use Pydantic's `alias_generator=to_camel` directly — preferred). |

---

## 2. Backend — Polymarket Gamma API integration (custom client, NOT a third-party SDK)

### 2.1 Verdict: **roll a tiny custom client, do NOT depend on `polymarket-apis` for v1**

There are three third-party Python packages on PyPI: `polymarket-apis` (unified, Pydantic-validated), `polymarket-gamma` (gamma-only wrapper), and Polymarket's own `py-clob-client` (CLOB only, not Gamma).

Trade-off:

| Approach | Pros | Cons |
|----------|------|------|
| Custom 100-line httpx client | Full control, no surprise breakage, fits our Pydantic models exactly, easy to mock in tests, can pin Polymarket schema changes ourselves | Need to maintain it |
| `polymarket-apis` PyPI | One import for everything (gamma, clob, websockets, graphql) | Third-party, single maintainer, can drift behind Polymarket API changes, brings WAY more surface than we need (we only want gamma read-only), Pydantic models may not match our internal models exactly |

**Recommendation: custom client.** The Gamma API is small (≈5 endpoints we'll ever hit), public, and stable. Wrapping it ourselves with `httpx + tenacity + pydantic models` is ~150 lines and means we own every line of the audit-critical replication path. If `polymarket-apis` becomes the obvious community standard later, swap it in.

### 2.2 Gamma API spec (verified mid-2026)

**Base URL:** `https://gamma-api.polymarket.com` (HTTPS only; fully public — no API key/wallet).

**Endpoints we care about:**

| Endpoint | Method | Purpose | Key params |
|----------|--------|---------|------------|
| `/markets` | GET | List/filter markets | `limit`, `offset`, `active`, `closed`, `archived`, `enableOrderBook`, `order` (e.g. `volume24hr`), `ascending` |
| `/markets/{id}` | GET | Single market by ID | — |
| `/markets/slug/{slug}` | GET | Single market by slug | — |
| `/events` | GET | List/filter events (an event groups N markets) | `limit`, `offset`, `active`, `closed`, `slug` |
| `/events/{id}` | GET | Single event by ID | — |
| `/tags` | GET | Tag taxonomy | — |

**Rate limits (Cloudflare-enforced, queued not 429'd by default):**

| Endpoint | Limit |
|----------|-------|
| `/markets` | 300 req / 10s |
| `/events` | 500 req / 10s |
| `/markets` + `/events` listing combined | 900 req / 10s |
| `/tags` | 200 req / 10s |
| `/public-search` | 350 req / 10s |
| General (everything else) | 4,000 req / 10s |

We're polling top-25 every 30–60s → ~1 req per polling cycle. **Three orders of magnitude under the limit.** No concern.

**Market JSON schema (fields that matter to us, verified from samples + Polymarket/agents repo):**

```jsonc
{
  "id": "abc123",                     // primary key for us (string)
  "conditionId": "0x1234…",           // on-chain condition id
  "slug": "will-alice-win-election",  // stable URL slug
  "question": "Will Alice win the election?",
  "description": "…",
  "category": "Politics",
  "startDate": "2025-11-01T00:00:00Z",
  "endDate":   "2025-11-08T00:00:00Z",
  "active": true,
  "closed": false,
  "archived": false,
  "outcomes":      "[\"Yes\",\"No\"]",   // ⚠️ STRINGIFIED JSON — json.loads() it
  "outcomePrices": "[\"0.65\",\"0.35\"]",// ⚠️ STRINGIFIED JSON — json.loads() it
  "clobTokenIds":  "[\"0xtoken1\",\"0xtoken2\"]", // ⚠️ STRINGIFIED JSON
  "volume":     "150000.00",          // string, parse to Decimal
  "liquidity":  "50000.00",           // string, parse to Decimal
  "volume24hr": 12345.67,             // number (yes, inconsistent)
  "resolutionSource": "…",
  "umaResolutionStatus": "resolved" | "proposed" | "disputed" | null,
  "events": [ { …nested event object… } ],
  "tags":  [ { "id": "1", "label": "Politics" } ]
}
```

**Gotchas (HIGH confidence — these will bite the dev otherwise):**
1. **`outcomes`, `outcomePrices`, `clobTokenIds` are JSON strings, not arrays.** Always `json.loads()` them after parsing the response.
2. **Numeric strings** for `volume`/`liquidity` — parse to `Decimal`, never `float`.
3. **`active` + `closed` are independent booleans.** A market can be `active=true, closed=false` (currently live), `active=false, closed=false` (paused/archived), or `closed=true` (settled). Use `active=true AND closed=false` to filter "currently tradable".
4. **Resolution polling.** UMA resolution finalizes after a 2-hour challenge window. For house settlement triggered by Polymarket outcome, poll resolved markets every 5–15 minutes and only settle when `closed=true AND outcomePrices` shows a clean 0/1 distribution (e.g. `["1","0"]` = Yes won). Until then, treat as "pending oracle".
5. **No webhooks.** Polymarket offers WebSockets for CLOB (price changes) but **not** for Gamma resolutions. Polling is the only option for resolution detection.
6. **CORS:** the Gamma API responds with permissive CORS but we never call it from the browser. **Always proxy via our backend** so we control the schema we expose to Next.js.

### 2.3 Polling architecture (recommended pattern)

```
Celery Beat (RedBeat) ─┬─ every 30s ──→ task: poll_top25_markets
                        │                └─ httpx GET /markets?active=true&closed=false&order=volume24hr&limit=25
                        │                └─ upsert into our `polymarket_markets` table
                        │                └─ publish "market_updated" events for SSE/websocket fan-out (later)
                        │
                        └─ every 5m  ──→ task: poll_pending_resolutions
                                         └─ for each market in our DB with status='live' AND endDate < now:
                                            └─ GET /markets/{id}
                                            └─ if closed AND outcomePrices is decisive → trigger settle_market(market_id)
```

Use **Redis SET** (not the DB) to dedupe polling cycles if two workers somehow run the same task; or just trust RedBeat's single-Beat semantics. Cache `tag` data with a 1-hour TTL — it rarely changes.

---

## 3. Backend — Wallet & double-entry ledger (the hard part)

### 3.1 Verdict: **custom Postgres-native double-entry ledger** (do NOT use TigerBeetle, do NOT use pgledger as a hard dependency)

| Option | Verdict |
|--------|---------|
| **TigerBeetle** | Massive overkill for play-money demo (purpose-built for 1M+ tx/sec real-money systems with primary/replica + state machine replication). Adds a separate database to operate. **Skip.** |
| **pgledger** (Postgres extension/schema) | Interesting reference, but it's a separate install + you give up control of the schema (it owns its own tables). For a single-tenant demo this is more rope than rope. **Skip as dep, study as reference.** |
| **Custom schema** (`accounts`, `transfers`, `entries` tables) | Full control, fits XPredict's domain (user wallets, market liability accounts, house P&L), uses standard SQLAlchemy + Alembic, easy to audit/test, trivial to extend for multi-tenant in v2. **THIS.** |

Pol's "production-grade from day 1" principle is **exactly** the right call here — but production-grade means *correct ACID-bound double-entry in our own Postgres*, not adopting an exotic ledger database. The day Stripe is wired in, you don't rewrite the ledger; you just add a new account type (`fiat_pending`) and a new transfer kind.

### 3.2 Schema (Pol can adapt during phase planning)

```sql
-- accounts: every "place money can sit"
CREATE TABLE accounts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_type      TEXT NOT NULL,           -- 'user', 'market', 'house', 'system'
    owner_id        UUID,                     -- nullable for 'house'/'system' singletons
    kind            TEXT NOT NULL,           -- 'user_wallet', 'market_liability', 'house_revenue', 'house_promo'
    currency        TEXT NOT NULL DEFAULT 'PLAY_USD',
    balance         NUMERIC(18,4) NOT NULL DEFAULT 0,  -- denormalized cache; truth is in entries
    version         INT NOT NULL DEFAULT 0,            -- optimistic locking
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (owner_type, owner_id, kind, currency)
);

-- transfers: one row per business event (deposit, bet, payout, refund, admin adjustment)
CREATE TABLE transfers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kind            TEXT NOT NULL,           -- 'admin_topup', 'bet_placed', 'bet_settled_win', 'bet_settled_loss', 'refund'
    idempotency_key TEXT UNIQUE,             -- caller-supplied; prevents double-spends on retry
    actor_user_id   UUID,                     -- who triggered this (admin or user)
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    -- ⚠️ NO updated_at, NO deleted_at — transfers are IMMUTABLE
);

-- entries: the actual debit/credit lines (always at least 2 per transfer, must sum to 0)
CREATE TABLE entries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    transfer_id     UUID NOT NULL REFERENCES transfers(id),
    account_id      UUID NOT NULL REFERENCES accounts(id),
    direction       TEXT NOT NULL CHECK (direction IN ('debit','credit')),
    amount          NUMERIC(18,4) NOT NULL CHECK (amount > 0),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    -- ⚠️ NO update, NO delete — entries are IMMUTABLE
);

-- enforce immutability with REVOKE + a deny trigger
CREATE OR REPLACE FUNCTION deny_modification() RETURNS TRIGGER AS $$
BEGIN RAISE EXCEPTION 'transfers/entries are append-only'; END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER transfers_immutable BEFORE UPDATE OR DELETE ON transfers FOR EACH ROW EXECUTE FUNCTION deny_modification();
CREATE TRIGGER entries_immutable   BEFORE UPDATE OR DELETE ON entries   FOR EACH ROW EXECUTE FUNCTION deny_modification();

-- audit-trail invariant: every transfer's entries must net to zero (per currency)
-- enforce in app (within the SQLAlchemy transaction), AND add a deferrable constraint or post-insert trigger as belt-and-suspenders
```

**Key rules (any junior must internalize these):**
1. **One transaction per transfer.** Begin tx → insert `transfers` row → insert ≥2 `entries` rows → update `accounts.balance` rows (with version increment) → commit. If anything fails, the whole thing rolls back. `AsyncSession.begin()` handles this cleanly.
2. **Entries always net to zero.** A "place bet of 10 PLAY_USD" creates: `DEBIT user_wallet 10` + `CREDIT market_liability 10`. Settlement winner: `DEBIT market_liability 10` + `CREDIT user_wallet 25` *plus* `DEBIT house_revenue 0` (etc.) — every event balances.
3. **`balance` column on `accounts` is a denormalized cache.** Truth is `SUM(credits) - SUM(debits)` over `entries`. Reconcile periodically (nightly Celery task) and alert if drift.
4. **Idempotency.** Every transfer-creating API endpoint takes an `Idempotency-Key` header; we store it in `transfers.idempotency_key UNIQUE` and short-circuit on duplicate.
5. **Optimistic locking on `accounts`** to prevent two concurrent bets from over-spending the same wallet: `UPDATE accounts SET balance = balance - 10, version = version + 1 WHERE id = ? AND version = ?` — if 0 rows affected, raise and retry the whole transfer.
6. **Wallet API surface** is tiny: `get_balance(user)`, `place_bet(user, market, outcome, amount)`, `settle_market(market, winning_outcome)`, `admin_adjust(user, amount, reason)`. No "set balance" — only deltas via transfers.
7. **No floats. Ever.** `Decimal` everywhere in Python, `NUMERIC(18,4)` in Postgres. `asyncpg` makes this seamless.

### 3.3 Audit log (separate from ledger)

The ledger itself IS most of the audit. Add a separate `audit_log` table for **non-financial** sensitive actions:

```sql
CREATE TABLE audit_log (
    id            BIGSERIAL PRIMARY KEY,
    occurred_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actor_user_id UUID,
    actor_ip      INET,
    action        TEXT NOT NULL,    -- 'user.login', 'user.banned', 'market.house_created', 'market.house_resolved'
    target_type   TEXT,
    target_id     TEXT,
    payload       JSONB NOT NULL DEFAULT '{}',
    -- immutability via trigger, same pattern as transfers/entries
);
```

Write to it via a thin `audit.record(...)` helper called from every admin endpoint. **Do NOT** rely on SQLAlchemy event listeners alone (they can be bypassed accidentally). Keep it explicit at the call site.

### 3.4 Useful libraries (small surface)

| Library | Version | Purpose |
|---------|---------|---------|
| `python-ulid` or `uuid7` | latest | Time-sortable IDs for `transfers.id` if you want better index locality than v4 UUIDs. **Optional.** Default `gen_random_uuid()` is fine for the demo. |
| `dirty-equals` | `>=0.8` | Test-time helpers for asserting "amount equals 10 and timestamp roughly now" without flaky tests. Tiny but lovely. |

---

## 4. Frontend — Next.js 15 + React 19

### 4.1 Recommended versions

| Technology | Pinned version | Notes | Confidence |
|------------|----------------|-------|------------|
| Next.js | `15.x` (`>=15.1,<16.0`) | Stay on 15. Next 16 (already out) removes synchronous `cookies()`/`headers()`/`searchParams` access completely and tightens a few caching behaviours. Stay on 15 for v1, plan a focused upgrade phase later. | HIGH |
| React | `19.x` (`>=19.0,<20.0`) | Required by Next 15 App Router. **Match `react-is` to the same minor** — recharts needs this. | HIGH |
| TypeScript | `>=5.5,<5.8` | Modern enough for `satisfies`, `const` type parameters. 5.6+ has improved Next.js types. | HIGH |
| Tailwind CSS | `4.x` (`>=4.0,<5.0`) | v4 is the new default in shadcn/ui templates. v4 ditches `tailwind.config.js` in favor of CSS-first config (`@theme`). Different mental model than v3 — onboarding cost ~30min. | HIGH |
| shadcn/ui | CLI version `>=3.0` | shadcn/ui is "copy-paste components," not an npm dep. Run `npx shadcn@latest init` with the v4/React-19 template. Officially compatible with Next 15 + React 19. | HIGH |
| Radix UI primitives | latest (pulled in by shadcn) | Headless, accessibility-first. shadcn components are built on Radix; they're upgraded together. | HIGH |
| lucide-react | `>=0.460` | Icon library used by shadcn. | HIGH |

```json
// package.json (high-level pins; full deps via shadcn init)
{
  "dependencies": {
    "next": "^15.1.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "react-is": "^19.0.0"   // peer dep for recharts under React 19 — must match React minor
  },
  "devDependencies": {
    "typescript": "^5.6.0",
    "tailwindcss": "^4.0.0"
  }
}
```

### 4.2 Critical Next.js 15 gotchas (HIGH confidence)

1. **`cookies()`, `headers()`, `draftMode()`, `params`, `searchParams` are now async.** Every Server Component / Route Handler that reads them must `await`. Example:
   ```tsx
   // ❌ Next 14 style — deprecated in 15, removed in 16
   const cookieStore = cookies()
   // ✅ Next 15
   const cookieStore = await cookies()
   ```
   Codemod: `npx @next/codemod@canary next-async-request-api .`

2. **Fetch is no longer cached by default.** In Next 14 `fetch()` was opt-out-of-cache; in 15 it's opt-in via `{ cache: 'force-cache' }` or `{ next: { revalidate: N } }`. Audit every `fetch` for intent.

3. **GET Route Handlers no longer cached by default** either. Same fix: `export const dynamic = 'force-static'` if you want static behaviour.

4. **App Router + Pages Router mixing on different React versions is unsupported.** All-in on App Router. The Pages Router still works but use it only if you literally have no choice.

### 4.3 Data fetching & state management

| Concern | Recommendation | Why |
|---------|---------------|-----|
| Server-side data for SSR pages | Plain `async function Page()` Server Components with `fetch()` directly against our FastAPI backend. Cache via `{ next: { revalidate: 30 } }` for market lists. | Idiomatic Next 15. No client lib needed for read-only pages. |
| Client-side data + cache + revalidation (user dashboard, live odds, admin tables) | **TanStack Query v5** (`@tanstack/react-query` `>=5.85,<6.0`) | Industry standard. `useQuery`/`useMutation` with stale-while-revalidate, optimistic updates, infinite queries. Plays nicely with React 19. Pair with `@tanstack/react-query-devtools` (dev only). |
| Local UI state (modals, drawers, "is sidebar open") | **Zustand** (`zustand` `>=5.0,<6.0`) | Lighter than Redux, simpler than Jotai for our scale. Industry default for SaaS dashboards (per 2025 trend data). Not used for server state — that's TanStack Query's job. |
| Forms | **react-hook-form** (`>=7.55,<8.0`) + **zod** (`>=3.24,<4.0`) + **@hookform/resolvers** | Standard combo. shadcn/ui Form components are built on top of RHF. Pair the same `zod` schemas with our backend's Pydantic models (we already enforce server-side; client uses Zod for UX). |
| Charts (admin dashboard P&L, volume) | **Recharts** (`>=2.15,<3.0`) | shadcn's `<Chart>` component is a Recharts wrapper. **Recharts v2.15+** has React 19 marked compatible; pin `react-is` to match React 19. v3 is in beta — skip until stable. |
| Tables (CRM user list, market list) | **TanStack Table v8** (`@tanstack/react-table` `>=8.20,<9.0`) | Headless, you bring your own UI (shadcn has table primitives ready). Best perf for 1000+ row admin tables. Skip Material/Mantine wrappers — too heavy for this project. |
| Toasts / notifications | **sonner** (the one shadcn ships) | Default in current shadcn templates. |
| Date handling | **date-fns** (`>=4.0,<5.0`) | Tree-shakable, immutable. Skip moment.js (deprecated). dayjs is fine too but date-fns has better TS types. |

**Skip Redux, RTK, Recoil.** Overkill for this scope. Skip Jotai unless you discover later that you need atomic granular re-renders for a live-odds-firehose component (and even then, TanStack Query's subscription model usually handles it).

### 4.4 Polymarket data on the frontend

**Never call gamma-api.polymarket.com from the browser.** Always proxy via our FastAPI backend. Two reasons: (1) we control the schema we expose to Next (cleaner Pydantic-validated payloads, not Polymarket's stringified-JSON quirks), (2) we add internal market IDs to the response so Next never knows about Polymarket-specific IDs except as a hidden `source_id`.

---

## 5. Testing

### 5.1 Backend

| Library | Version | Purpose |
|---------|---------|---------|
| pytest | `>=8.3,<9.0` | Test runner. **Pin to 8.x for now** — pytest 9.0 just dropped (per Context7 listing) but ecosystem plugins (especially pytest-asyncio) still catching up. |
| pytest-asyncio | `>=0.24,<0.26` | Async test support. Use `asyncio_mode = "auto"` in pyproject. |
| httpx (already a dep) | — | `AsyncClient(transport=ASGITransport(app=app))` for in-process API tests. |
| pytest-httpx | `>=0.32,<0.36` | Mock outbound httpx calls — perfect for stubbing Gamma API responses in tests. |
| pytest-postgresql or testcontainers-python | `>=6.0` (testcontainers) | Real Postgres in tests (NOT sqlite). For the wallet/ledger you MUST test against Postgres — sqlite doesn't have `gen_random_uuid()`, triggers, deferrable constraints, NUMERIC, ROW-LEVEL locking semantics, etc. testcontainers spins up a disposable PG in Docker per session. |
| dirty-equals | `>=0.8` | Better assertions (`amount == IsApprox(10.0)`). |
| factory-boy | `>=3.3` (optional) | Test data factories. Optional but pleasant. |
| faker | `>=30` (pulled in by factory-boy) | Random realistic data. |

```ini
# pyproject.toml [tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

### 5.2 Frontend

| Library | Version | Purpose |
|---------|---------|---------|
| Vitest | `>=2.1,<3.0` | Modern Jest-compatible test runner. Faster than Jest, native ESM. **Recommended over Jest** for new Next.js projects. |
| @testing-library/react | `>=16.0,<17.0` | Component tests. v16+ required for React 19. |
| @testing-library/jest-dom | `>=6.5` | Matchers like `toBeInTheDocument()`. |
| @testing-library/user-event | `>=14.5` | Simulating user interactions. |
| Playwright | `>=1.48,<2.0` | End-to-end tests against a deployed/staging instance. Bet flows ↔ wallet ↔ settlement is exactly the e2e test you cannot skip. |
| msw | `>=2.6,<3.0` | Mock service worker for stubbing our own API in component tests. |

```bash
# scaffolding
npm i -D vitest @vitejs/plugin-react @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom @playwright/test msw
```

---

## 6. Dev tools & code quality

### 6.1 Backend

| Tool | Version | Purpose |
|------|---------|---------|
| Ruff | `>=0.7,<0.9` | Linter + formatter. Replaces flake8 + isort + black + many plugins. ~100x faster. Set `target-version = "py312"`. |
| mypy | `>=1.13,<2.0` | Static type checking. Strict on `app/`, lenient on `tests/`. |
| pre-commit | `>=4.0,<5.0` | Run ruff + mypy + secret-scan before each commit. |
| detect-secrets or trufflehog | latest | Block accidental commits of `.env` secrets, API keys. |

### 6.2 Frontend

| Tool | Version | Purpose |
|------|---------|---------|
| Biome | `>=1.9` | **Optional, recommended.** Replaces ESLint + Prettier with a single fast Rust binary. If team prefers familiar tools: ESLint 9 + Prettier 3.3. |
| typescript-eslint | `>=8.13` | Only if you choose ESLint over Biome. |
| Husky + lint-staged | latest | Pre-commit hooks. |

### 6.3 Containerization & local dev

| Tool | Version | Purpose |
|------|---------|---------|
| Docker | `>=25` | Dev + prod. |
| docker compose | v2 (built into Docker) | Local orchestration: `backend`, `worker` (celery), `beat`, `db` (postgres:16), `redis`, `frontend`. |
| Mailpit | `>=1.20` | Local SMTP catcher for auth emails in dev. Replaces MailHog (now unmaintained). |

```yaml
# docker-compose.yml (sketch)
services:
  db:        { image: postgres:16-alpine, … }
  redis:     { image: redis:7-alpine, … }
  backend:   { build: ./backend, command: uvicorn app.main:app --reload, … }
  worker:    { build: ./backend, command: celery -A app.celery worker -l info, … }
  beat:      { build: ./backend, command: celery -A app.celery beat -S redbeat.RedBeatScheduler -l info, … }
  flower:    { build: ./backend, command: celery -A app.celery flower, … }
  mailpit:   { image: axllent/mailpit, … }
  frontend:  { build: ./frontend, command: npm run dev, … }
```

---

## 7. Deployment — staging

### 7.1 Recommendation: **Railway for v1 staging, Fly.io as the "we'll graduate to this" option**

| Concern | Railway | Fly.io | Winner for XPredict |
|---------|---------|--------|---------------------|
| Time-to-deploy | <1 min, no Dockerfile needed (but supports them) | 5–10 min, Dockerfile-driven | Railway |
| Managed Postgres | First-class, managed plugin | Self-managed (`fly postgres`), no auto-failover, you handle backups | Railway |
| Managed Redis | First-class | Upstash Redis add-on (external) | Railway |
| Celery worker as separate service | One-click (separate service in the same project) | Separate machine config | Railway |
| Cost predictability | Flat $5/mo Hobby + usage | Per-machine per-region, harder to estimate | Railway |
| Global low-latency / multi-region | Single region | Native multi-region, edge | Fly.io (irrelevant for v1) |
| Private networking complexity | Project-scoped, simple | WireGuard mesh, powerful but more setup | Railway |

**Choose Railway for v1 staging.** It maps cleanly onto our `docker-compose.yml`: each `service:` becomes a Railway "service", Postgres and Redis are managed plugins. Total monthly cost for a demo: $5 base + ~$5–15 usage = **$10–20/mo**.

**Re-evaluate Fly.io when:**
- We need multi-region (none of our v1 users will care).
- We outgrow Railway's pricing (>$100/mo of usage).
- We need fine-grained machine control (irrelevant for demo).

### 7.2 Production-style local

```
docker compose up        # boots all 7 services
docker compose run backend alembic upgrade head
docker compose run backend pytest
```

Everything Railway runs in staging must work via `docker compose` locally. **No "works in staging only" features.**

---

## 8. Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Celery 5.5 + RedBeat | ARQ | Pure async stack with simpler ops, AND we don't need cross-project parity with live-bets. (For us: live-bets uses Celery; stick with it.) |
| Celery 5.5 + RedBeat | APScheduler | Single-process app with no horizontal scaling. (We will scale horizontally — skip.) |
| Custom Postgres ledger | TigerBeetle | We move to real money + need 100k+ tx/sec. v1: massive overkill. |
| Custom Postgres ledger | pgledger | We want a fully opinionated schema we don't own. Pol's "production-grade" stance argues for owning the schema. |
| Custom httpx Gamma client | `polymarket-apis` PyPI | We later need CLOB / WebSockets / GraphQL too. v1: only Gamma read-only — write our own. |
| structlog | loguru | Single-script project with no OpenTelemetry plans. v1 needs Sentry + traces → structlog. |
| TanStack Query | SWR | Smaller bundle, simpler API. We need mutations and devtools → TanStack Query wins. |
| Zustand | Jotai | Truly atomic state with heavy fine-grained subscriptions (e.g. 50-component live-odds grid). Not v1. |
| Recharts | Tremor | If we want a "batteries-included dashboard kit" (Tremor v3+). Worth re-evaluating for the admin dashboard phase — but lock-in to Tremor's design system fights shadcn. |
| Railway | Fly.io | Multi-region or strict cost/control needs. v1: Railway. |
| Postgres 16 | Postgres 17 | New project, extensions ecosystem matured (probably mid-2026 onward). Re-evaluate when prepping v2. |

---

## 9. What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| **`passlib`** | Effectively unmaintained, blocks modern Argon2 tuning. | `pwdlib[argon2]` (pulled in by fastapi-users v14). |
| **SQLAlchemy 1.4-style `query(Model).filter(...)`** | Deprecated API in 2.0; brittle async support. | `select(Model).where(...)` + `session.execute()`. |
| **SQLModel** for this project | Tempting (Pydantic + SQLA combined). But async story is messier than raw SQLA 2.0, and the wallet/ledger needs precise control over types and migrations. Adds churn. | Raw SQLAlchemy 2.0 `Mapped[]` + Pydantic schemas separately. (Use SQLModel if a single small project — not here.) |
| **`databases` (encode/databases)** | Effectively dead since SQLA 2.0 made async native. | SQLAlchemy 2.0 async. |
| **bcrypt 5.x direct usage** | Subtle truncation at 72 bytes, weaker than Argon2id. | Argon2id via pwdlib (default in fastapi-users v14). |
| **Postgres `MONEY` type** | Locale-dependent, returns strings, decimal-math problems. | `NUMERIC(18,4)` always. |
| **FLOAT/REAL for any monetary column** | Floating-point rounding errors compound silently — guaranteed audit failure. | `NUMERIC(18,4)` + Python `Decimal`. |
| **APScheduler in multi-worker prod** | Will fire duplicate tasks on every worker. | Celery Beat / RedBeat. |
| **loguru** for FastAPI prod | No first-party OpenTelemetry integration; replaces stdlib in surprising ways. | structlog (routed through stdlib). |
| **pages router in Next.js for new code** | Effectively legacy; React Server Components only work in App Router. | App Router everywhere. |
| **`useFormState`** (Next 15) | Renamed to `useActionState` in React 19. | `useActionState`. |
| **Recharts <2.15 on React 19** | Peer-dep warning, hydration glitches. | Recharts 2.15+ AND match `react-is` to React 19. |
| **`moment.js`** | Deprecated, large, mutable API. | `date-fns` (or `dayjs`). |
| **Material UI for the admin dashboard** | Big design system that fights Tailwind/shadcn. | shadcn primitives + Tailwind. |
| **Redux Toolkit** | Bigger than we need; we don't have multi-page Redux state. | Zustand + TanStack Query. |
| **Polling Gamma from the browser** | Exposes Polymarket schema quirks (stringified JSON), no rate-limit governance. | Proxy via FastAPI backend. |
| **Skipping `idempotency_key` on wallet endpoints** | Network retries WILL create double-spends. | Mandatory `Idempotency-Key` header on every POST that creates a transfer. |
| **Storing balances as the source of truth (no entries)** | Loses the audit trail; you can't answer "how did this user end up with $X?" | Entries are truth; balance is a denormalized cache reconciled nightly. |

---

## 10. Version Compatibility Matrix

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| FastAPI 0.115.x | Pydantic 2.10+, Starlette 0.40–0.46 | Pin FastAPI minor; don't let it drift. |
| fastapi-users 14.0.2 | FastAPI ≥0.103, Pydantic 2.x, SQLAlchemy 2.x async | Bcrypt hashes auto-upgrade to Argon2 on login. |
| SQLAlchemy 2.0.43 | Python 3.8+ (we use 3.12), asyncpg ≥0.27, psycopg2-binary ≥2.9, Alembic 1.x | Alembic env.py must run sync. |
| Celery 5.5.x | Python 3.9+ (we use 3.12), redis-py 5.x, kombu 5.4.x | Celery 5.6 bumps min Python to 3.9 (same constraint) but is too fresh. |
| Next.js 15.x | React 19.x, Node ≥18.18 (Next docs); use Node 20 LTS | React 18 is unsupported in App Router on 15. |
| Recharts 2.15.x | React 19 (peer-marked); requires `react-is` matching React minor | If using npm, may need `--legacy-peer-deps` once. pnpm/bun/yarn handle it. |
| TanStack Query 5.85+ | React 18 or 19 | First-class React 19 support. |
| shadcn/ui v3 CLI | Next.js 15 + React 19 + Tailwind 4 | Run `npx shadcn@latest init` and pick the React 19 / Tailwind v4 template. |
| Postgres 16.x | SQLAlchemy 2.0.x | No known incompatibilities. |

---

## 11. Quick install reference

### Backend

```bash
# Project init
poetry init  # or uv init / hatch new
# core
poetry add "fastapi[standard]@~0.115.7" uvicorn[standard] gunicorn \
           "pydantic@^2.10" "pydantic-settings@^2.6" python-dotenv \
           "sqlalchemy@^2.0.43" "asyncpg@^0.30" "psycopg2-binary@^2.9" "alembic@^1.14" \
           "fastapi-users[sqlalchemy]@^14.0.2" \
           "celery@~5.5" "redis@^5.0" "celery-redbeat@^2.2" "flower@^2.0" \
           "httpx@^0.28" "tenacity@^9.0" \
           "structlog@^24.4" "sentry-sdk[fastapi,celery,sqlalchemy]@^2.18" \
           "slowapi@^0.1.9"
# dev
poetry add --group dev "pytest@^8.3" "pytest-asyncio@^0.24" "pytest-httpx@^0.32" \
                       "testcontainers@^4.8" "factory-boy@^3.3" "dirty-equals@^0.8" \
                       "ruff@^0.7" "mypy@^1.13" "pre-commit@^4.0"
```

### Frontend

```bash
# init Next.js 15
npx create-next-app@latest --typescript --tailwind --app --eslint --src-dir frontend
cd frontend
# shadcn/ui
npx shadcn@latest init
# data + state + forms
npm i "@tanstack/react-query@^5.85" "@tanstack/react-table@^8.20" "zustand@^5.0" \
      "react-hook-form@^7.55" "zod@^3.24" "@hookform/resolvers@^3.9" \
      "recharts@^2.15" "date-fns@^4.0" "lucide-react@^0.460" sonner
# dev
npm i -D "vitest@^2.1" "@vitejs/plugin-react" "@testing-library/react@^16" \
         "@testing-library/jest-dom" "@testing-library/user-event" jsdom \
         "@playwright/test@^1.48" "msw@^2.6" \
         "@tanstack/react-query-devtools@^5.85"
```

---

## 12. Confidence summary

| Decision | Confidence | Notes |
|----------|------------|-------|
| FastAPI 0.115.x pin | HIGH | Verified versions list via Context7. |
| SQLAlchemy 2.0.43 + asyncpg | HIGH | Verified via Context7 + SQLAlchemy release notes. |
| fastapi-users 14.0.2 / Argon2 default | HIGH | Verified via GitHub releases (Nov 2024 → Oct 2025) and Context7 docs. |
| Celery 5.5 (avoid 5.6) | HIGH | Verified via PyPI + Celery changelog. 5.6 released Mar 2026, too fresh. |
| Polymarket Gamma rate limits & schema quirks | HIGH | Verified via Polymarket docs (rate-limits page) + agents repo. |
| Custom client (not `polymarket-apis`) | HIGH | Trade-off well-understood; v1 only needs gamma read-only. |
| Custom Postgres double-entry ledger | HIGH | Standard pattern; pgledger + Modern Treasury articles confirm shape. |
| Next.js 15 + React 19 + shadcn/ui Tailwind v4 | HIGH | Verified via shadcn docs + Next.js upgrade guide. |
| Recharts 2.15+ for React 19 | MEDIUM | Verified peer-dep change; hydration edge cases reported on some setups — apply shadcn's chart recipe rather than custom-rolling. |
| Railway over Fly.io for v1 | MEDIUM | Opinion-based; both work. Railway wins on time-to-demo for our scope. |
| Postgres 16 (not 17) | MEDIUM | Risk-averse choice; PG 17 is fine but extension ecosystem maturity argues for 16 in v1. |
| structlog over loguru | HIGH | OpenTelemetry interop is the deciding factor. |

---

## 13. Sources

### Context7 (verified library docs, mid-2026)
- `/fastapi/fastapi` — versions 0.115/0.118/0.122/0.128 (confirmed 0.115 is the stable production pin)
- `/fastapi-users/fastapi-users` — JWT/cookie backends, Argon2 hashing via pwdlib, SQLAlchemy async user model
- `/sqlalchemy/sqlalchemy` and `/websites/sqlalchemy_en_20` — 2.0 async patterns (`AsyncSession`, `Mapped[]`, `selectinload`)
- `/celery/celeryproject` and `/websites/celeryq_dev_en_stable` — Celery 5.x + beat patterns
- `/vercel/next.js/v15.1.8` — App Router data fetching, async request APIs
- `/tanstack/query` v5.84+ — verified current
- `/tanstack/table` — headless table v8
- `/shadcn-ui/ui` — versions shadcn@3.2.x / 3.5 (React 19 / Tailwind v4 templates)
- `/encode/httpx` — async client patterns
- `/pydantic/pydantic-settings` v2.14 — `SettingsConfigDict` API
- `/pytest-dev/pytest` v9.x (but we pin 8.3)
- `/hynek/argon2-cffi` — Argon2 reference

### Official documentation
- [Polymarket Gamma API rate limits](https://docs.polymarket.com/quickstart/introduction/rate-limits) — verified endpoint-specific limits
- [Polymarket Gamma structure](https://docs.polymarket.com/developers/gamma-markets-api/gamma-structure) — base URL + endpoint inventory
- [Polymarket UMA resolution](https://docs.polymarket.com/developers/resolution/UMA) — settlement flow & timing
- [Polymarket agents repo `gamma.py`](https://github.com/Polymarket/agents/blob/main/agents/polymarket/gamma.py) — concrete endpoint usage + stringified-JSON quirks
- [Next.js 15 upgrade guide](https://nextjs.org/docs/app/guides/upgrading/version-15) — async cookies/headers, caching changes
- [shadcn/ui React 19 + Next 15 guide](https://ui.shadcn.com/docs/react-19) — peer-dep resolution for recharts
- [FastAPI release notes](https://fastapi.tiangolo.com/release-notes/) — 0.115 stable line
- [fastapi-users releases](https://github.com/fastapi-users/fastapi-users/releases) — v14.0.0 (Nov 2024) → 14.0.2 (Oct 2025), Argon2 default, maintenance mode
- [Celery release notes](https://docs.celeryq.dev/en/stable/changelog.html) — 5.5.x and 5.6 (Mar 2026)
- [SQLAlchemy 2.0.43 release](https://pypi.org/project/SQLAlchemy/) — Aug 2025
- [pydantic-settings docs](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) — v2.14 SettingsConfigDict
- [PostgreSQL version guide](https://sqlflash.ai/article/20250729_postgresql-version-chosssing/) — PG 16 vs 17 ecosystem maturity
- [Railway vs Fly comparison](https://docs.railway.com/platform/compare-to-fly) and [The Software Scout 2026 comparison](https://thesoftwarescout.com/fly-io-vs-railway-2026-which-developer-platform-should-you-deploy-on/)

### Patterns & deep-dive references
- [Paul Gross — pgledger: Ledger Implementation in PostgreSQL](https://www.pgrs.net/2025/03/24/pgledger-ledger-implementation-in-postgresql/) — schema shape we adapted
- [Modern Treasury — Immutability & Double-Entry](https://www.moderntreasury.com/journal/enforcing-immutability-in-your-double-entry-ledger) — append-only enforcement
- [Modern Treasury — Scaling a Ledger Part V](https://www.moderntreasury.com/journal/how-to-scale-a-ledger-part-v) — invariants and reconciliation
- [TigerBeetle docs](https://docs.tigerbeetle.com/single-page/) — alternative we deliberately rejected for v1
- [Polymarket agents Gamma reference](https://github.com/Polymarket/agents/blob/main/agents/polymarket/gamma.py) — real-world client patterns
- [Apitally — FastAPI logging guide](https://apitally.io/blog/fastapi-logging-guide) and [Dash0 — structlog vs loguru](https://www.dash0.com/guides/python-logging-libraries) — observability decision
- [Tenacity docs](https://tenacity.readthedocs.io/) — retry decorator patterns used in Gamma client
- [TanStack Query v5 docs](https://tanstack.com/query/v5) — current React 19 patterns

---

*Stack research for: white-label prediction market platform with Polymarket data integration and play-money wallet (production-grade).*
*Researched: 2026-05-25.*
*Confidence overall: HIGH.*
