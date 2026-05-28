# Phase 3: Wallet & Double-Entry Ledger - Context

**Gathered:** 2026-05-27
**Status:** Ready for planning
**Source:** Authored from Spike 001-004 findings + ROADMAP Phase 3 success criteria + STACK §3.2 (discuss-phase skipped — the core technical ambiguity, locking strategy, was resolved empirically by the spike per CLAUDE.md "discuss is optional").

<domain>
## Phase Boundary

Build the financial backbone that every later money-touching phase inherits: an append-only
double-entry ledger (`accounts` / `transfers` / `entries`), race-condition-proof transfers,
idempotency, a `CHECK (balance >= 0)` guard, an admin recharge primitive, a Stripe stub
interface, and a nightly reconciliation task. **No bet logic** (that is Phase 5) — only the
ledger engine and its admin/player read surfaces.

**Delivers (ROADMAP SC#1–#7):**
1. A `user_wallet` account is created in the SAME transaction as user registration.
2. 50 concurrent overdraft transfers → exact balance, zero drift, `CHECK (balance >= 0)` holds.
3. Admin recharge is idempotent via `Idempotency-Key` (debit `house_promo` → credit `user_wallet`).
4. Player reads balance + paginated transaction history; money is ALWAYS a JSON string, never float.
5. NO user-to-user transfer exists anywhere (DB/REST/GraphQL/admin); negative test proves it.
6. Disabled "Add funds" button + `WalletService.recharge(payment_provider="stripe")` → `NotImplementedError`.
7. Nightly `reconcile_wallets` Celery task: `SUM(entries)` vs `accounts.balance`; drift → CRITICAL + Sentry.

**Out of scope (later phases):** bets/settlement (Phase 5), `market_liability`/`house_revenue`
flows in anger (Phase 5), signup bonus (Phase 5), real Stripe (v2), multi-tenant (tenant_id ghosted only).
</domain>

<decisions>
## Implementation Decisions (LOCKED)

### Schema (per STACK §3.2 — UUID model; ARCHITECTURE.md BIGINT is SUPERSEDED)
- `accounts (id UUID PK, owner_type, owner_id, kind, currency DEFAULT 'PLAY_USD', balance NUMERIC(18,4) DEFAULT 0, version INT DEFAULT 0, created_at TIMESTAMPTZ, tenant_id UUID ghost)` + `UNIQUE (owner_type, owner_id, kind, currency)` + `CHECK (balance >= 0)`.
- `transfers (id UUID PK, kind, idempotency_key TEXT UNIQUE, actor_user_id, metadata JSONB, created_at)` — IMMUTABLE (no updated_at/deleted_at).
- `entries (id UUID PK, transfer_id FK, account_id FK, direction CHECK IN ('debit','credit'), amount NUMERIC(18,4) CHECK (amount > 0), created_at)` — IMMUTABLE; index on `account_id`.
- Immutability enforced two ways (reuse Phase 1 `audit_log` pattern): a `BEFORE UPDATE OR DELETE` deny-trigger AND `REVOKE UPDATE, DELETE`.
- All money columns `NUMERIC(18,4)` + Python `Decimal` (PITFALLS #4 — never float). New tables carry the `tenant_id` ghost column (Phase 1 standard).

### Concurrency control (DECIDED by Spike 002)
- **Wallet debit = `SELECT … FOR UPDATE` on the wallet row inside `AsyncSession.begin()`** (pessimistic). Spike 002 at N=50: FOR UPDATE 1.00× attempt amplification vs optimistic 3.38× vs SERIALIZABLE 5.70× — all correct, FOR UPDATE fastest/simplest on a hot single row.
- `CHECK (balance >= 0)` is DB-level defense-in-depth, NOT the primary guard.
- Keep the `version` column for optimistic concurrency on non-hot paths / future use.
- Multi-account transfers acquire row locks in **canonical UUID order** (Spike 004: unordered → deadlock 40P01; ordered → 0). Recharge (2 accounts) and future settlement must follow this.

### Transfer semantics (PITFALLS #10 + Spike 003)
- One DB transaction per transfer: insert `transfers` → insert ≥2 `entries` (net to zero) → mutate `accounts.balance` (+version) → commit; any failure rolls back everything.
- `accounts.balance` is a denormalized cache; truth is `SUM(credit) − SUM(debit)` over `entries`.
- **Idempotency:** `transfers.idempotency_key UNIQUE`; on a duplicate key (`23505`), SELECT and RETURN the existing transfer (a true idempotent 200 response), do NOT error and do NOT re-apply.

### Service surface
- `WalletService` (async) is the only writer: `get_balance(user)`, `get_transactions(user, page)`, `recharge(user, amount, reason, idempotency_key, payment_provider="house")`, and an internal `create_wallet(user, *, session)` used by the registration hook. No "set balance" — only deltas via transfers.
- `recharge(payment_provider="stripe")` raises `NotImplementedError` (v2 wires it without refactor — SC#6).
- Wallet auto-creation hooks into the Phase 2 fastapi-users registration flow (`UserManager.on_after_register` / same-transaction creation) so SC#1's "same transaction as the user row" holds.

### Anti-gambling guard (PITFALLS #3 / SC#5)
- There is NO user-to-user transfer path. Wallet-mutation endpoints reject any `dst_user_id`-style parameter; `entries.account_id` only references the caller's wallet + a system/house account; a negative test asserts no API accepts a user→user move and the schema has no FK that would allow it.

### API serialization (SC#4)
- Pydantic response models serialize all money as **strings** (`Decimal` → str), never JSON floats. Transaction history is paginated (kind, amount, timestamp, reason).

### Reconciliation (SC#7)
- Nightly Celery (RedBeat) `reconcile_wallets` task computes `SUM(entries)` per account, compares to `accounts.balance`, logs at INFO when clean; on injected/real drift logs CRITICAL and a Sentry event fires.

### Claude's Discretion (reasonable defaults — Pol may adjust)
- Seed system singletons `house_promo` (recharge source) and `house_revenue` (Phase 5 sink) via the Phase 3 migration; `market_liability` accounts are created per-market in Phase 4.
- Endpoints: `POST /admin/wallets/{user_id}/recharge` (admin Bearer, `Idempotency-Key` header); `GET /wallet/me/balance` + `GET /wallet/me/transactions?page=` (player cookie).
- Reconciliation schedule: nightly 03:00 UTC via RedBeat.
- Currency fixed to `PLAY_USD` for v1.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Spike findings (this milestone — validated empirically)
- `.planning/spikes/LOCKING-ATOMICITY-ANALYSIS.md` — locking decision (FOR UPDATE), atomicity, idempotency, deadlock-ordering, with the spike-002 numbers.
- `.planning/spikes/_lib/harness.py` — the exact validated schema DDL + SQL patterns (FOR UPDATE, idempotency 23505, canonical lock order) on SQLAlchemy 2.0 async + asyncpg.
- `.planning/spikes/MANIFEST.md` — verdict table for spikes 001–004.

### Design research
- `.planning/research/STACK.md` §3 (wallet/ledger — schema §3.2, the 7 key rules, testing note "MUST test against Postgres").
- `.planning/research/PITFALLS.md` #1 (race/FOR UPDATE), #4 (Decimal/NUMERIC), #5 (idempotent), #10 (one-transaction boundary), #3 (regulatory/no transfer) + the "Looks Done But Isn't" wallet checklist.
- `.planning/research/ARCHITECTURE.md` — note its BIGINT ledger model is SUPERSEDED by STACK §3.2 (UUID).

### Existing codebase patterns to reuse
- Phase 1 Alembic migration `0001` (audit_log immutability trigger + REVOKE + `tenant_id` ghost + money-column lint) — replicate the immutability pattern for `transfers`/`entries`.
- Phase 2 `User` + `RefreshToken` ORM, `UserManager`, async session factory (`app/db/session.py` lazy engine) — hook wallet creation into registration.
- `app/core/config.py` Settings; structlog + Sentry helpers; testcontainers integration-test harness (`pytest.mark.integration`).
</canonical_refs>

<specifics>
## Specific Ideas

- The concurrent-correctness gate (SC#2) should reuse the spike's `asyncio.gather` + invariant-check
  shape as an integration test (50 concurrent, exact balance, drift 0, CHECK rejects overdraw) against
  testcontainers Postgres — it is the phase's signature test.
- The idempotency test (SC#3) and the fault-injection atomicity test (PITFALLS #10) mirror Spike 003.
- Money-as-string serialization must have an explicit test asserting the JSON payload contains a string,
  not a float (PITFALLS "Looks Done But Isn't").
</specifics>

<deferred>
## Deferred Ideas

- Real Stripe recharge (Phase 3 ships only the `payment_provider="stripe"` → `NotImplementedError` stub).
- `market_liability` / `house_revenue` debit/credit flows exercised by bets + settlement (Phase 5).
- Signup bonus credit on email verification (Phase 5, `idempotency_key = bonus:{user_id}`).
- Multi-tenant scoping (tenant_id is ghosted/constant in v1).
</deferred>

---

*Phase: 03-wallet-double-entry-ledger*
*Context authored 2026-05-27 from Spike 001–004 + ROADMAP SC + STACK §3.2 (discuss-phase intentionally skipped — ambiguity resolved by spike).*
