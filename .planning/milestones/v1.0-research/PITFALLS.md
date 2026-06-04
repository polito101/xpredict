# Pitfalls Research

**Domain:** White-label prediction market platform (play money, Polymarket-sourced + house markets)
**Researched:** 2026-05-25
**Confidence:** HIGH (most pitfalls cross-verified from official docs, post-mortems, and authoritative writeups; Polymarket-specific behavior confirmed against docs.polymarket.com and agentbets.ai rate-limit guide)

> **Read this if you read nothing else.** The top three killers for XPredict are:
> 1. **Race conditions on wallet writes** — two bets debit the same balance, balance goes negative or money is created out of thin air. Use `SELECT ... FOR UPDATE` on the wallet row inside the same transaction as the ledger insert. Non-negotiable.
> 2. **Settling markets too early on Polymarket data** — `closed: true` is NOT `resolved`. UMA dispute window is ~2 hours and outcomes can be overturned. Settling on `closed` corrupts user balances.
> 3. **The "play money" regulatory line** — the moment play tokens become tradable, redeemable, or have *any* path to value (referral bonuses with cash equivalent, prizes, swag, "premium" tiers tied to balance), Spain's Ley 13/2011 may classify XPredict as gambling. Keep tokens strictly non-transferable, non-redeemable, no in-platform marketplace.

---

## Critical Pitfalls

Severity scale: **CRITICAL** (product fails or operator gets sued) / **HIGH** (real money or trust lost) / **MEDIUM** (degraded UX or technical debt) / **LOW** (annoying but recoverable).

### Pitfall 1: Wallet race conditions allow double-spend or negative balances

**Severity:** CRITICAL
**What goes wrong:**
Two concurrent bet requests for the same user both read balance = 100, both check "100 >= 50 ✓", both insert a -50 ledger entry, and the user has bet 100 with a balance of 100. Or worse: balance ends at -50 because the second update wrote `balance = 100 - 50` after the first one committed.

**Why it happens:**
- Naive `read balance → check → update balance` pattern in application code
- SQLAlchemy default `READ COMMITTED` doesn't lock rows on `SELECT`
- Async FastAPI handlers compound the problem (multiple coroutines hit the wallet row simultaneously)
- Developer tests with one request and assumes it works

**How to avoid:**
- Inside a single DB transaction: `SELECT balance FROM wallets WHERE user_id = ? FOR UPDATE` then check, then `INSERT INTO ledger_entries (...)`, then `UPDATE wallets SET balance = balance - ? WHERE user_id = ?` — all in one commit
- Use **double-entry ledger** as the source of truth, materialize `balance` either via trigger or by computing `SUM(amount)` from the ledger; the `wallets.balance` column is a cache, never the truth
- Enforce a `CHECK (balance >= 0)` constraint at the DB level — defense in depth so even a buggy app can't go negative
- Use `asyncpg` (native async) so the connection actually serializes properly; do NOT mix sync `psycopg2` with async session
- Acquire locks in a consistent order (always wallet then bet, never the reverse) to prevent deadlocks
- Consider `SERIALIZABLE` isolation for the bet placement transaction specifically — Postgres aborts conflicting transactions and you retry

**Warning signs:**
- "Sometimes the balance is wrong, but I can't reproduce it" — classic race
- Load tests with 50+ concurrent bets show balance drift
- `pg_stat_activity` shows `idle in transaction` rows holding locks
- Audit log SUM doesn't equal the wallet balance

**Phase to address:**
Phase that builds the wallet/ledger (likely Phase 3 or 4). Must be in place **before** any bet placement code is written.

---

### Pitfall 2: Settling on `closed` instead of `resolved` (Polymarket dispute window)

**Severity:** CRITICAL
**What goes wrong:**
The Celery polling job sees a Polymarket market with `closed: true` and triggers settlement: pays out YES holders, marks the market resolved in XPredict. Two hours later UMA disputes the outcome, the resolution flips, and XPredict has already paid the wrong side. Now you either claw back money from winners (UX disaster) or eat the loss yourself (every disputed market is a financial bug).

**Why it happens:**
- Polymarket has two distinct concepts: a market `closes` (no more trading) and then enters UMA's optimistic oracle process. A proposer posts a $750 USDC.e bond and a **~2-hour challenge window** opens. Only if undisputed (or after the dispute is resolved on-chain) does the market actually `resolve` with a final outcome
- The Gamma API exposes `closed`, `closedTime`, `resolved`, `resolutionSource`, `umaResolutionStatus` — these mean different things
- "Tail-end arbitrage" on Polymarket (prices hovering at 0.95-0.99 between close and resolution) exists precisely because the gap is real and exploitable
- Developers see `closed: true` and assume "ready to settle"

**How to avoid:**
- **Never settle on `closed`.** Settle only on a confirmed final state (e.g., resolved + outcome present + UMA confirmed)
- Add an internal cooldown: even when Polymarket says resolved, wait an extra grace period (e.g., 30 minutes after the UMA window closes) before our settlement job runs
- Store the entire resolution event payload in the audit log, including UMA proposer, dispute status, and timestamps
- Make settlement **idempotent and reversible**: a settled bet has a `settlement_id` referencing the resolution event; if the resolution event is invalidated, the system has a reversal mechanism (reverse-ledger entries, never DELETE)
- Tail strategy: for replicated Polymarket markets, our market should also be "live but unsettleable" during the dispute window — show users "Resolution pending UMA confirmation"
- Manual override: admin can pause settlement on a specific market if they see chatter about a dispute

**Warning signs:**
- Pol/Cuco says "we'll settle when the market closes" in early planning — STOP and fix the language
- Tests only cover the happy path of clean Polymarket resolution
- No code path handles "market resolved, then resolution overturned"

**Phase to address:**
Phase that implements Polymarket polling/integration AND phase that implements settlement. Both must understand the close-vs-resolve distinction.

---

### Pitfall 3: Play tokens accidentally become "gambling" under Spain's Ley 13/2011

**Severity:** CRITICAL
**What goes wrong:**
XPredict launches with "play money tokens." A well-meaning growth feature ships: referrals give 1,000 tokens, and there's a leaderboard with monthly prizes (a hoodie, a gift card, anything with monetary value). Or worse: the operator we sell to enables a "premium tier" priced in tokens, or lets users transfer tokens between accounts. Suddenly the three elements of gambling (prize + chance + consideration) are all present, and DGOJ classifies us as unlicensed gambling. Operator gets fined, we get a lawsuit, project dies.

**Why it happens:**
- The legal threshold isn't "did you accept fiat?" — it's whether tokens have **economic value** (FinCEN-style "convertible virtual currency" test, mirrored loosely in EU thinking) and whether there's any redemption mechanism, however indirect
- Even sweepstakes-model "social casinos" (Stake.us etc.) are being banned state-by-state in the US (NY: 26 operators ordered to cease; Montana SB 555; Connecticut SB 1235 — now criminal). EU is similar via national regulators
- Spain's Ley 13/2011 defines gambling as risking money/economic value on uncertain outcomes; "social games without cash prizes" are excluded — the cash-prize exclusion is the only thin line
- The platform's own intent doesn't matter — what matters is whether a court sees economic value flowing in or out
- White-label adds risk: an operator can configure XPredict to do things we never anticipated (cash prizes, token sales, redemption mechanics)

**How to avoid:**
- **Hard-code non-transferability**: tokens cannot move user-to-user, ever. No gift, no transfer, no resale market. Enforce at the DB level (FK constraint on ledger entries to a system account, with a CHECK that user-to-user is impossible)
- **No redemption path**: tokens never convert to fiat, crypto, prizes, swag, gift cards, subscriptions, or "credit" toward anything with monetary value. This is non-negotiable for play-money status
- **No purchase of tokens**: users cannot buy tokens with fiat or crypto. Tokens are granted by the system (signup bonus, daily reward, admin grant) only
- **Add a "token policy" config** that white-label operators sign before activation — explicitly listing what's prohibited (selling tokens, prize redemption, transfers). Disable these as features at the code level, not just the UI
- **Per-tenant feature flags** (looking ahead to v2): `allow_token_purchase = false` cannot be enabled without manual intervention + legal review
- **Geo-blocking**: even with play money, restrict access from jurisdictions with hostile case law (start US-restricted; the Kater v. Churchill Downs Ninth Circuit ruling held a play-token game *was* gambling under WA law)
- **Terms of service** explicit that tokens have no monetary value, cannot be redeemed, cannot be transferred, are revocable, are entertainment-only. Have a Spanish lawyer review for DGOJ posture before any operator launch
- **Avoid the word "deposit"** in the UI — say "claim free tokens" or "load play balance"; "deposit" implies real money

**Warning signs:**
- Anyone proposes "let users buy tokens with euros for the cool ones"
- Anyone proposes a leaderboard with non-trivial prizes
- Anyone proposes a referral program with cash equivalent
- Operator asks "can I let my VIPs withdraw their winnings?"
- Marketing material uses "win real prizes" / "cash out"

**Phase to address:**
Phase 0 / project setup (ToS, token policy doc) AND every phase that touches wallet, marketing features, or operator config. This is a continuous concern, not a one-time checkbox. Specifically flag the leaderboard/CRM phases.

---

### Pitfall 4: Decimal/money handled as float — rounding eats balance over time

**Severity:** HIGH
**What goes wrong:**
Code uses Python `float` or PostgreSQL `REAL`/`FLOAT8` for token balances and bet amounts. After thousands of bets, balances drift: a user who deposited 1000.00 and lost 100 bets of 0.10 each ends up at 899.9999999998. Worse, summing the ledger doesn't equal the wallet balance — your audit fails. Worst: house edge gets eaten by accumulated rounding errors invisible to admins.

**Why it happens:**
- Most fractions (0.1, 0.2, 0.3 in decimal) have no exact binary representation. `0.1 + 0.2 == 0.30000000000000004` is the classic gotcha
- SQLAlchemy default for `Float` column type maps to PostgreSQL `FLOAT8` — imprecise
- Developers used to web dev see `float` and don't think about it
- Tests with whole numbers pass; the bug surfaces only with fractional amounts in production

**How to avoid:**
- **Postgres column type: `NUMERIC(18, 4)`** (or `(20, 8)` if you want crypto-like precision) — explicit, exact, arbitrary precision. Never `FLOAT`, `REAL`, `DOUBLE PRECISION`, or `MONEY` (the `MONEY` type has locale issues)
- **Python: `from decimal import Decimal`** for every money-touching path. Construct from strings (`Decimal("0.10")`) not floats (`Decimal(0.10)` retains the binary error)
- **Pydantic models**: use `Decimal` type, set `decimal_places` and `max_digits` validation, and configure JSON encoder to serialize as string (not float) in API responses
- **Alternative**: store as integer milli-tokens or micro-tokens (multiply everything by 1000 or 1,000,000) and only convert to decimal for display. Simpler, faster, but commits to a precision level
- **Round explicitly with a documented mode** (e.g., `ROUND_HALF_EVEN` aka banker's rounding) at the point of display only — never in business logic
- **Invariant check job**: nightly Celery task that verifies `SUM(ledger.amount) == wallet.balance` for every user; alert if it diverges by even 1 unit

**Warning signs:**
- `Decimal` not imported in any wallet/ledger module
- SQLAlchemy column types are `Float`, `Numeric` without `precision=` and `scale=`, or `MONEY`
- Comparisons like `if balance == amount` (use Decimal compare, not float equality)
- Tests pass with whole numbers but no test uses fractional amounts

**Phase to address:**
Phase that designs the DB schema (foundational). Must be locked in before any bet/wallet code is written. Bake into a coding standard.

---

### Pitfall 5: Settlement is not idempotent — re-running pays out twice

**Severity:** CRITICAL
**What goes wrong:**
The Celery settlement task runs for market X. It crashes after paying out 50 of 100 winning bets. The task is retried (Celery's at-least-once delivery). It runs again, pays out *all* 100 winners — including the 50 already paid. House loses half its float in one bug.

**Why it happens:**
- Celery delivers at-least-once: tasks WILL run twice, especially during deploys, crashes, or worker timeouts
- Naive task code: `SELECT bets WHERE market_id = ? AND outcome = winner` → pay each one
- No record of "this bet has been settled" until the payout commits, so retries don't know what's already done
- `acks_late=True` combined with retries makes the problem worse

**How to avoid:**
- **Mark each bet `settled_at` and `settlement_id`** in the same transaction as the ledger insert. The settlement query MUST filter `WHERE settled_at IS NULL`
- **Idempotency key** on every state-changing API/task: `(bet_id, settlement_event_id)` as a unique constraint on the ledger entry. Second insert raises `UniqueViolation`, task knows it already ran
- **Use `celery-once` or `celery-singleton`** for the settlement task with a Redis lock keyed on `market_id` — prevents concurrent execution
- **Idempotent task design**: the function should be safe to call N times with the same arguments. Check the world state ("is this bet settled?") before acting, not just rely on "did I send the message?"
- **Audit table for each settlement run**: `settlement_runs(id, market_id, started_at, completed_at, status, bets_settled)` — admin can see "this market was settled at T, by run R, paying N bets"
- **NEVER use DELETE or UPDATE-in-place on the ledger**. Reversals are new entries with `is_reversal = true` and a `reverses_entry_id` FK

**Warning signs:**
- Settlement task has no `WHERE settled_at IS NULL`
- No unique constraint scoping ledger entries to bet + event type
- "We'll handle retries later" in planning
- Single test of settlement happy path, no test of "what if it runs twice"

**Phase to address:**
Phase that implements market settlement (likely co-located with Polymarket integration and house resolution). Idempotency tests are a verification gate.

---

### Pitfall 6: Human resolver of house markets has no audit trail or rollback

**Severity:** HIGH
**What goes wrong:**
Admin Pol resolves a house market "Will Real Madrid win La Liga?" as YES at 22:00. Five minutes later, news breaks that the league was awarded due to a technicality — actually a draw playoff. Pol wants to reverse. Without an audit log of the resolution event, who clicked it, what they saw, what the system showed at the time, there's no clean reversal path. Users who already got paid demand to keep the money. Users who didn't get paid demand they should have. Trust dies.

**Why it happens:**
- Manual resolution feels simple ("admin clicks YES, system pays out") so it's built without ceremony
- No mental model that human + ambiguous outcome = dispute risk inherited from prediction-market domain
- Resolver bias is real (admin bets on house markets — even if banned by policy, it leaks)
- No documentation of resolution criteria when the market was created

**How to avoid:**
- **Resolution criteria locked at market creation**: when admin creates a house market, they must write the resolution criteria (the source of truth, the date by which it resolves, what happens if ambiguous). Display this to users. Cannot be edited after first bet is placed
- **Two-step resolve with confirmation**: admin proposes outcome → 1 hour grace period (or shorter for clear outcomes) → admin or a second admin confirms → settlement runs. Mirrors UMA's two-step optimistic flow
- **Full audit of resolution event**: `(market_id, proposer_user_id, proposed_outcome, proposed_at, confirmer_user_id, confirmed_at, evidence_text, evidence_url)` — every field mandatory. Stored in the immutable audit log
- **Reversal mechanism**: admin can issue a reversal event that creates reverse-ledger entries for every payout. Mark the original resolution as `reversed_by_event_id`. NEVER edit or delete the original event
- **Self-betting ban for admins**: enforce at DB level via constraint or trigger (Kalshi suspended a U.S. Senator for self-betting; this is a real risk). At minimum, log all admin bets in a separate visible audit
- **Resolution policy document**: criteria for "ambiguous" — what triggers manual review, what auto-resolves
- **Time-zone discipline**: resolution dates stored as `TIMESTAMPTZ` only, never `TIMESTAMP`. A market "resolving on 2026-05-25" must specify the moment (start of day in which TZ?)

**Warning signs:**
- House market creation flow doesn't capture resolution criteria
- Admin UI has a "resolve" button with no confirmation step
- No `audit_events` or similar immutable table
- "We'll trust Pol" as the security model

**Phase to address:**
Phase that builds admin/CRM for house markets. Must coexist with audit-log foundation phase.

---

### Pitfall 7: Connection pool contamination leaks data across users (and tenants in v2)

**Severity:** HIGH (single-tenant) / CRITICAL (multi-tenant v2)
**What goes wrong:**
PgBouncer or asyncpg's pool reuses a DB connection. Connection A served user 1's request and set `SET LOCAL app.user_id = 1`. The connection is returned to the pool. Connection B picks it up for user 2's request. `SET LOCAL` cleared with the transaction — but if the app used `SET app.user_id` (session-level) instead, or used pgBouncer in transaction-pooling mode while the app expected session-pooling, the next user sees the previous user's context. In multi-tenant: tenant 2 sees tenant 1's data.

**Why it happens:**
- Async + connection pools + Postgres session state interact in subtle ways
- Developers use `SET app.tenant_id = ...` once at connection acquisition, assume it stays
- PgBouncer transaction pooling mode (recommended for performance) breaks any session-level state
- RLS policies with `current_setting('app.user_id')` are silently bypassed when the setting is empty (RLS defaults to "no rows" if the policy expression is false, but if the developer wrote a permissive default, they get data leakage)

**How to avoid:**
- **Always use `SET LOCAL`**, never `SET` — limits scope to the current transaction
- **Connection acquisition middleware**: at the start of every request, in a transaction, set `app.user_id` and (eventually) `app.tenant_id`. Verify it's set before any query
- **PgBouncer mode discipline**: pick transaction or session pooling explicitly and document it. Asyncpg's pool is session-pooling by default, which is safer but more resource-intensive
- **RLS policies must FAIL CLOSED**: write policies as `USING (user_id = current_setting('app.user_id')::int)` and ensure `current_setting` raises if missing (`current_setting('app.user_id', false)` with `missing_ok = false`)
- **Connection reset on return**: if using PgBouncer with `server_reset_query`, set it to `DISCARD ALL`
- **For v2 multi-tenant**: enable `FORCE ROW LEVEL SECURITY` on every table; the table owner doesn't bypass RLS this way. Reference CVE-2024-10976 and CVE-2025-8713 — even correct RLS has had bugs
- **Test for it**: integration test that runs two concurrent requests as different users and verifies no cross-contamination

**Warning signs:**
- Code reads `SET app.user_id` (no LOCAL)
- No explicit decision about pooling mode
- RLS implemented but no test that proves it can't be bypassed
- "It works in dev" but dev uses one connection

**Phase to address:**
Phase that establishes the FastAPI + SQLAlchemy + DB connection layer (foundational). Multi-tenant migration phase (v2) revisits this.

---

### Pitfall 8: JWT-only auth with no revocation, refresh, or rotation

**Severity:** HIGH
**What goes wrong:**
User logs out — token still valid until expiry. User's laptop is stolen — attacker has hours. Password reset — old tokens still work. Admin bans a user — they still have a valid JWT for 24 hours. Refresh tokens are stored in localStorage where XSS reads them.

**Why it happens:**
- Tutorials present JWT as "stateless, no DB lookup needed" — true, but the cost is no revocation
- Developers skip refresh tokens or skip rotation because "it's just for a demo"
- HS256 secret is shared with frontend or committed accidentally
- Long-lived access tokens (24h) because "I don't want to deal with refresh"

**How to avoid:**
- **Hybrid pattern**: short-lived access JWT (15 minutes) + long-lived refresh token stored server-side (`refresh_tokens` table with `(token_hash, user_id, expires_at, revoked_at, rotated_to_id)`)
- **Refresh token rotation**: every use issues a new refresh token and revokes the old. If a revoked token is presented, **revoke the entire session family** (token reuse = stolen)
- **Tokens in HTTP-only, Secure, SameSite=Lax cookies** — never localStorage (XSS-readable)
- **Revocation list / token version**: store `token_version` per user; ban-user bumps it; access tokens carry their version; check on validate. Stateless-ish, cheap, allows instant kill
- **Password reset tokens**: single-use, expire in 15 minutes, stored as hashed value in DB, deleted after use. Reset MUST invalidate all existing sessions (bump `token_version`)
- **Email enumeration prevention**: forgot-password endpoint returns 200 OK whether the email exists or not. Same for login: always "invalid credentials," never "user not found"
- **HS256 secret**: 32+ random bytes, from env var (`SECRET_KEY` loaded via Pydantic `BaseSettings`), never committed. Distinct secret for refresh vs access. Rotate-able (keep `kid` claim and support old keys for grace period)
- **Argon2id over bcrypt** for password hashing: 64MB memory, 3 iterations, 1 thread (OWASP 2026). Bcrypt's 72-byte silent password truncation is a real footgun
- **Rate-limit auth endpoints**: SlowAPI or fastapi-limiter with Redis storage. Login: 5 attempts per IP per minute, exponential lockout after 5 failures per user. Password reset: 3 per IP per hour, 1 per email per 5 minutes. Registration: 5 per IP per hour

**Warning signs:**
- `fastapi-users` config uses `JWTStrategy` only, no refresh
- No `refresh_tokens` table in schema
- `SECRET_KEY` is hardcoded or "changeme" anywhere in the repo
- No rate-limit decorator on `/auth/login`
- Tokens stored in localStorage in the Next.js frontend

**Phase to address:**
Phase that builds auth (likely Phase 2 or 3). Set the pattern correctly first time — auth is hard to retrofit.

---

### Pitfall 9: Polymarket polling burns rate limit and goes stale

**Severity:** HIGH
**What goes wrong:**
Naive Celery beat task polls `GET /markets` every 5 seconds for all 25 markets, individually. Burns through the 300 req/10s `/markets` limit in seconds, gets throttled or 429'd, polling silently degrades. Frontend shows stale prices. Bets are placed against odds that are 3 minutes old. House loses money or users lose trust.

**Why it happens:**
- Polymarket Gamma API has tiered limits: 4,000/10s general, **300/10s on `/markets`, 500/10s on `/events`, 350/10s on search**. Cloudflare throttles (delays, then 429s) over the limit
- Developer treats Polymarket as infinite-bandwidth, polls aggressively
- No exponential backoff on 429, no jitter, no respect for `Retry-After`
- WebSocket API (real-time) exists but isn't used because "REST is simpler"

**How to avoid:**
- **Batch reads**: `GET /markets?ids=1,2,3,...` (or the bulk endpoint) instead of N requests. One request gets all 25 markets
- **Polling cadence math**: 25 markets, fetch all in 1 request every 10 seconds = 1 req/10s = 0.3% of `/markets` limit. Plenty of headroom for retries
- **Use WebSocket for hot markets** — eliminates polling pressure entirely for the most-active subset
- **Exponential backoff with jitter** on retries: 1s, 2s, 4s, 8s, ... capped at 60s, ±20% jitter. Use `tenacity` library
- **Respect `Retry-After` header** if returned; check Cloudflare response headers
- **Single-flight via Celery distributed lock** (`celery-once`/Redis): only one poller runs at a time. Avoid two beat schedulers (e.g., during deploy overlap) double-polling
- **Latency monitoring as throttle warning**: if response time spikes 3x baseline, you're being throttled before you hit 429. Add Prometheus histogram + alert
- **Cache last-known prices in Redis** with a freshness timestamp. UI shows "Updated 4s ago" — explicit staleness is fine; silent staleness is not
- **Schema evolution**: pin the version (Gamma is currently unversioned via URL but evolving). Validate response with Pydantic and log unknown fields. Be ready for breaking changes — they ship without notice
- **`closed` defaults**: note that Polymarket recently changed `closed` to default `false` (i.e., closed markets excluded by default). Set the parameter explicitly to make your intent obvious

**Warning signs:**
- Celery beat schedule has `interval: 5s` or shorter on a Polymarket task
- No `tenacity` or equivalent retry decorator
- No Redis cache for prices
- No metric for Polymarket API latency or error rate

**Phase to address:**
Phase that implements Polymarket integration. Must include monitoring/alerting from day one.

---

### Pitfall 10: No transaction boundary between bet placement and ledger insert

**Severity:** CRITICAL
**What goes wrong:**
Bet is inserted, then the ledger debit fails (DB hiccup, constraint violation, network blip). Now there's a bet without a ledger entry — user "owes" the system but has the bet. Or the inverse: ledger debited but bet insert fails — user paid for nothing. The ledger and the operational state diverge.

**Why it happens:**
- Two-step operations split across two transactions ("commit the bet, then commit the ledger")
- Bet placement and ledger update done in two separate API calls (frontend-driven)
- Sagas / event-driven architecture used prematurely without compensating actions

**How to avoid:**
- **One transaction per bet placement**: open transaction, lock wallet row, check balance, insert bet, insert ledger debit, update wallet cache, commit. All or nothing
- **DB constraint as truth**: `bets.id` is referenced by `ledger_entries.bet_id` (FK) — orphaned bet impossible
- **Outbox pattern for downstream effects**: if placing a bet must notify another system, write the notification to an `outbox` table in the same transaction; a separate worker drains it. Never call external APIs inside the bet transaction
- **Repository pattern**: a single `place_bet(user, market, side, amount)` function owns the entire transaction. No exposing pieces to the API layer
- **Tests**: explicit test that simulates DB failure mid-transaction and verifies neither side committed

**Warning signs:**
- Two `commit()` calls in one logical operation
- Bet creation endpoint and "deduct balance" endpoint are separate API routes called by the frontend
- "We use Saga pattern" without compensating-action logic implemented

**Phase to address:**
Phase that builds bet placement. Co-located with wallet/ledger phase.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems. **All "MVP" entries must have a phase scheduled to remove them.**

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Skip `tenant_id` columns (single-tenant v1) | Faster schema, fewer joins | Multi-tenant v2 requires schema migration across every table + data backfill — could be a multi-month project | NEVER for new tables. Decision: add `tenant_id` columns from day 1, populated with `1` for single-tenant; ignore at query layer until v2. Pol explicitly accepted this risk in PROJECT.md — write it down again here |
| Store `SECRET_KEY` in `.env.example` with a placeholder | Easy local dev | Someone copies `.env.example` to `.env` and ships placeholder secret to prod | NEVER. Generate unique secrets per environment. Use a `secrets-check` script in pre-commit hook |
| Settle bets synchronously on market close (no dispute window) | Simple, fast UX | Catastrophic on first overturned resolution | NEVER for Polymarket-sourced markets. Acceptable for house markets WHERE admin has confirmed outcome and our policy explicitly says no dispute |
| Use float for play money "because it's just demo" | Faster prototyping | Rounding drift accumulates; sums don't match; debugging hell | NEVER. Decimal from day 1. Trivial code change, zero runtime cost |
| Skip rate limiting in dev/staging | Faster local testing | Production launch is the first time rate limits are tested = guaranteed incident | OK to skip in dev only if config differs from prod and is loud about it. Staging MUST mirror prod |
| Single admin user without RBAC | Faster to ship CRM | Adding a second admin role requires retroactive permission checks across all admin endpoints | NEVER. Even v1 should have `is_admin: bool` flag + `@admin_required` decorator. RBAC roles later |
| Skip audit log because "Postgres has timestamps" | Saves a table | Cannot answer "who resolved this market?" or "why does balance not match?" | NEVER for money-touching operations. Acceptable for read-only data |
| Hardcode operator branding in frontend code | Demo looks polished fast | Every new operator = code fork or feature branch hell | OK for first demo IF code is in a `theme.config.ts` that gets swapped, not scattered across components. Make it data-driven before second operator |
| Mock Polymarket in tests by hardcoding responses | Fast tests | Tests pass forever after Polymarket changes their API | OK for unit tests of business logic. Contract tests must hit real (or recorded VCR) Polymarket responses on CI weekly |
| Long-lived JWT (24h) with no refresh | Skip refresh token complexity | Cannot revoke, must build refresh later under pressure | NEVER. Refresh tokens are not optional for production-grade auth |
| Disable HTTPS in dev | Easy local debugging | First HTTPS-only bug surfaces in prod (cookies, CORS, secure flags) | OK with explicit `Settings.is_dev=True` gate. Staging and prod always HTTPS-only |

---

## Integration Gotchas

Common mistakes when connecting to external services.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| **Polymarket Gamma API — `closed` vs `resolved`** | Treating `closed: true` as "ready to settle" | Settle only when fully resolved (UMA confirmed + post-window grace period). Store both `closed_at` and `resolved_at` in our DB and never settle on `closed_at` |
| **Polymarket Gamma API — rate limits** | One request per market, hitting 300/10s on `/markets` | Batch via `ids=` query param. Cache in Redis. Use WebSocket for real-time hot markets |
| **Polymarket Gamma API — schema drift** | Pydantic model with `extra='ignore'`, silent acceptance of changes | `extra='forbid'` in dev/staging to catch new fields; `extra='allow'` + warning log in prod. Contract test on CI |
| **Polymarket — UMA dispute resolution** | Assuming the proposed outcome is final | Wait for the dispute window (~2h) PLUS our internal cooldown before settlement. Be ready to reverse if overturned |
| **Polymarket — outcome data semantics** | Assuming "Yes" is always index 0, "No" is index 1 | Use the `outcomes` array order from the API verbatim. Some markets have N outcomes; some have unusual labels |
| **Polymarket — timezones and timestamps** | Assuming UTC, treating strings as comparable | All Polymarket times are UTC ISO 8601; parse explicitly with `datetime.fromisoformat` and store as `TIMESTAMPTZ` |
| **Polymarket — closed-but-still-fetched markets** | Replaying old markets because the API still returns them | Filter by `closed` and `active` parameters explicitly. Track which markets we replicate in our DB; do not blindly mirror |
| **Polymarket — pagination** | Forgetting to follow `has_more` / not handling `offset` | Loop until `has_more=false`. Always provide explicit `limit` (don't rely on default) |
| **Email provider (transactional)** | Hardcoding sender domain, no SPF/DKIM/DMARC | Use a service (Resend, Postmark, SES); configure DNS records before launch; have a verified-domain check at startup |
| **Stripe (future, when fiat enabled)** | Skipping webhook signature verification | Webhooks MUST verify `Stripe-Signature`; idempotency keys on all payment-intent creates; never trust the client's claim of "I paid" |
| **Redis as broker AND cache** | Sharing a single instance for Celery + cache + sessions | Separate DBs (Redis supports 16 databases via `DB 0`, `DB 1`, etc.) OR separate instances. Celery losing the broker means losing tasks |
| **PgBouncer in front of Postgres** | Session-level features (advisory locks, `LISTEN/NOTIFY`, prepared statements) break silently in transaction pooling | Pick a pooling mode and document it. Asyncpg has its own pool — adding PgBouncer is often unnecessary at our scale |

---

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| **Leaderboard query scans entire ledger** | P95 of `/leaderboard` grows linearly; DB CPU spikes when leaderboard is hit | Materialized view refreshed every N seconds, OR Redis sorted set updated on every settlement, OR `user_stats` denormalized table updated via trigger | ~10k users + ~100k bets |
| **N+1 queries fetching markets with prices** | API response time > 1s on `/markets` | `joinedload` / `selectinload` in SQLAlchemy. Always profile with `EXPLAIN ANALYZE` | Any non-trivial catalog |
| **No DB indexes on hot paths** | Sequential scans on `bets WHERE user_id = ?`, `ledger WHERE wallet_id = ?` | Index every FK and every WHERE-clause column. Composite indexes for multi-column filters. Use `pg_stat_user_indexes` to detect unused indexes too | Immediate (10k rows) |
| **Async code that blocks the event loop** | Latency spikes, throughput plateau at low req/s | `asyncpg` driver (not `psycopg2`); never call sync I/O inside an async handler; `httpx.AsyncClient` not `requests` | ~50 concurrent users |
| **All caching via Postgres** | Postgres CPU at 80% during peak | Redis cache for hot reads (market list, leaderboard, session state). Cache invalidation tied to ledger commits | ~1k req/min |
| **Polling Polymarket too often** | Stale data anyway (because rate-limited) + 429s in logs | Cache + batch + WebSocket for hot markets | Day 1 if naive |
| **Real-time price updates via polling from frontend** | Frontend hammers `/markets` every 2 seconds × N users | WebSocket or Server-Sent Events for price stream; REST only for the initial load | ~50 concurrent users on the catalog |
| **Audit log table without partitioning** | Queries slow down as table grows; vacuum takes forever | `PARTITION BY RANGE (created_at)` on monthly partitions once the table is in place. Easier to add early than retrofit | ~10M rows |
| **Synchronous email sending in request handler** | Login takes 2s because SMTP is slow | Email via Celery task always. Even welcome emails | Immediate |
| **No connection pool limits in SQLAlchemy** | Postgres `max_connections` exhausted, app errors out | `pool_size=20`, `max_overflow=10`, `pool_recycle=300` baseline. Scale per worker count | Concurrent request burst |
| **Single Celery worker, all tasks one queue** | One slow task (Polymarket polling 429-retry-loop) blocks settlement task | Separate queues per concern: `polymarket`, `settlement`, `notifications`. Multiple workers, prioritized | Day of a market resolution event |

---

## Security Mistakes

Domain-specific security issues beyond general web security.

| Mistake | Risk | Prevention |
|---------|------|------------|
| **Admin can resolve any market regardless of role** | Compromised admin account drains house | Multi-step resolution with two distinct admins (proposer + confirmer) for any market over a threshold. Audit log all admin actions |
| **No "self-bet" prevention for admins** | Insider trading; legal liability (Kalshi suspended Senator Klein, real precedent) | DB constraint: `bets.user_id != markets.created_by_user_id` for house markets. Logged exception: admin bets visible in audit |
| **Bet history is readable by other users** | Privacy violation; competitors can copy your strategy | Authorization on every read: `GET /users/{id}/bets` requires `user_id == current_user.id` OR admin. Default-deny |
| **Password reset token has long TTL or is single-use only via comment** | Stolen email = account takeover | 15-minute TTL, single-use enforced at DB level (UNIQUE constraint + delete-after-use), token is hashed in DB (never store raw token) |
| **CORS configured with `*` "for development"** | Any site can call our API with credentials | Explicit origin list per environment. Production: only our frontend domain. Never `*` with `credentials: true` |
| **No CSRF protection on cookie-auth endpoints** | Cross-site requests place bets on behalf of users | If using cookie sessions: `SameSite=Lax` minimum, ideally CSRF token on state-changing requests. If JWT in Authorization header: less risk but still protect mutating endpoints |
| **Polymarket data is trusted blindly** | Compromised or spoofed response settles markets wrongly | TLS verification on (default); validate response with Pydantic; sanity-check outcome prices are 0-1; sanity-check resolution events are signed/sourced from Polymarket's expected domain. Polymarket itself can be wrong — our settlement is downstream of theirs and we accept that risk |
| **Email enumeration via registration / forgot-password** | Attackers harvest valid email list | Generic responses. "If an account exists, you'll get an email." Same response time (rate-limit timing attacks too) |
| **Sensitive data in logs** | Logs leaked = passwords/tokens leaked | Log filter that scrubs `password`, `token`, `secret`, `authorization` keys. Sentry/log shipper config includes scrubbing. Never log full request bodies for auth endpoints |
| **No rate limit on bet placement** | Single user spams thousands of bets per second, possibly exploiting a race window | Rate limit per-user per-market: e.g., 10 bets per minute per market per user. Stricter for new accounts |
| **Token in URL** (e.g., password reset, magic link) | Token leaks to logs, referer headers, server access logs | Tokens in URL must be single-use AND short-lived AND scrubbed from server access logs |
| **Admin auth same path as user auth** | Admin endpoint discoverable; brute-force surface area | Separate admin login endpoint, optional 2FA requirement, IP allowlist via env var for v1 demo, full 2FA for v2 |
| **No 2FA option for users** | Account takeover from password reuse | TOTP support (2FA via authenticator app). MVP-acceptable to defer, but design the schema to support it from day 1 |

---

## UX Pitfalls (Trust Issues)

Common user experience mistakes in this domain. Trust is the entire product in betting — these are not cosmetic.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| **Odds change after user clicks "Place Bet"** | User feels cheated, distrust | Lock-in the odds shown at click time; reject the bet if true odds have moved more than X bps and re-prompt. Better: optimistic UX — accept the bet at displayed price within tolerance |
| **No "what happens on settlement" explanation** | User confused about payout, especially if odds moved | Show "If YES wins, you receive: Z tokens (currently X% chance)" calculator on the bet form. Show "Resolves on DATE based on SOURCE" |
| **Resolution criteria hidden** | User loses, claims market was "unfair" | Resolution criteria visible from market detail page. Persistent. Cannot be edited after first bet |
| **Slow settlement after market resolves** | "I won, where's my payout?" | Settle within minutes of resolution event being confirmed; show "Settlement pending" status with ETA. Push notification when settled |
| **No "my bets" history with P&L** | User feels disconnected from past activity | Bet history with: stake, odds at placement, outcome, payout, P&L per bet. Sortable, filterable. Total lifetime P&L visible |
| **Withdrawal/refund delays without explanation** (relevant later when real money) | Massive trust killer; the #1 complaint on every betting platform | Clear timelines, status updates, no "manual review" without reason |
| **Hidden house edge / opaque pricing** | Users feel exploited | Display explicit fees if any. Polymarket-style: "Price 0.65 means 65% implied probability" — be transparent that pricing IS probability |
| **"You may have won" notifications that don't settle** | Trust erodes on every false hope | Show "Pending UMA confirmation" / "Pending resolution" not "You won!" until settled |
| **Generic "transaction failed" error on bet placement** | User panics: "Did my money disappear?" | Specific errors: "Insufficient balance" / "Market closed" / "Network error, please retry — your balance was not charged" |
| **No way to see who resolved a market** | Suspicion that admin manipulates outcomes | Show resolution metadata: resolved at TIME by SYSTEM/ADMIN_USERNAME, source URL, evidence text |
| **Token balance not real-time after a bet** | User thinks bet failed because balance display didn't update | Optimistic UI update on bet success; server confirms via WS or polling within 2s |
| **No daily/weekly stake limit, no responsible-play tools** | Even with play money, this looks like a casino without guardrails (and DGOJ now requires risk-detection mechanisms by Royal Decree 176/2023 for real-money) | Add self-imposed limits, session-time warnings, "you've placed 50 bets today" prompts. Sets the tone, prepares for real-money pivot |
| **Mobile experience as afterthought** | Most prediction-market traffic is mobile | Next.js + responsive design from day 1; test on actual phones, not just devtools |

---

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces. **Use during phase verification.**

- [ ] **Wallet / Ledger:** Verify SUM of ledger entries equals wallet.balance for every user — run on every CI build with seed data
- [ ] **Wallet / Ledger:** Verify `CHECK (balance >= 0)` exists as a DB constraint, not just app-level
- [ ] **Wallet / Ledger:** Verify all money columns are `NUMERIC(p, s)`, not float or money
- [ ] **Bet placement:** Run a concurrent test (e.g., locust, 50 concurrent bets per user with insufficient balance for all) and verify no balance goes negative
- [ ] **Bet placement:** Verify bet + ledger are in one transaction (kill the DB mid-bet; verify nothing committed)
- [ ] **Settlement:** Run the same settlement twice and verify idempotent (no double payouts)
- [ ] **Settlement:** Verify reversal path exists for overturned Polymarket resolutions and for incorrect house resolutions
- [ ] **Polymarket integration:** Schema-validate all incoming responses; log unknown fields; do not silently accept
- [ ] **Polymarket integration:** Settle only on confirmed resolved state, NOT `closed: true`
- [ ] **Polymarket integration:** Rate-limit handling tested — synthetically 429 the client and verify backoff works
- [ ] **Auth:** Verify password reset invalidates all existing sessions (token_version bump)
- [ ] **Auth:** Verify logout actually revokes the refresh token in DB
- [ ] **Auth:** Verify rate limit on login (try 100 wrong passwords; verify lockout kicks in)
- [ ] **Auth:** Email enumeration check — registration and forgot-password return same response for existing/non-existing email
- [ ] **Audit log:** Verify audit table is append-only at DB level (revoke UPDATE/DELETE; use stored procedure for inserts)
- [ ] **Audit log:** Every state-changing operation has an audit event entry — grep code for missing `audit_log.write(...)` calls
- [ ] **Admin resolution:** Two-step confirm flow works; resolution criteria locked at market creation
- [ ] **Admin actions:** Every admin endpoint requires `is_admin` AND logs to audit
- [ ] **Self-bet ban:** Admin cannot bet on a market they created (DB constraint or trigger, not just UI)
- [ ] **CORS:** Verify production CORS does not include `*` or dev origins
- [ ] **Secrets:** Run `gitleaks` or equivalent on the repo. Verify `.env.local` is gitignored
- [ ] **Tenant scoping (v1 forward-compat):** Verify every table has `tenant_id` column even if always `1`
- [ ] **Branding:** Verify operator config is loaded from data, not hardcoded; logo / palette swap works without code change
- [ ] **Observability:** Verify Sentry captures backend errors AND frontend errors; alert on >X errors/min
- [ ] **Observability:** Verify Postgres metrics exposed (queries, connection count, slow query log)
- [ ] **Backups:** Run a backup, drop a table, restore from backup, verify data integrity — actually do this, not just configure it
- [ ] **Backups:** PITR (point-in-time recovery) tested with WAL archiving
- [ ] **Monitoring:** Alert on settlement task failures, on Polymarket API error rate, on auth failure spike, on balance/ledger drift
- [ ] **Decimal precision:** Verify all API responses serialize Decimal as string, not float
- [ ] **Timezones:** Verify all timestamps in DB are `TIMESTAMPTZ`; frontend renders in user's local TZ
- [ ] **Regulatory:** ToS forbids token transfer, redemption, monetary value; legal review completed for Spain; geo-blocking configured if needed
- [ ] **Demo trap check:** Run a "production migration" dry run — change every env var, secret, hostname, DB connection — verify nothing breaks. Catches hardcoded dev URLs

---

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| **Wallet balance drift (ledger ≠ balance)** | LOW (if caught early) / HIGH (if user-facing for days) | Reconcile script: for each user, recompute balance from `SUM(ledger.amount)`, compare to `wallets.balance`, write an audit event explaining the correction, update balance. Notify users only if material |
| **Double payout from non-idempotent settlement** | HIGH | Write reverse ledger entries marked `(is_reversal=true, reverses_entry_id=X)` for the duplicate payouts. Communicate to affected users (transparent). Add the missing idempotency guard. Postmortem |
| **Polymarket resolution overturned after we settled** | MEDIUM-HIGH | Reverse settlements: reverse ledger entries for all paid bets, re-settle to the new outcome. Audit event explaining the chain. User communication: "Polymarket's UMA Oracle changed this outcome; we've adjusted." Have policy doc in advance |
| **Race condition allowed double-spend** | MEDIUM | Forensic: query audit log to find affected bets. Reverse the excess bet (it should never have been placed). User communication. Fix the lock |
| **Polymarket API breaking change** | LOW (if monitored) / MEDIUM (if mass failure) | Switch to cached prices; mark markets as "data source temporarily unavailable" (don't fail loudly); fix the schema; redeploy. Pin a known-good response format with VCR |
| **Auth token leaked** | MEDIUM | Bump `token_version` for affected users (instant kill). Force password reset. Investigate source (logs, vulnerabilities, frontend XSS) |
| **Admin resolution error** | LOW (with reversal path) / HIGH (without) | Reverse via admin reversal flow (creates compensating ledger entries). New audit event chained to the original. Communicate to affected users |
| **DB corruption / data loss** | HIGH | PITR restore from WAL archive to last clean state. Replay user actions from audit log if log is intact. This is why audit log lives in a separate logical place from operational tables |
| **Multi-tenant data leak (v2)** | CRITICAL | Take down the leaky surface immediately. Reset all sessions. Forensic on what was exposed. Notify affected tenants. GDPR-mandatory in EU within 72h |
| **Float precision drift caught after months** | MEDIUM-HIGH | One-time migration to Decimal: snapshot balances, recompute from ledger as Decimal, write correction events. Same script can be used for ongoing reconciliation |
| **Settlement stuck (Celery worker crashed mid-task)** | LOW | Idempotent task = just re-trigger. Worker visibility timeout + retry handles this if configured. Verify on staging |

---

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls. **This is the most important table for the roadmap builder.**

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| **#1 Wallet race conditions** | Phase that designs DB schema + Phase that implements wallet/ledger (foundational, very early) | Concurrent bet placement test; `CHECK (balance >= 0)` constraint exists; row-level locking in code reviewed |
| **#2 Settling on `closed` vs `resolved`** | Phase that implements Polymarket polling + Phase that implements settlement | Test simulates resolution + dispute + overturn; settlement only fires on confirmed `resolved` event |
| **#3 Regulatory line — play money becomes gambling** | Phase 0 (project setup, ToS) + every phase touching wallet/marketing/operator-config | ToS reviewed by lawyer; transfer/redeem endpoints don't exist (negative test); operator config has no flags that enable real-money features without legal review |
| **#4 Float instead of Decimal** | Phase that designs DB schema (foundational) | Schema audit: every money column is `NUMERIC(p,s)`; coding standard documented; CI lints float comparisons |
| **#5 Non-idempotent settlement** | Phase that implements settlement | Test runs settlement twice; verifies no double payout. Unique constraint scoped to (bet_id, event_type) on ledger entries |
| **#6 Manual resolution no audit / no rollback** | Phase that builds admin CRM for house markets | Resolution flow has two-step confirm; audit event has all required fields; reversal path tested |
| **#7 Connection pool contamination** | Phase that establishes FastAPI + SQLAlchemy + DB layer (foundational) | `SET LOCAL` not `SET` in code; RLS test with two concurrent users verifies isolation; pooling mode documented |
| **#8 JWT-only auth, no revocation** | Phase that builds auth | Refresh token table exists; logout invalidates token in DB; password reset bumps token_version |
| **#9 Polymarket polling cadence / rate limits** | Phase that implements Polymarket integration | Batch endpoint used; tenacity backoff implemented; Redis cache hit-rate metric exists; latency alert configured |
| **#10 No transaction boundary bet + ledger** | Phase that builds bet placement | Single-transaction implementation reviewed; kill-DB-mid-transaction test verifies atomicity |
| **Demo trap: hardcoded config** | Phase 0 (project bootstrap) — set the pattern | All config via Pydantic `BaseSettings`; no hostnames/keys in code; `.env.example` differs from `.env.local`; `gitleaks` in CI |
| **Demo trap: branding hardcoded** | Phase that builds frontend foundation | Theme config is a data file, not scattered constants; logo loaded from runtime config |
| **Demo trap: single tenant_id assumption** | Phase that designs DB schema | Every table has `tenant_id` column from day 1 |
| **Observability gaps** | Phase that establishes deployment / infra | Sentry configured frontend + backend; Prometheus exporters for Postgres + app; dashboard exists; alerts exist (not just config; tested by triggering them) |
| **Backup not tested** | Phase that establishes deployment / infra | Documented + tested restore procedure; PITR enabled; backup integrity check in CI weekly |
| **UX trust: hidden resolution criteria** | Phase that builds market display | Resolution criteria visible on market detail page; locked after first bet |
| **UX trust: settle delay communication** | Phase that builds market display + settlement | "Resolution pending" status visible; notification on settle |

---

## The Demo Trap — Production Shortcuts That Bite Later

Production shortcuts that look fine in a demo but block real launch. **This is its own section because PROJECT.md explicitly warns about it ("Por qué play money con seguridad de producción").**

### Shortcuts that are NEVER acceptable, even in demo

1. **Float for money.** Trivial to do right from day 1. There is no demo benefit to float.
2. **Hardcoded secrets in code.** A demo gets reviewed by a potential buyer's engineer; they see "SECRET = 'demo123'" in the code and the sale is over.
3. **Skipping wallet locks.** A demo with a race condition might work in a recorded video but will crater in a live demo when two test users bet at once.
4. **Settling on `closed`.** If you demo a Polymarket-resolved market and a buyer asks "what happens if it gets overturned?", "we'll fix that later" is a no-sale answer.
5. **Plaintext or weak password storage.** Argon2id from day 1. No exceptions.
6. **Auth without rate-limit on login.** A buyer's pen-tester will find this in 30 seconds.
7. **No audit log.** Buyer asks "show me the history of this bet" — if you can't, the sale is dead. Audit log is what you sell on top of "we built it like real money."

### Shortcuts that ARE acceptable in demo IF scheduled to remove

8. **Single-tenant schema (with `tenant_id` columns ghosted in).** OK per PROJECT.md decision. Scheduled removal: v2 multi-tenant phase.
9. **No 2FA on user accounts.** OK to defer if email reset is secure. Scheduled removal: v1.x or v2.
10. **No mobile app.** OK per PROJECT.md. Responsive web only. Scheduled removal: v2+.
11. **No notifications other than transactional email.** OK. Schedule: post-validation.
12. **Manual operator onboarding (no self-serve dashboard).** OK for first 1-3 operators. Schedule: phase to build operator-self-serve when N>3.
13. **Static branding via config file (not UI).** OK for first operator. Schedule: branding admin UI for second operator.
14. **Single admin (Pol).** OK as long as `is_admin: bool` flag is in DB and `@admin_required` decorator wraps endpoints. Adding more admins = data, not code.
15. **House markets only manually resolved.** OK by design per PROJECT.md. Not actually a shortcut.

### How to verify you haven't fallen into the trap

Before any "demo to operator" milestone:
- [ ] Run a `prod-migration-dry-run` script: replace every `localhost`, every dev secret, every `DEBUG=True`. Boot the stack. Place a bet. Settle. Verify nothing broke.
- [ ] Run security scan: bandit (Python), npm audit, gitleaks, OWASP ZAP against staging.
- [ ] Run the entire "Looks Done But Isn't" checklist as a gate.
- [ ] Have a non-team engineer (or AI reviewer) read the code base from cold and write down every "TODO," "FIXME," "HACK," "this is just for demo" comment they find. Triage every one of them.

---

## The Regulatory Line — When Play Money Becomes Regulated

**Severity: CRITICAL — this is an existential risk to XPredict and any operator we sell to.**

### The three-element test (Spain Ley 13/2011 + EU general principle)

Gambling under Spanish law requires all three:
1. **Prize** — something of economic value won
2. **Chance** — an outcome dependent on chance (prediction markets generally qualify, even if "skill" is involved)
3. **Consideration** — the player risks something of value

XPredict v1 is safe by **removing element 1 (no economic-value prize) and element 3 (no consideration paid)**. We must defend both.

### What keeps us safe

- Tokens are **granted by the system only** (signup bonus, daily reward, admin grant). Users never **pay** for tokens with fiat, crypto, points convertible from elsewhere, time, or attention with measurable value (no "watch this ad to earn tokens" with cash-out)
- Tokens are **non-transferable** between users. Hard constraint at DB level
- Tokens are **non-redeemable**. No path to fiat, crypto, gift cards, swag, subscriptions, prizes
- No leaderboard prizes of monetary value
- No "premium" features purchasable in tokens that have cash equivalent

### What breaks us (the "do not do" list)

| Feature | Why it's gambling | Reasoning |
|---------|-------------------|-----------|
| Sell tokens for euros | Adds consideration (element 3) | Player risks real money on chance outcome → gambling |
| Allow users to gift tokens to each other | Creates secondary market | Once a token has any external value, it's a convertible virtual currency (FinCEN test) |
| Cash prize for top leaderboard player | Adds prize (element 1) | Even if tokens didn't cost anything, the cash prize is "won via chance" |
| Branded swag prize for leaderboard winner | Same as above, gray-area | Even non-cash prizes count if they have monetary value. Some jurisdictions consider gift cards as cash equivalent |
| Allow operator to enable "buy tokens" mode | Adds consideration | Operator has activated gambling. Without DGOJ license, this is illegal in Spain |
| Allow operator to enable "redeem tokens for prizes" | Adds prize | Same |
| Token-bridge to live-bets (when integrated) | Depends on live-bets's regulatory posture | If live-bets is real-money licensed, transferring play tokens to it = "purchase of live-bets credit" = consideration. Hard line |
| Sweepstakes-model dual currency (gold coins + sweeps coins) | Marginal/illegal in many jurisdictions | US: NY banned 26 sweepstakes operators in 2025; Montana SB 555 outright banned. Don't copy this model |
| Referral bonus with cash equivalent | Marginal | Free tokens for referring are probably OK; cash for referrals to a betting platform is regulated as gambling promotion in Spain |
| Geo-fencing not enforced | Even if Spain is OK, US states (Kater v. Churchill Downs) have ruled play-token games are gambling | Default geo-block US states with hostile rulings; expand allowlist with legal review |

### Cuco's developer-facing checklist

When implementing any feature:
1. Does this feature let users move tokens between accounts? **STOP, legal review.**
2. Does this feature let users exchange tokens for anything that has monetary value? **STOP, legal review.**
3. Does this feature involve a prize the system gives based on bet outcomes? **STOP, legal review.**
4. Does this feature let an operator configure something that would change answers 1-3? **Add a feature flag locked to `False` and requires manual platform-admin enable.**

### Operator-facing checklist (before any sale)

The white-label operator signs:
1. They will not enable token purchase
2. They will not enable token redemption
3. They will not award cash or prizes based on bet outcomes
4. They will geo-fence per our recommended list
5. They will display ToS that asserts tokens have no monetary value
6. They will not advertise tokens as having monetary value
7. They will obtain DGOJ license before any "convert to real money" plan

The operator agreement is a binding part of the deal, not a "best efforts."

### Royal Decree 176/2023 / DGOJ 2025 risk-detection rules (preparing for the real-money future)

Even if v1 is play money, the Spanish DGOJ now requires risk-behavior detection mechanisms for licensed operators. Build with this in mind:
- Track time spent per session
- Track bet velocity (bets per hour)
- Track loss velocity
- Have plumbing for "intervention" messages — "you've lost 70% of today's balance, take a break"
- All of this is harmless in play money but reads as "production-ready for regulated market" to a sophisticated buyer

This is a **selling point**, not just a regulatory cost.

---

## Sources

### Polymarket / Prediction Market specifics
- [Polymarket Documentation — Gamma API Overview](https://docs.polymarket.com/developers/gamma-markets-api/overview) (HIGH — official)
- [Polymarket Help — How Are Prediction Markets Resolved](https://help.polymarket.com/en/articles/13364518-how-are-prediction-markets-resolved) (HIGH — official, 2-hour UMA challenge window confirmed)
- [AgentBets — Polymarket Rate Limits Guide March 2026](https://agentbets.ai/guides/polymarket-rate-limits-guide/) (MEDIUM — third-party, but cites exact endpoint limits)
- [Chainstack — Polymarket API for Developers](https://chainstack.com/polymarket-api-for-developers/) (MEDIUM)
- [PolyTrack — Polymarket Disputes & UMA Oracle](https://www.polytrackhq.app/blog/polymarket-resolution-disputes-uma) (MEDIUM)
- [UMA — What is a Prediction Market Dispute](https://blog.uma.xyz/articles/what-is-a-prediction-market-dispute) (HIGH — UMA official)
- [KuCoin — Polymarket V2 Ghost Fills Issue](https://www.kucoin.com/news/flash/polymarket-v2-launches-ghost-fills-addressed-but-not-fully-resolved) (MEDIUM — relevant for off-chain matching pitfalls)
- [PredictionNews — Prediction Market Resolutions: Good, Bad, Ugly](https://predictionnews.com/learn/resolutions/) (MEDIUM)
- [Polymarket Documentation — Fetching Markets](https://docs.polymarket.com/developers/gamma-markets-api/fetch-markets-guide) (HIGH)
- [Medium — Beyond Simple Arbitrage: 4 Polymarket Strategies](https://medium.com/illumination/beyond-simple-arbitrage-4-polymarket-strategies-bots-actually-profit-from-in-2026-ddacc92c5b4f) (MEDIUM — tail-end arbitrage)
- [Kalshi — DFL Senator Suspended for Self-Betting](https://abcnews.com/US/prediction-market-kalshi-suspends-3-congressional-candidates-betting/story?id=132284917) (HIGH — real precedent for insider-trading risk)

### Wallet / Ledger Correctness
- [Modern Treasury — Designing Ledgers API with Concurrency Control](https://www.moderntreasury.com/journal/designing-ledgers-with-optimistic-locking) (HIGH — production ledger system)
- [Martin Richards — Real-Time Ledger Systems: Optimistic Locking](https://www.martinrichards.me/post/ledger_p1_optimistic_locking_real_time_ledger/) (MEDIUM)
- [Finlego — Real-Time Ledger with Double-Entry](https://finlego.com/blog/designing-a-real-time-ledger-system-with-double-entry-logic) (MEDIUM)
- [Paul Gross — Ledger Implementation in PostgreSQL](https://www.pgrs.net/2025/03/24/pgledger-ledger-implementation-in-postgresql/) (MEDIUM)
- [Crunchy Data — Working with Money in Postgres](https://www.crunchydata.com/blog/working-with-money-in-postgres) (HIGH — Postgres NUMERIC for money)
- [Lightspark — Idempotency Key in Fintech](https://www.lightspark.com/glossary/idempotency-key) (MEDIUM)
- [Bytecraft / Medium — FastAPI + Celery Idempotent Tasks](https://medium.com/@hjparmar1944/fastapi-celery-work-queues-idempotent-tasks-and-retries-that-dont-duplicate-d05e820c904b) (MEDIUM)
- [Leapcell — Implementing Concurrent Control with ORM](https://leapcell.io/blog/implementing-concurrent-control-with-orm-a-deep-dive-into-pessimistic-and-optimistic-locking) (MEDIUM — SELECT FOR UPDATE patterns)
- [SQLAlchemy 2.0 — Transactions and Connection Management](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html) (HIGH — official)
- [Token Ledger — Double-Entry Token Balance Library](https://github.com/wuliwong/token_ledger) (MEDIUM — reference implementation)

### Auth / Security
- [OWASP — Argon2id 2026 Parameter Recommendations](https://guptadeepak.com/the-complete-guide-to-password-hashing-argon2-vs-bcrypt-vs-scrypt-vs-pbkdf2-2026/) (HIGH — references OWASP)
- [DevDecode — bcrypt vs Argon2 2026](https://www.devdecode.dev/blog/bcrypt-vs-argon2) (MEDIUM — includes 72-byte bcrypt truncation gotcha)
- [Medium — JWT in FastAPI: The Secure Way (Refresh Tokens Explained)](https://medium.com/@jagan_reddy/jwt-in-fastapi-the-secure-way-refresh-tokens-explained-f7d2d17b1d17) (MEDIUM)
- [OneUptime — How to Handle JWT Revocation](https://oneuptime.com/blog/post/2026-02-02-jwt-revocation/view) (MEDIUM)
- [Choudhary — Refresh Token Rotation](https://choudharycodes.medium.com/title-securing-your-web-applications-with-jwt-authentication-and-refresh-token-rotation-63a9aa1a4b12) (MEDIUM)
- [Greeden Blog — FastAPI Auth Real-World Pitfalls](https://blog.greeden.me/en/2025/10/14/a-beginners-guide-to-serious-security-design-with-fastapi-authentication-authorization-jwt-oauth2-cookie-sessions-rbac-scopes-csrf-protection-and-real-world-pitfalls/) (MEDIUM)
- [TestDriven — Securing FastAPI with JWT](https://testdriven.io/blog/fastapi-jwt-auth/) (MEDIUM)
- [Techbuddies — FastAPI Rate Limiting Implementation](https://www.techbuddies.io/2025/12/13/python-rate-limiting-for-apis-implementing-robust-throttling-in-fastapi/) (MEDIUM)
- [DEV Community — Thread-Safe Rate Limiter with FastAPI and Atomic Redis](https://dev.to/aris_georgatos/how-to-build-a-thread-safe-rate-limiter-with-fastapi-and-atomic-redis-454f) (MEDIUM)

### Multi-tenant / Data Isolation
- [Medium / InstaTunnel — Multi-Tenant Leakage: When RLS Fails in SaaS](https://medium.com/@instatunnel/multi-tenant-leakage-when-row-level-security-fails-in-saas-da25f40c788c) (HIGH — connection pool contamination, async context leaks)
- [AWS Database Blog — Multi-tenant Data Isolation with PostgreSQL RLS](https://aws.amazon.com/blogs/database/multi-tenant-data-isolation-with-postgresql-row-level-security/) (HIGH — official AWS)
- [Permit.io — Postgres RLS Implementation Guide: Best Practices, Common Pitfalls](https://www.permit.io/blog/postgres-rls-implementation-guide) (MEDIUM)
- [Clockwise — Multi-Tenant Architecture for SaaS 2026 Guide](https://clockwise.software/blog/multi-tenant-architecture/) (MEDIUM)
- [Developex — White-Label SaaS Architecture & Growth Strategy 2026](https://developex.com/blog/building-scalable-white-label-saas/) (MEDIUM)

### Regulatory
- [BOE — Ley 13/2011 de regulación del juego](https://www.boe.es/buscar/act.php?id=BOE-A-2011-9280) (HIGH — official Spanish law)
- [ICLG — Gambling Laws and Regulations Spain 2026](https://iclg.com/practice-areas/gambling-laws-and-regulations/spain) (HIGH)
- [Chambers — Gaming Law Spain 2025](https://practiceguides.chambers.com/practice-guides/gaming-law-2025/spain) (HIGH)
- [DGOJ — Dirección General de Ordenación del Juego](https://www.estafa.info/dgoj-regulacion/) (MEDIUM — explains DGOJ regulation scope)
- [Mundo Video — DGOJ 2026 Identity Check Rules](https://www.mundovideo.com.co/en/europe/spain-gambling-identity-checks-2026-new-dgoj-rules-target-fraud-and-tighten-operator-controls/) (MEDIUM — RD 176/2023 risk-detection)
- [Venable LLP — Regulatory Risks of In-Game Virtual Currency](https://www.venable.com/insights/publications/2017/05/regulatory-risks-of-ingame-and-inapp-virtual-curre) (HIGH — Kater v. Churchill Downs cited)
- [Esports Lawyers / Gilbert's LLP — Why Gambling with Virtual Currencies Isn't Legally Gambling](https://esportslawyers.ca/why-gambling-with-virtual-currencies-isnt-legally-gambling) (MEDIUM — counterpoint)
- [Fenwick — In-Game Currency Triggers State Gambling Laws](https://www.fenwick.com/insights/publications/in-game-currency-triggers-state-gambling-laws-rendering-mobile-game-illegal-gambling) (HIGH — Kater ruling)
- [Wikipedia — Virtual currency law in the United States](https://en.wikipedia.org/wiki/Virtual_currency_law_in_the_United_States) (MEDIUM)
- [Atlas Live — Sweepstakes Casinos: Loophole or Legal Liability](https://atlaslive.tech/content-hub/sweepstakes-casinos-loophole-or-legal-liability) (MEDIUM — US enforcement context)

### Performance / Operational
- [Crafyourstartup — FastAPI Performance Optimization Guide](https://craftyourstartup.com/cys-docs/fastapi-performance-optimization/) (MEDIUM)
- [Medium — Building Production-Grade Async Backend with FastAPI, SQLAlchemy](https://dev.to/rosewabere/building-a-production-grade-async-backend-with-fastapi-sqlalchemy-postgresql-and-alembic-2ca4) (MEDIUM)
- [LoadForge — Optimizing Database Performance for High-Speed FastAPI](https://loadforge.com/guides/database-performance-tuning-for-high-speed-fastapi-web-services) (MEDIUM)
- [DEV Community / Bhagya Rana — FastAPI with AsyncPostgres](https://medium.com/@bhagyarana80/fastapi-with-asyncpostgres-lower-latency-through-native-drivers-ca69ad941cb8) (MEDIUM — asyncpg vs psycopg2)
- [Medium / Virgillia Yeala — Building Complete Monitoring Stack with Prometheus, Grafana, Sentry](https://medium.com/@virgilliayeala/building-a-complete-monitoring-stack-using-prometheus-grafana-and-sentry-d452bdbfd67b) (MEDIUM)
- [Celery Documentation — Tasks](https://docs.celeryq.dev/en/stable/userguide/tasks.html) (HIGH — official)
- [Vinta Software — Celery Advanced: Mastering Idempotency, Retries, Error Handling](https://www.vintasoftware.com/blog/celery-wild-tips-and-tricks-run-async-tasks-real-world) (MEDIUM)

### Event Sourcing / Audit
- [Architecture Weekly / Oskar Dudycz — Building Your Own Ledger Database](https://www.architecture-weekly.com/p/building-your-own-ledger-database) (HIGH — event sourcing for ledgers)
- [DesignGurus — How to Enforce Immutability and Append-Only Audit Trails](https://www.designgurus.io/answers/detail/how-do-you-enforce-immutability-and-appendonly-audit-trails) (MEDIUM)
- [Hubifi — Immutable Audit Trails Guide](https://www.hubifi.com/blog/immutable-audit-log-basics) (MEDIUM)

### UX / Trust
- [BlogExample — Building Trust in Online Betting Through Transparency](https://www.blogexample.com/blog/building-trust-in-online-betting-through/) (LOW-MEDIUM)
- [The Comeback — Why the Platform You Bet On Matters](https://thecomeback.com/gambling/why-the-platform-you-bet-on-matters-more-than-you-think.html) (LOW-MEDIUM)

---
*Pitfalls research for: White-label prediction market platform (XPredict)*
*Researched: 2026-05-25*
