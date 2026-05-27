# Phase 3: Wallet & Double-Entry Ledger - Research

**Researched:** 2026-05-27
**Domain:** Append-only double-entry ledger + race-safe wallet on FastAPI 0.115 / SQLAlchemy 2.0 async + asyncpg / Postgres 16 / Celery 5.5 + RedBeat / fastapi-users v15
**Confidence:** HIGH — locking/atomicity/idempotency empirically validated by Spikes 001-004; the registration-hook transaction question is resolved by reading the *installed* fastapi-users 15.0.5 source; serialization/header/schedule patterns confirmed against official docs. All packages already pinned in `backend/uv.lock` (no new external dependencies).

> **The locking debate is CLOSED.** Spike 002 chose pessimistic `SELECT … FOR UPDATE` inside
> `AsyncSession.begin()` (1.00× attempt amplification at N=50 vs optimistic 3.38× vs SERIALIZABLE
> 5.70×). This research does NOT re-litigate it — it wires the seven things the spike did not cover.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
**Schema (per STACK §3.2 — UUID model; ARCHITECTURE.md BIGINT is SUPERSEDED):**
- `accounts (id UUID PK, owner_type, owner_id, kind, currency DEFAULT 'PLAY_USD', balance NUMERIC(18,4) DEFAULT 0, version INT DEFAULT 0, created_at TIMESTAMPTZ, tenant_id UUID ghost)` + `UNIQUE (owner_type, owner_id, kind, currency)` + `CHECK (balance >= 0)`.
- `transfers (id UUID PK, kind, idempotency_key TEXT UNIQUE, actor_user_id, metadata JSONB, created_at)` — IMMUTABLE (no updated_at/deleted_at).
- `entries (id UUID PK, transfer_id FK, account_id FK, direction CHECK IN ('debit','credit'), amount NUMERIC(18,4) CHECK (amount > 0), created_at)` — IMMUTABLE; index on `account_id`.
- Immutability enforced two ways (reuse Phase 1 `audit_log` pattern): a `BEFORE UPDATE OR DELETE` deny-trigger AND `REVOKE UPDATE, DELETE`.
- All money columns `NUMERIC(18,4)` + Python `Decimal` (PITFALLS #4 — never float). New tables carry the `tenant_id` ghost column (Phase 1 standard).

**Concurrency control (DECIDED by Spike 002):**
- **Wallet debit = `SELECT … FOR UPDATE` on the wallet row inside `AsyncSession.begin()`** (pessimistic).
- `CHECK (balance >= 0)` is DB-level defense-in-depth, NOT the primary guard.
- Keep the `version` column for optimistic concurrency on non-hot paths / future use.
- Multi-account transfers acquire row locks in **canonical UUID order** (Spike 004).

**Transfer semantics (PITFALLS #10 + Spike 003):**
- One DB transaction per transfer: insert `transfers` → insert ≥2 `entries` (net to zero) → mutate `accounts.balance` (+version) → commit; any failure rolls back everything.
- `accounts.balance` is a denormalized cache; truth is `SUM(credit) − SUM(debit)` over `entries`.
- **Idempotency:** `transfers.idempotency_key UNIQUE`; on a duplicate key (`23505`), SELECT and RETURN the existing transfer (a true idempotent 200 response), do NOT error and do NOT re-apply.

**Service surface:**
- `WalletService` (async) is the only writer: `get_balance(user)`, `get_transactions(user, page)`, `recharge(user, amount, reason, idempotency_key, payment_provider="house")`, and an internal `create_wallet(user, *, session)` used by the registration hook. No "set balance" — only deltas via transfers.
- `recharge(payment_provider="stripe")` raises `NotImplementedError` (v2 wires it without refactor — SC#6).
- Wallet auto-creation hooks into the Phase 2 fastapi-users registration flow so SC#1's "same transaction as the user row" holds.

**Anti-gambling guard (PITFALLS #3 / SC#5):**
- There is NO user-to-user transfer path. Wallet-mutation endpoints reject any `dst_user_id`-style parameter; `entries.account_id` only references the caller's wallet + a system/house account; a negative test asserts no API accepts a user→user move and the schema has no FK that would allow it.

**API serialization (SC#4):** Pydantic response models serialize all money as **strings** (`Decimal` → str), never JSON floats. Transaction history is paginated (kind, amount, timestamp, reason).

**Reconciliation (SC#7):** Nightly Celery (RedBeat) `reconcile_wallets` task computes `SUM(entries)` per account, compares to `accounts.balance`, logs INFO when clean; on drift logs CRITICAL and a Sentry event fires.

### Claude's Discretion (reasonable defaults — Pol may adjust)
- Seed system singletons `house_promo` (recharge source) and `house_revenue` (Phase 5 sink) via the Phase 3 migration; `market_liability` accounts are created per-market in Phase 4.
- Endpoints: `POST /admin/wallets/{user_id}/recharge` (admin Bearer, `Idempotency-Key` header); `GET /wallet/me/balance` + `GET /wallet/me/transactions?page=` (player cookie).
- Reconciliation schedule: nightly 03:00 UTC via RedBeat.
- Currency fixed to `PLAY_USD` for v1.

### Deferred Ideas (OUT OF SCOPE)
- Real Stripe recharge (Phase 3 ships only the `payment_provider="stripe"` → `NotImplementedError` stub).
- `market_liability` / `house_revenue` debit/credit flows exercised by bets + settlement (Phase 5).
- Signup bonus credit on email verification (Phase 5, `idempotency_key = bonus:{user_id}`).
- Multi-tenant scoping (tenant_id is ghosted/constant in v1).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| WAL-01 | One `user_wallet` (PLAY_USD) created automatically on registration | §"SC#1 — Same-transaction wallet creation"; the fastapi-users v15 commit-before-hook finding drives the recommended pattern |
| WAL-03 | Player can view current wallet balance | §"SC#4 — Money-as-string serialization"; `GET /wallet/me/balance` |
| WAL-04 | Player can view full paginated transaction history | §"SC#4"; keyset/offset pagination over `entries` joined to `transfers` |
| WAL-06 | Append-only double-entry ledger; balance is a reconciled cache | Locked schema (above) + §"Immutability pattern (reuse Phase 1)" + reconciliation §SC#7 |
| WAL-07 | All writes use `FOR UPDATE` in one tx with `idempotency_key UNIQUE` | Spike 002/003 — harness `_spend_once` is the exact validated shape |
| WAL-08 | `CHECK (balance >= 0)` on every wallet account | Locked schema; `BALANCE_CHECK_DDL` in harness; defense-in-depth |
| WAL-09 | Non-transferable between users at DB schema level; no API path | §"SC#5 — Anti-gambling firewall"; negative-test shape |
| PLT-05 | Stripe stub: disabled "Add funds" button + `recharge(payment_provider="stripe")` → NotImplementedError | §"SC#6 — Stripe stub"; feature flag `stripe_recharge_enabled` already seeded in Phase 1 |
| PLT-09 | Nightly reconciliation; drift → CRITICAL + alert | §"SC#7 — Reconciliation"; RedBeat crontab entry + structlog CRITICAL + Sentry |
</phase_requirements>

## Summary

Phase 3 builds the financial backbone: a Postgres-native `accounts`/`transfers`/`entries` double-entry ledger with race-safe transfers, idempotency, a non-negative balance guard, an idempotent admin recharge primitive, a Stripe stub, and a nightly reconciliation task. Every schema, locking, atomicity, idempotency, and deadlock-ordering decision is already locked and **empirically validated** by Spikes 001-004 against testcontainers Postgres 16 on the exact stack. The `_lib/harness.py` file is not just a spike artifact — its `_spend_once`, `spend`, `attempt_with_fault`, `locked_transfer`, and `run_load` functions are the **reference implementation** the production `WalletService` should mirror, and `run_load` + the `LoadResult.correct` invariant check is the literal shape of the SC#2 signature test.

The research's primary new contribution is resolving **SC#1's "same transaction as the user row"** constraint. Reading the installed `fastapi-users 15.0.5` source proves the stock `SQLAlchemyUserDatabase.create()` calls `await self.session.commit()` *before* `on_after_register` ever fires. Therefore the existing `on_after_register` hook (which opens its own audit session) **cannot** satisfy SC#1 as written — by the time it runs, the user row is already committed in a separate transaction. The recommended fix is a thin custom `UserManager.create()` override (or a custom user-db adapter) that inserts the `user_wallet` row into the same session immediately after the user `INSERT` and before the single `commit()`. This is the one genuinely non-obvious wiring decision in the phase and the plan must make it explicit. (See Assumptions Log A1 — exact mechanism choice is a design decision for the planner; both viable options are documented.)

The other open items resolve cleanly: Pydantic v2 **already** serializes `Decimal` as a JSON string by default in `mode="json"` (FastAPI's response path), so SC#4 is met by default — but an explicit `PlainSerializer` annotated type is the prescribed defense-in-depth against a future float regression. FastAPI reads the `Idempotency-Key` header via a `Header()` parameter (underscores auto-map to hyphens). RedBeat picks up a `crontab`-scheduled entry appended to the existing empty `celery_app.conf.beat_schedule = {}`. The Phase 1 `audit_log` immutability pattern (deny-trigger + `REVOKE`) ports verbatim to `transfers`/`entries`.

**Primary recommendation:** Build `WalletService` as a direct port of the spike harness's transfer pattern (FOR UPDATE inside `async with session.begin()`, 23505→return-existing idempotency, canonical-UUID lock order). Override `UserManager.create()` to co-insert the wallet before the single commit (SC#1). Reuse Phase 1's migration immutability + `tenant_id` + Money-lint patterns verbatim. Make the SC#2 concurrent gate a `pytest.mark.integration` test against testcontainers Postgres using the harness `run_load`/`LoadResult.correct` shape.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Wallet balance mutation, double-entry posting | API / Backend (`WalletService` + Postgres) | Database (CHECK, triggers, FOR UPDATE) | All money truth lives server-side in one ACID boundary; the DB enforces the invariants the app relies on |
| Concurrency control (race safety) | Database (row lock via `FOR UPDATE`) | API (one tx per transfer) | Postgres row-level locking is the validated mechanism; the app only owns the transaction boundary |
| Idempotency | Database (`UNIQUE idempotency_key`) | API (catch 23505 → return existing) | Uniqueness is a DB guarantee; the app translates the violation into an idempotent 200 |
| Wallet auto-creation on registration | API / Backend (`UserManager.create` override) | Database (same-tx INSERT) | Must share the user-creation transaction (SC#1) — belongs where fastapi-users owns the user INSERT |
| Money serialization (Decimal → string) | API / Backend (Pydantic response models) | — | Pure presentation-boundary concern; never a DB or client responsibility |
| Reconciliation (drift detection) | Worker (Celery task) | Database (aggregate SUM), Observability (structlog/Sentry) | Scheduled out-of-band job; reads ledger, never mutates; alerts via existing observability |
| "Add funds" disabled button (Stripe stub) | Frontend (Next.js) | API (`recharge(payment_provider="stripe")` raises) | UI affordance + a backend method signature; no real payment tier in v1 |
| Anti-gambling firewall (no user→user) | Database (no FK path) + API (reject `dst_user_id`) | — | Defense at schema level (no FK that allows it) AND request level (schema rejects the param) |

## Standard Stack

**No new external packages.** Every dependency this phase needs is already declared in `backend/pyproject.toml` and pinned in `backend/uv.lock`. This is a pure build-on-existing-stack phase.

### Core (already installed — versions verified from `backend/uv.lock`)
| Library | Installed version | Purpose | Why Standard |
|---------|-------------------|---------|--------------|
| SQLAlchemy | `2.0.50` `[VERIFIED: uv.lock]` | Async ORM + Core; `AsyncSession.begin()`, `select(...).with_for_update()` | The validated spike stack; 2.0 async-first API |
| asyncpg | `0.31.0` `[VERIFIED: uv.lock]` | Async Postgres driver | Returns `NUMERIC` as `Decimal` natively (PITFALLS #4); the spike driver |
| Alembic | `1.18.4` `[VERIFIED: uv.lock]` | Migration `0003` (down_revision `0002_phase2_auth`) | Phase 1/2 used it; runs sync via psycopg2 |
| psycopg2-binary | `2.9.12` `[VERIFIED: uv.lock]` | Sync driver for Alembic | Alembic `env.py` is synchronous |
| Pydantic | `2.13.4` `[VERIFIED: uv.lock]` | Request/response schemas; Decimal-as-string | v2 serializes Decimal→JSON string by default (SC#4) |
| Celery | `5.5.3` `[VERIFIED: uv.lock]` | `reconcile_wallets` task | The validated background-task stack |
| celery-redbeat | `2.3.3` `[VERIFIED: uv.lock]` | Redis-backed beat scheduler | `celery_app.conf.beat_scheduler` already set to `redbeat.RedBeatScheduler` |
| fastapi-users | `15.0.5` `[VERIFIED: uv.lock]` | User mgmt; registration hook for SC#1 | Phase 2 standard; v15 (not v14) is the installed reality |
| structlog | `25.5.0` `[VERIFIED: uv.lock]` | CRITICAL drift log (SC#7) | Phase 1 observability standard |
| sentry-sdk | `2.60.0` `[VERIFIED: uv.lock]` | Drift alert (SC#7) | Already wired into worker + beat via `app/celery_app.py` |

### Supporting (dev — already installed)
| Library | Installed version | Purpose | When to Use |
|---------|-------------------|---------|-------------|
| testcontainers | `4.14.2` `[VERIFIED: uv.lock]` | Real Postgres 16 for integration tests | SC#2 concurrent gate, immutability, SC#1, idempotency — MUST be Postgres (PITFALLS) |
| pytest-asyncio | (installed, `asyncio_mode="auto"`) | Async tests | All ledger tests |
| dirty-equals | `>=0.8` (installed) | `IsNow`/approx assertions | Timestamp + amount assertions in history tests |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom Postgres ledger | TigerBeetle | Overkill for play-money; separate DB to operate. Rejected in STACK §3.1. |
| Custom Postgres ledger | pgledger | Gives up schema control. Rejected as dependency, used as reference. |
| `FOR UPDATE` (locked) | optimistic version CAS / SERIALIZABLE | Spike 002 measured both: 3.38× / 5.70× amplification on the hot wallet row. FOR UPDATE wins. Do not revisit. |

**Installation:** None. `uv sync --directory backend` is already satisfied.

## Package Legitimacy Audit

> This phase installs **no** external packages. All libraries are pre-existing, pinned in `backend/uv.lock`, and already in production use across Phases 1-2. `slopcheck` was not available at research time, but the audit is moot: there is nothing new to vet. The table below records the in-use versions for traceability.

| Package | Registry | Status | Source Repo | slopcheck | Disposition |
|---------|----------|--------|-------------|-----------|-------------|
| sqlalchemy 2.0.50 | PyPI | mature, in-use since Phase 1 | github.com/sqlalchemy/sqlalchemy | n/a (not run) | Already approved (Phase 1) |
| asyncpg 0.31.0 | PyPI | mature, in-use | github.com/MagicStack/asyncpg | n/a | Already approved |
| celery-redbeat 2.3.3 | PyPI | in-use (Phase 1 beat) | github.com/sibson/redbeat | n/a | Already approved |
| fastapi-users 15.0.5 | PyPI | in-use (Phase 2) | github.com/fastapi-users/fastapi-users | n/a | Already approved |
| pydantic 2.13.4 | PyPI | in-use since Phase 1 | github.com/pydantic/pydantic | n/a | Already approved |

**Packages removed due to slopcheck [SLOP] verdict:** none (no new packages).
**Packages flagged as suspicious [SUS]:** none.

## Architecture Patterns

### System Architecture Diagram

```
                           ┌─────────────────────────────────────────────┐
   REGISTRATION (SC#1)     │  POST /auth/register (existing proxy route)  │
   ───────────────────────►│  UserManager.create()  [OVERRIDDEN]          │
                           │    1. validate_password                       │
                           │    2. user_db.create(dict)  ── INSERT users   │
                           │    3. WalletService.create_wallet(session) ──┐│
                           │    4. session.commit()  ◄── ONE TRANSACTION ──┘│
                           │    5. on_after_register (audit, email — after)│
                           └─────────────────────────────────────────────┘
                                              │ (commits user + wallet atomically)
                                              ▼
                           ┌─────────────────────────────────────────────┐
   ADMIN RECHARGE (SC#3)   │  POST /admin/wallets/{user_id}/recharge      │
   Bearer + Idempotency-Key│  WalletService.recharge(payment_provider=    │
   ───────────────────────►│    "house")                                  │
                           │    async with session.begin():               │  ┌──────────────┐
                           │      lock accounts in canonical UUID order ───┼─►│  Postgres 16 │
                           │      INSERT transfers(idempotency_key) ───────┼─►│  accounts    │
                           │        └─ 23505? SELECT existing, return 200  │  │  transfers   │
                           │      INSERT entries(debit house_promo,        │  │  entries     │
                           │                     credit user_wallet)       │  │              │
                           │      UPDATE balances (+version)               │  │ CHECK >= 0   │
                           │      AuditService.record(session) ── same tx  │  │ deny-trigger │
                           │    commit                                     │  │ REVOKE U/D   │
                           └─────────────────────────────────────────────┘  └──────┬───────┘
                                                                                    │
   PLAYER READS (SC#4)     ┌─────────────────────────────────────────────┐         │
   cookie session          │  GET /wallet/me/balance     → Decimal→str    │◄────────┤
   ───────────────────────►│  GET /wallet/me/transactions?page=  (paged)  │  read   │
                           └─────────────────────────────────────────────┘         │
                                                                                    │
   RECONCILE (SC#7)        ┌─────────────────────────────────────────────┐         │
   RedBeat crontab 03:00   │  Celery task reconcile_wallets               │  read   │
   ───────────────────────►│    for each account: SUM(entries) vs balance │◄────────┘
                           │    drift==0 → log INFO                        │
                           │    drift!=0 → log CRITICAL + sentry capture ──┼──► Sentry
                           └─────────────────────────────────────────────┘
```

The diagram traces the four write/read flows through one shared Postgres boundary. Note the load-bearing detail at the top: the wallet INSERT must sit *inside* the user-creation transaction (steps 2-4), which the stock fastapi-users adapter does not allow (see SC#1 below).

### Recommended Project Structure
```
backend/app/wallet/                 # module stub already exists (currently empty __init__.py)
├── __init__.py
├── models.py        # accounts / transfers / entries ORM (Mapped[Money] for balance/amount)
├── service.py       # WalletService — the ONLY writer (port of harness _spend_once/spend)
├── schemas.py       # Pydantic: BalanceResponse, TransactionPage, RechargeRequest (Decimal→str)
├── router.py        # GET /wallet/me/balance, GET /wallet/me/transactions (player cookie)
├── admin_router.py  # POST /admin/wallets/{user_id}/recharge (admin Bearer, Idempotency-Key)
├── reconcile.py     # reconcile_wallets Celery task + RedBeat schedule entry
├── constants.py     # account kinds, owner types, transfer kinds, PLAY_USD, system-account UUIDs
└── exceptions.py    # InsufficientBalance, UserToUserTransferForbidden, etc.

backend/alembic/versions/0003_phase3_wallet_ledger.py   # down_revision = "0002_phase2_auth"
backend/tests/wallet/
├── conftest.py
├── test_models.py                 # schema shape, Money-lint compliance
├── test_migration_0003.py         # immutability trigger + REVOKE + CHECK + tenant_id default
├── test_wallet_creation.py        # SC#1: register → wallet exists in same tx
├── test_concurrent_transfers.py   # SC#2: 50 concurrent, drift 0, CHECK rejects (integration)
├── test_idempotency.py            # SC#3: same Idempotency-Key → one transfer (integration)
├── test_atomicity.py              # PITFALLS #10: fault mid-tx → full rollback (integration)
├── test_money_serialization.py    # SC#4: JSON payload is string, not float
├── test_no_user_to_user.py        # SC#5: negative test — dst_user_id rejected
├── test_stripe_stub.py            # SC#6: recharge(payment_provider="stripe") raises
└── test_reconcile.py              # SC#7: clean → INFO; injected drift → CRITICAL + sentry
```

### Pattern 1: Race-safe transfer (port of the validated spike harness)
**What:** One transaction per transfer; lock wallet row(s) `FOR UPDATE`; insert transfer + paired entries; mutate balance cache; commit.
**When to use:** Every `WalletService` write (recharge now; bet placement reuses it in Phase 5).
**Example (the validated shape — from `.planning/spikes/_lib/harness.py` `_spend_once`, lines 198-284):**
```python
# Source: .planning/spikes/_lib/harness.py (VALIDATED Spike 002/003)
async with session.begin():                          # ONE unit of work
    row = (await session.execute(
        select(Account.balance, Account.version)
        .where(Account.id == wallet_id)
        .with_for_update()                            # pessimistic row lock (Spike 002)
    )).one()
    if row.balance < amount:
        raise InsufficientBalance                     # CHECK >= 0 is defense-in-depth, not primary
    transfer = Transfer(kind=..., idempotency_key=key, actor_user_id=...)
    session.add(transfer)
    await session.flush()                             # get transfer.id for the entries' FK
    session.add_all([
        Entry(transfer_id=transfer.id, account_id=src_id, direction="debit",  amount=amount),
        Entry(transfer_id=transfer.id, account_id=dst_id, direction="credit", amount=amount),
    ])
    await session.execute(update(Account)
        .where(Account.id == src_id)
        .values(balance=Account.balance - amount, version=Account.version + 1))
    await session.execute(update(Account)
        .where(Account.id == dst_id)
        .values(balance=Account.balance + amount))
    # commit on clean exit; ANY exception ⇒ full rollback (Spike 003 part 1 proved this)
```
> Note on multi-account locks: recharge touches 2 accounts (`house_promo` + `user_wallet`). Acquire BOTH `FOR UPDATE` locks in **canonical UUID order** (`sorted((a_id, b_id), key=str)`) before mutating — Spike 004 proved unordered → `40P01` deadlock, ordered → zero. See harness `locked_transfer` lines 510-546.

### Pattern 2: Idempotent recharge (23505 → return existing)
**What:** On a duplicate `idempotency_key`, the `transfers` INSERT raises Postgres `23505`; catch it, SELECT the existing transfer by key, return it as a 200 (same transfer id, no re-apply).
**When to use:** Admin recharge endpoint (SC#3); every future transfer-creating endpoint.
**Example (validated by Spike 003 part 2 — 10 concurrent same-key → 1 applied + 9 deduped):**
```python
# Source: .planning/spikes/LOCKING-ATOMICITY-ANALYSIS.md §7 + harness spend() lines 318-336
from sqlalchemy.exc import IntegrityError

try:
    async with session.begin():
        transfer = await _post_transfer(session, ..., idempotency_key=key)
    return transfer                              # fresh transfer — first caller
except IntegrityError as exc:
    if getattr(exc.orig, "sqlstate", None) == "23505":   # unique_violation
        existing = (await session.execute(
            select(Transfer).where(Transfer.idempotency_key == key)
        )).scalar_one()
        return existing                          # true idempotent 200 — no double-credit
    raise
```
> Implementation note: the harness used raw `text()` + `DBAPIError`; the production code uses the ORM, so catch `IntegrityError` and read `.orig.sqlstate`. The SQLSTATE constant `"23505"` is the same one the harness branches on (`SQLSTATE_UNIQUE_VIOLATION`, harness line 78).

### Pattern 3: Immutability (reuse Phase 1 `audit_log` pattern verbatim)
**What:** `BEFORE UPDATE OR DELETE` deny-trigger + `REVOKE UPDATE, DELETE … FROM PUBLIC` on `transfers` and `entries`.
**When to use:** The `0003` migration.
**Example (direct port of `0001_phase1_foundations.py` lines 79-99):**
```python
# Source: backend/alembic/versions/0001_phase1_foundations.py (Phase 1, tests green)
LEDGER_IMMUTABLE_MSG = "transfers/entries are append-only -- UPDATE and DELETE are forbidden"
op.execute(f"""
    CREATE OR REPLACE FUNCTION raise_ledger_immutable() RETURNS TRIGGER AS $$
    BEGIN RAISE EXCEPTION '{LEDGER_IMMUTABLE_MSG}'; END;
    $$ LANGUAGE plpgsql;
""")
for tbl in ("transfers", "entries"):
    op.execute(f"""
        CREATE TRIGGER {tbl}_immutability_trigger
        BEFORE UPDATE OR DELETE ON {tbl}
        FOR EACH ROW EXECUTE FUNCTION raise_ledger_immutable();
    """)
    op.execute(f"REVOKE UPDATE, DELETE ON {tbl} FROM PUBLIC;")
```
> The test asserts the literal message (Phase 1 precedent: `test_audit_log_update_blocked` checks `"append-only" in msg or "permission denied" in msg`). `accounts.balance` is NOT immutable — it is a mutable cache; only `transfers`/`entries` get the trigger.

### Pattern 4: Money-as-string serialization (SC#4)
**What:** Decimal money fields serialize as JSON strings, never floats.
**When to use:** Every wallet response schema.
**Example:**
```python
# Source: https://pydantic.dev/docs/validation/latest/concepts/serialization/
from decimal import Decimal
from typing import Annotated
from pydantic import BaseModel, PlainSerializer

# Pydantic v2 ALREADY serializes Decimal→string in mode="json" (FastAPI's response path).
# This PlainSerializer is defense-in-depth: it makes the contract explicit + regression-proof.
MoneyStr = Annotated[Decimal, PlainSerializer(lambda v: str(v), return_type=str, when_used="json")]

class BalanceResponse(BaseModel):
    balance: MoneyStr
    currency: str            # "PLAY_USD"

class TransactionItem(BaseModel):
    kind: str
    amount: MoneyStr
    direction: str           # "debit" | "credit"
    created_at: datetime     # TIMESTAMPTZ → ISO 8601 string
    reason: str | None
```
> **Verified default:** Pydantic v2 serializes `Decimal` as a JSON **string** by default — `model_dump(mode="json")` → `{'amount': '10.0000'}` `[CITED: github.com/pydantic/pydantic#7120, #7457]`. FastAPI's `response_model` uses `mode="json"`, so SC#4 passes even without the annotation. The `PlainSerializer` is the *prescribed* explicit guard so a careless future change to `float` can't silently regress it. **The SC#4 test must assert the raw JSON bytes contain a quoted string** (e.g. `'"10.0000"' in response.text` / `isinstance(response.json()["balance"], str)`), per CONTEXT "Looks Done But Isn't".

### Pattern 5: Idempotency-Key header (FastAPI)
**Example:**
```python
# Source: https://fastapi.tiangolo.com/tutorial/header-params/
from typing import Annotated
from fastapi import Header

@admin_router.post("/admin/wallets/{user_id}/recharge")
async def recharge(
    user_id: UUID,
    body: RechargeRequest,
    idempotency_key: Annotated[str | None, Header()] = None,   # maps to "Idempotency-Key"
    admin: User = Depends(current_active_admin),
): ...
```
> FastAPI auto-converts `idempotency_key` ↔ `Idempotency-Key` (underscore→hyphen) and headers are case-insensitive `[CITED: fastapi.tiangolo.com/tutorial/header-params]`. Decide whether a missing key is a 400 (require it) or server-generated — CONTEXT/ROADMAP SC#3 implies the client supplies it, so require it (400 if absent) for the admin recharge endpoint.

### Pattern 6: RedBeat nightly schedule entry (SC#7)
**Example:**
```python
# Source: https://redbeat.readthedocs.io/en/latest/tasks.html
from celery.schedules import crontab
from app.celery_app import celery_app

# Append to the existing empty dict (app/celery_app.py line 44: beat_schedule = {})
celery_app.conf.beat_schedule.update({
    "reconcile-wallets-nightly": {
        "task": "app.wallet.reconcile.reconcile_wallets",
        "schedule": crontab(hour=3, minute=0),     # 03:00 UTC (Claude's Discretion)
    },
})

@celery_app.task(name="app.wallet.reconcile.reconcile_wallets")
def reconcile_wallets() -> None:
    # Celery 5.5 has NO native async — wrap the async work in asyncio.run(...)
    # (STACK §1.4 gotcha). Do NOT share the FastAPI event loop.
    asyncio.run(_reconcile_async())
```
> The `RedBeatScheduler` is already configured (`app/celery_app.py` line 42). Tasks must be importable by the worker — register the task module so `celery_app.autodiscover_tasks` or an explicit import picks it up (mirror how Phase 1's `sentry_test_task` is defined on `celery_app`).

### Anti-Patterns to Avoid
- **Computing the new balance in Python from a non-locked read** — the exact race Spike 001 demonstrated (drift + money created). Always `FOR UPDATE` first.
- **Treating `CHECK (balance >= 0)` as the primary guard** — it only protects a bare single-row decrement; it does NOT protect a read→decide→write across multiple rows (LOCKING-ATOMICITY §3 nuance). FOR UPDATE is primary; CHECK is the net.
- **Surfacing `23505` as a 409/500 on a duplicate idempotency key** — that breaks idempotency. Return the existing transfer as 200.
- **Relying on `on_after_register` to create the wallet "atomically"** — it fires *after* the user commit in fastapi-users v15 (proven below). It would create the wallet in a *separate* transaction, failing SC#1.
- **Calling `session.commit()` inside `create_wallet`** — the registration override owns the single commit. `create_wallet(session)` must only `add`/`flush`, never commit (mirror `AuditService.record` contract).
- **Any `dst_user_id`-style parameter on a wallet-mutation endpoint** — SC#5 firewall. The only credit destination a user can name is their own wallet; the only debit source for recharge is a system/house account.
- **`async def` Celery task body** — Celery 5.5 has no native async; use `asyncio.run()` inside a sync task (STACK §1.4).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Race-safe debit | Custom Python mutex / app-level lock | Postgres `SELECT … FOR UPDATE` (Spike 002) | App locks don't survive multiple workers; the DB row lock is the only correct boundary |
| Idempotency dedup | A `seen_keys` set / Redis lock | `UNIQUE(idempotency_key)` + catch 23505 | The DB unique constraint is atomic & crash-safe; a cache is not (Spike 003) |
| Deadlock avoidance | Retry-everything / global lock | Canonical UUID lock ordering (Spike 004) | Ordering *prevents* the cycle; retry only papers over it |
| Ledger immutability | App-layer "please don't UPDATE" convention | Deny-trigger + `REVOKE` (Phase 1 pattern) | App conventions get bypassed; the DB enforces it for every connection |
| Money type | `float` / Postgres `MONEY` | `NUMERIC(18,4)` + `Decimal` via `Mapped[Money]` | Float drifts (PITFALLS #4); `Money` lint already enforces this in CI |
| Decimal→JSON | Manual `str()` in every endpoint | Pydantic default + `PlainSerializer` annotated type | Pydantic already does it; the annotation makes it explicit & DRY |
| Wallet creation atomicity | Post-commit hook + compensating delete | Same-transaction INSERT in `UserManager.create` | A two-step create leaves orphaned users on failure (the exact split-commit anti-pattern PITFALLS #10 warns against) |

**Key insight:** Almost every hard problem in this phase has already been solved either by Postgres primitives (locking, uniqueness, triggers) validated in the spikes, or by an existing Phase 1/2 pattern in this codebase. The phase's risk is in *wiring* (especially SC#1), not in *inventing*.

## Runtime State Inventory

> This is a greenfield build phase (new tables, new code) on an unreleased platform — but it does touch existing live-ish state in three narrow ways. Each category answered explicitly.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | **None requiring migration.** The `accounts`/`transfers`/`entries` tables do not yet exist; no historical ledger data to backfill. Existing `users` rows (from Phase 2 dev/test) will NOT retroactively get wallets — SC#1 creates wallets only for *new* registrations. **Decision for planner:** if any pre-existing users must get wallets, that is a one-off data backfill task; ROADMAP SC#1 only requires it on registration, so no backfill is in scope unless Pol says otherwise. | None in scope (flag backfill as an open question) |
| Live service config | **Celery beat schedule.** `app/celery_app.py` line 44 has `beat_schedule = {}` — Phase 3 appends the `reconcile-wallets-nightly` entry. RedBeat stores the live schedule in **Redis**, not git; a running beat container will pick up the new entry on restart. No UI-only config. | Append entry in code; restart beat in deploy |
| OS-registered state | **None.** No Task Scheduler / launchd / pm2 process names embed wallet identifiers. | None — verified by absence of any OS-scheduler usage (Celery owns scheduling) |
| Secrets / env vars | **None new.** `DATABASE_URL`, `REDIS_URL`, `SENTRY_DSN` already exist in `Settings`. No new secret. The `stripe_recharge_enabled` feature flag is already seeded in Postgres by Phase 1 migration `0001` (`FALSE`) — Phase 3 reads it, does not add it. | None |
| Build artifacts / installed packages | **None.** No new package → no new egg-info/lockfile churn. `uv.lock` already contains every dependency. The `app/wallet/__init__.py` stub exists and will be populated. | None |

**The canonical question:** *After every file is written, what runtime systems still need attention?* Only one: the **Celery beat process must be restarted** so RedBeat loads the new `reconcile-wallets-nightly` schedule from the updated config. Everything else is pure new-code/new-schema.

## Common Pitfalls

### Pitfall 1: `on_after_register` is NOT same-transaction in fastapi-users v15 (breaks SC#1)
**What goes wrong:** The natural instinct is to create the wallet in the existing `on_after_register` hook. But the user row is already committed by then, so the wallet lands in a *separate* transaction — violating SC#1's "same transaction as the user row." If the wallet INSERT then fails, you have a committed user with no wallet (and the audit hook also already ran).
**Why it happens:** `SQLAlchemyUserDatabase.create()` (installed v15.0.5) does `session.add(user)` → **`await self.session.commit()`** → `refresh` → returns; only *then* does `BaseUserManager.create()` call `await self.on_after_register(...)`. The commit is baked into the adapter, before any hook.
**How to avoid:** Override `UserManager.create()` (or supply a custom user-db adapter) so the wallet INSERT happens on the same session *between* the user INSERT and a single commit. See SC#1 below for the two concrete options.
**Warning signs:** A test that registers a user and immediately queries the wallet passes — but a test that injects a failure into wallet creation leaves a committed user behind.

### Pitfall 2: Catching the wrong exception class for 23505
**What goes wrong:** The spike harness caught `sqlalchemy.exc.DBAPIError` and read `.orig.sqlstate`. Production ORM code that inserts via `session.add()` will raise `sqlalchemy.exc.IntegrityError` (a subclass) on the unique violation — code that only catches a bare `Exception` or the wrong class will mis-handle idempotency.
**Why it happens:** Raw `text()` inserts vs ORM inserts surface slightly different exception wrappers.
**How to avoid:** Catch `IntegrityError`, then branch on `getattr(exc.orig, "sqlstate", None) == "23505"`. Re-raise anything else.
**Warning signs:** Duplicate-key test returns 500 instead of an idempotent 200.

### Pitfall 3: Forgetting canonical lock order on the 2-account recharge
**What goes wrong:** Recharge locks `house_promo` and `user_wallet`. If two operations ever lock them in opposite orders (e.g. a future settlement also touches `house_promo`), Postgres raises `40P01` deadlock.
**Why it happens:** Locking in "business order" (source then destination) is natural but not a total order across all transfer types.
**How to avoid:** Always sort the account IDs (`sorted(ids, key=str)`) and acquire `FOR UPDATE` in that order before mutating (Spike 004). A bounded retry-on-`40P01` is the belt-and-suspenders fallback.
**Warning signs:** Intermittent `40P01` under concurrent recharge + (Phase 5) settlement load.

### Pitfall 4: Money serialized as float in a corner of the API
**What goes wrong:** One endpoint returns `float(balance)` or a dict built by hand, leaking `10.4` instead of `"10.4000"` — exactly the PITFALLS #4 / "Looks Done But Isn't" trap.
**Why it happens:** Pydantic does the right thing by default, so a developer hand-rolling a `JSONResponse` bypasses the guard.
**How to avoid:** Every money value goes out through a Pydantic response model using `MoneyStr`. The SC#4 test asserts on raw JSON text, not the parsed value.
**Warning signs:** `response.json()["balance"]` is a `float` in any test.

### Pitfall 5: Reconciliation task can't be reached / runs in the wrong loop
**What goes wrong:** The `reconcile_wallets` task is defined but the worker never registers it (silent no-op), or it's written `async def` and Celery 5.5 can't run it.
**Why it happens:** Celery has no native async (STACK §1.4); task discovery requires the module to be imported by the worker.
**How to avoid:** Sync task body calling `asyncio.run(_reconcile_async())`; ensure the task module is imported by the celery app (mirror `app/celery_app.py`'s `sentry_test_task`). Test the task function directly in an integration test (call it, assert log + sentry).
**Warning signs:** Beat fires but nothing happens; `flower` shows the task as unregistered.

## Code Examples

### SC#1 — Same-transaction wallet creation (THE key wiring decision)
**Finding (HIGH confidence — read from installed source):** `fastapi_users 15.0.5`'s adapter commits before the hook:
```python
# Source: backend/.venv/Lib/site-packages/fastapi_users_db_sqlalchemy/__init__.py
async def create(self, create_dict: dict[str, Any]) -> UP:
    user = self.user_table(**create_dict)
    self.session.add(user)
    await self.session.commit()        # ← COMMIT happens HERE
    await self.session.refresh(user)
    return user
# Source: backend/.venv/Lib/site-packages/fastapi_users/manager.py  (BaseUserManager.create)
    created_user = await self.user_db.create(user_dict)
    await self.on_after_register(created_user, request)   # ← hook fires AFTER the commit
    return created_user
```
**Recommended fix — Option A (override `UserManager.create`, minimal blast radius):**
```python
# In app/auth/manager.py — override create() to co-insert the wallet in ONE transaction.
async def create(self, user_create, safe=False, request=None):
    await self.validate_password(user_create.password, user_create)
    if await self.user_db.get_by_email(user_create.email) is not None:
        raise exceptions.UserAlreadyExists()
    user_dict = (user_create.create_update_dict() if safe
                 else user_create.create_update_dict_superuser())
    password = user_dict.pop("password")
    user_dict["hashed_password"] = self.password_helper.hash(password)
    # Use the SAME session the user_db adapter holds, but do NOT let it commit early.
    session = self.user_db.session                      # SQLAlchemyUserDatabase.session
    user = self.user_db.user_table(**user_dict)
    session.add(user)
    await session.flush()                               # user.id available, NOT committed
    await WalletService.create_wallet(session, user=user)   # add+flush, no commit
    await session.commit()                              # ONE transaction → SC#1 holds
    await session.refresh(user)
    await self.on_after_register(user, request)
    return user
```
**Recommended fix — Option B (custom user-db adapter):** subclass `SQLAlchemyUserDatabase` and override `create()` to insert the wallet before `commit()`. Cleaner separation but touches the `get_user_db` dependency wiring.
> **Planner decision (A1 in Assumptions Log):** choose A or B. Option A keeps the change inside the already-customized `UserManager` and is the lighter touch; Option B is more "correct layering" but spreads the change. Either satisfies SC#1. **Whichever is chosen, `WalletService.create_wallet(session, *, user)` must `add`+`flush` only and never commit** — exactly the `AuditService.record` caller-owned-transaction contract this codebase already uses. Also confirm `get_user_db` yields a session whose transaction is still open at hook time (it is — the FastAPI dep `get_async_session` does not auto-commit, per `app/db/session.py`).

### SC#1 — The integration test shape
```python
# Source: derived from backend/tests/core/test_audit_immutability.py fixture pattern
pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]

async def test_wallet_created_on_registration(client):
    r = await client.post("/auth/register", json={
        "email": "p@example.com", "password": "Sufficiently-Long-1"})
    assert r.status_code == 201
    user_id = r.json()["id"]
    # exactly one user_wallet, balance 0, PLAY_USD
    # (assert via a fresh session query against accounts)
```

### SC#2 — The signature concurrent gate (reuse the harness directly)
```python
# Source: .planning/spikes/_lib/harness.py run_load() + LoadResult.correct (lines 388-411, 375-385)
async def test_50_concurrent_overdraft(engine):
    # opening balance funds exactly N//2 transfers of 50% each → overdraw rejected, drift 0
    res = await run_load(ledger, label="prod-gate", n=50, per_amount=...,
                         opening=..., strategy="for_update")
    assert res.correct          # final_balance >= 0 AND drift == 0 AND global_entry_sum == 0
    assert res.final_balance == res.opening - res.per_amount * res.outcomes["ok"]
```
> The phase plan should adapt `run_load`/`LoadResult` to the production `WalletService` (replace `_spend_once`'s raw SQL with the service call) OR assert the service produces the identical invariants. This is "the phase's signature test" (CONTEXT §Specific Ideas).

### SC#5 — No user-to-user transfer (negative test)
```python
# The wallet-mutation endpoints must have NO dst_user_id parameter at all.
async def test_no_user_to_user_path(client, admin_token):
    # recharge only credits the path user's own wallet from a HOUSE source
    r = await client.post(f"/admin/wallets/{victim_id}/recharge",
        json={"amount": "10.00", "reason": "x", "dst_user_id": str(other_id)},  # bogus
        headers={"Authorization": f"Bearer {admin_token}", "Idempotency-Key": "k1"})
    # Pydantic forbids the extra field (model_config extra="forbid") → 422,
    # OR the schema simply has no such field. Either way: rejected.
    assert r.status_code in (422, 400)
    # AND a schema-level assertion: entries.account_id FK cannot reference two user wallets
    # in one transfer (no API constructs such a transfer).
```
> Recommend `model_config = ConfigDict(extra="forbid")` on `RechargeRequest` so an unexpected `dst_user_id` is a hard 422 — making the firewall observable at the schema boundary.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| ARCHITECTURE.md BIGINT ledger PKs | STACK §3.2 UUID PKs | Spike milestone | Use UUID `accounts`/`transfers`/`entries`; ARCHITECTURE.md model is SUPERSEDED |
| STACK §3.2 rule 5 "optimistic locking" as wallet guard | FOR UPDATE pessimistic (Spike 002) | Spike 002 | Wallet debit is FOR UPDATE-first; `version` retained for non-hot paths. **Docs follow-up for Pol:** reconcile STACK §3.2 rule 5 wording (flagged in LOCKING-ATOMICITY §5.3 + MANIFEST). |
| fastapi-users v14 (CONTEXT D-01) | v15.0.5 installed | Phase 2 | All hooks/signatures follow v15; `create()` commits before `on_after_register` |

**Deprecated/outdated:**
- The ARCHITECTURE.md ledger schema (BIGINT) — do not use; STACK §3.2 UUID is canonical.
- Any assumption that `on_after_register` can host same-transaction work — false in v15.

## Assumptions Log

> Claims tagged `[ASSUMED]` that the planner / discuss-phase should confirm.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The `UserManager.create()` override (Option A) vs custom adapter (Option B) is a free design choice; both satisfy SC#1. Option A recommended. | SC#1 / Anti-patterns | LOW — both are correct; picking one is a planning decision, not a correctness risk. The *constraint* (same-tx, create_wallet never commits) is verified, not assumed. |
| A2 | No backfill of wallets for pre-existing Phase 2 dev/test users is in scope (SC#1 only requires creation on registration). | Runtime State Inventory | LOW-MED — if Pol wants existing users to have wallets, add a one-off backfill task. Confirm with PM. |
| A3 | Missing `Idempotency-Key` on admin recharge should be a 400 (client must supply it). | Pattern 5 | LOW — alternative is server-generated key; ROADMAP SC#3 phrasing ("calling … twice with the same Idempotency-Key") implies client-supplied. |
| A4 | `gen_random_uuid()` is available without an explicit `CREATE EXTENSION pgcrypto` (Postgres 13+ built-in). | Schema | NONE — verified: Phase 1 (`0001`) and Phase 2 (`0002`) migrations already use `gen_random_uuid()` server defaults successfully against `postgres:16-alpine`. |
| A5 | Reconciliation at 03:00 UTC nightly via `crontab(hour=3, minute=0)`. | Pattern 6 | NONE — explicitly Claude's Discretion in CONTEXT. |

## Open Questions

1. **Wallet backfill for existing users**
   - What we know: SC#1 mandates wallet creation *on registration*. Phase 2 already created some users in dev/test.
   - What's unclear: whether those pre-existing users need wallets now.
   - Recommendation: out of scope unless Pol says otherwise; if needed, a single idempotent backfill task using the same `create_wallet` primitive (one transfer per user is not needed — wallet starts at balance 0).

2. **`actor_user_id` on `transfers` — nullable for system-initiated?**
   - What we know: admin recharge has an admin actor; the registration wallet-creation transfer (if any) has no human actor.
   - What's unclear: whether wallet *creation* posts an opening transfer at all (balance starts 0, so no opening entry is strictly required) vs just an `accounts` row.
   - Recommendation: create the `accounts` row only (balance 0, no transfer) on registration — no money moves, so no double-entry is needed. The first money event is the admin recharge. Confirm in planning. (This keeps SC#1 to a single INSERT and avoids a zero-amount entry that would violate `CHECK (amount > 0)`.)

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker | testcontainers Postgres (SC#2/#3 integration tests) | ✓ (required for backend phases per CLAUDE.md; spikes ran on Docker 29.4.3) | 29.x | none — integration tests cannot run without it (Wave-0 unit tests can) |
| Postgres 16 | ledger schema, FOR UPDATE, triggers, NUMERIC | ✓ via `postgres:16-alpine` testcontainer | 16 | none |
| Redis | RedBeat schedule store, Celery broker | ✓ (Phase 1 docker-compose; tests use `fakeredis`) | 7 | `fakeredis` for unit tests; real Redis for beat |
| uv | dependency mgmt / running tests (`uv run --directory backend`) | ✓ | — | none |

**Missing dependencies with no fallback:** none — the toolchain is the same one Phases 1-2 and the spikes already used successfully.
**Missing dependencies with fallback:** Redis → `fakeredis` for unit-level tests (the reconciliation *task logic* can be unit-tested without a live beat; the *schedule registration* is config and asserted by inspecting `beat_schedule`).

## Validation Architecture

> `workflow.nyquist_validation` is not disabled in config — this section is included.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio (`asyncio_mode = "auto"`) `[VERIFIED: backend/pyproject.toml]` |
| Config file | `backend/pyproject.toml` `[tool.pytest.ini_options]` |
| Integration marker | `@pytest.mark.integration` (testcontainers Postgres) + `pytest.mark.asyncio(loop_scope="session")` |
| Quick run command | `uv run --directory backend pytest -m "not integration" -q` |
| Full suite command | `uv run --directory backend pytest -q` (spins testcontainers Postgres) |

### Phase Requirements → Test Map
| Req / SC | Behavior | Test Type | Automated Command | File Exists? |
|----------|----------|-----------|-------------------|-------------|
| SC#1 / WAL-01 | Registration creates one `user_wallet` in the same tx | integration | `pytest tests/wallet/test_wallet_creation.py -x` | ❌ Wave 0 |
| SC#2 / WAL-07/08 | 50 concurrent overdrafts → balance exact, drift 0, CHECK rejects | integration | `pytest tests/wallet/test_concurrent_transfers.py -x` | ❌ Wave 0 (port harness `run_load`) |
| SC#3 / WAL-06 | Same Idempotency-Key → one transfer, same id returned | integration | `pytest tests/wallet/test_idempotency.py -x` | ❌ Wave 0 |
| PITFALLS #10 | Fault mid-tx → nothing persists | integration | `pytest tests/wallet/test_atomicity.py -x` | ❌ Wave 0 (mirror harness `attempt_with_fault`) |
| SC#4 / WAL-03/04 | Balance + paginated history; money is JSON string | unit + integration | `pytest tests/wallet/test_money_serialization.py -x` | ❌ Wave 0 |
| SC#5 / WAL-09 | No user→user path; `dst_user_id` rejected | unit | `pytest tests/wallet/test_no_user_to_user.py -x` | ❌ Wave 0 |
| SC#6 / PLT-05 | `recharge(payment_provider="stripe")` raises `NotImplementedError` | unit | `pytest tests/wallet/test_stripe_stub.py -x` | ❌ Wave 0 |
| SC#7 / PLT-09 | Clean → INFO; injected drift → CRITICAL + Sentry capture | integration | `pytest tests/wallet/test_reconcile.py -x` | ❌ Wave 0 |
| immutability | UPDATE/DELETE on transfers/entries blocked; CHECK + tenant_id default | integration | `pytest tests/wallet/test_migration_0003.py -x` | ❌ Wave 0 (mirror `test_audit_immutability.py`) |

### Sampling Rate
- **Per task commit:** `uv run --directory backend pytest -m "not integration" -q` (fast — no Docker)
- **Per wave merge:** `uv run --directory backend pytest -q` (full, incl. testcontainers)
- **Phase gate:** full suite green before `/gsd-verify-work`; the SC#2 concurrent gate is the headline observable.

### Wave 0 Gaps
- [ ] `tests/wallet/conftest.py` — wallet-specific fixtures (seed `house_promo`/`house_revenue`, a funded wallet); reuse the session-scoped `engine`/`async_session` fixtures from `tests/conftest.py`.
- [ ] All nine `tests/wallet/test_*.py` files above (none exist yet).
- [ ] The SC#2 test should **port `.planning/spikes/_lib/harness.py`** (`run_load`, `LoadResult`, `_spend_once`) rather than re-derive it — it is already validated.
- Framework install: none needed (pytest + testcontainers already in dev deps).

*The concurrency gate against testcontainers Postgres (SC#2) is the Nyquist-critical observable: it is the one test that, if it passes, proves the race-safety claim empirically — the same proof the spike produced, now bound to production code.*

## Security Domain

> `security_enforcement` not disabled — included.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | reuse | Phase 2 fastapi-users (cookie player / Bearer admin) — recharge endpoint behind `current_active_admin` |
| V3 Session Management | reuse | Phase 2 DatabaseStrategy; no new session surface |
| V4 Access Control | **yes** | Admin recharge requires `is_admin` (Bearer); player reads scoped to `current_active_player` own wallet (no cross-user read) |
| V5 Input Validation | **yes** | Pydantic schemas; `extra="forbid"` on `RechargeRequest` to reject `dst_user_id` (SC#5); amount `Decimal > 0` |
| V6 Cryptography | n/a | No new crypto; UUIDs via `gen_random_uuid()` |
| V7 Error Handling / Logging | **yes** | Reconciliation CRITICAL log + Sentry (SC#7); audit row on recharge (reuse `AuditService.record`) |
| V11 Business Logic | **yes** | Idempotency (no double-credit), non-negative balance, no user→user (regulatory firewall PITFALLS #3) |

### Known Threat Patterns for this stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Double-spend via concurrent debits | Tampering | `FOR UPDATE` row lock (Spike 002) + `CHECK (balance >= 0)` |
| Replayed recharge (network retry / double-click) | Tampering | `idempotency_key UNIQUE` → return existing transfer (Spike 003) |
| Ledger tampering (UPDATE/DELETE) | Tampering / Repudiation | Deny-trigger + `REVOKE` (Phase 1 pattern); reversals are new entries, never edits |
| Privilege misuse: player recharges own/other wallet | Elevation of Privilege | Recharge is admin-only (Bearer + `is_admin`); audit-logged |
| User-to-user value transfer (gambling-law breach) | Elevation / regulatory | No FK path + no API param + `extra="forbid"` + negative test (SC#5, PITFALLS #3) |
| Money exposed as float (precision tampering) | Tampering | `NUMERIC(18,4)` + Decimal + Money-lint + JSON-string serialization (SC#4) |
| Cross-user balance/history read | Information Disclosure | `/wallet/me/*` bound to `current_active_player`; admin reads via separate admin surface |

## Sources

### Primary (HIGH confidence)
- `backend/.venv/Lib/site-packages/fastapi_users_db_sqlalchemy/__init__.py` — `SQLAlchemyUserDatabase.create()` commits before hook (the SC#1 finding, read from installed v15.0.5).
- `backend/.venv/Lib/site-packages/fastapi_users/manager.py` — `BaseUserManager.create()` calls `on_after_register` after the adapter commit.
- `.planning/spikes/_lib/harness.py` + `.planning/spikes/LOCKING-ATOMICITY-ANALYSIS.md` + `.planning/spikes/MANIFEST.md` — validated FOR UPDATE / 23505 idempotency / canonical lock order (Spikes 001-004).
- `backend/alembic/versions/0001_phase1_foundations.py` — immutability trigger + REVOKE + tenant_id pattern to port.
- `backend/app/core/audit/service.py`, `app/auth/manager.py`, `app/db/session.py`, `app/celery_app.py`, `app/db/types.py` — existing patterns (caller-owned tx, sessionmaker hygiene, beat config, Money alias).
- `backend/uv.lock` — exact installed versions (all packages already present).
- `.planning/research/STACK.md` §3, `.planning/research/PITFALLS.md` #1/#4/#5/#10/#3 + "Looks Done But Isn't" checklist, `.planning/ROADMAP.md` Phase 3, `.planning/REQUIREMENTS.md`.

### Secondary (MEDIUM confidence — official docs, current)
- [Pydantic Serialization](https://pydantic.dev/docs/validation/latest/concepts/serialization/) — `field_serializer`, `PlainSerializer`, Annotated reusable serializers.
- [pydantic#7120](https://github.com/pydantic/pydantic/issues/7120) + [pydantic#7457](https://github.com/pydantic/pydantic/issues/7457) — Decimal serializes to JSON string by default in v2.
- [FastAPI Header Parameters](https://fastapi.tiangolo.com/tutorial/header-params/) — `Header()` param, underscore→hyphen, optional default.
- [RedBeat Tasks](https://redbeat.readthedocs.io/en/latest/tasks.html) — crontab `beat_schedule` entry + `RedBeatSchedulerEntry`.

### Tertiary (LOW confidence)
- None — every claim is backed by installed source, a spike, an existing code pattern, or official docs.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all versions read from `uv.lock`; nothing new to install.
- Architecture / locking / atomicity / idempotency: HIGH — empirically validated by Spikes 001-004 on the exact stack.
- SC#1 same-transaction mechanism: HIGH on the *finding* (commit-before-hook, read from source); design choice (Option A vs B) flagged as A1.
- Serialization / header / schedule: HIGH — confirmed against official docs + Pydantic default behavior cross-checked.
- Pitfalls: HIGH — sourced from PITFALLS.md (cross-verified) + the spike nuances.

**Research date:** 2026-05-27
**Valid until:** ~2026-06-27 (stable stack; the only fast-moving risk is a fastapi-users or Pydantic minor bump — re-verify the commit-before-hook behavior if fastapi-users is upgraded past 15.0.x).
