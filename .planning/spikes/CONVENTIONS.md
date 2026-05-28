# Spike Conventions

Patterns and stack choices established across spike sessions. New spikes follow these unless the question requires otherwise.

## Stack
- **Backend spikes:** Python 3.12+ with project deps from `backend/pyproject.toml` (SQLAlchemy 2.0, asyncpg, Pydantic v2, httpx)
- **Database:** Postgres 16 from docker-compose (`localhost:5432`, user `xpredict`) or testcontainers (`postgres:16-alpine`) for isolation
- **Runner:** `cd backend && uv run python <spike_script.py>` or `uv run --directory backend python .planning/spikes/NNN-*/run.py`
- **No extra deps needed** — project has everything (testcontainers available for concurrency spikes)

## Structure
- Each spike lives in `.planning/spikes/NNN-descriptive-name/`
- Main script: `spike_<name>.py` or `run.py` — standalone, runs from backend dir
- Fixtures: `fixtures/*.json` for captured test data
- Shared lib: `.planning/spikes/_lib/` — `harness.py` (concurrent load runner, invariant checks) + `pg.py` (testcontainers DSN)
- Spike schema isolation: use `spike_NNN` Postgres schema, create + drop per run

## Patterns
- **Postgres isolation:** Create a temporary schema (`spike_001`, etc.) at start, drop at end
- **Concurrency reproduction:** `asyncio.gather` of N transfers, each on its OWN `AsyncSession` from a pool sized >= N
- **Invariant checks:** final balance, ledger drift, global double-entry sum (must be 0)
- **SQLSTATE branching:** asyncpg surfaces `23505` (unique), `23514` (CHECK), `40001` (serialization failure), `40P01` (deadlock)
- **Dual-format validators:** Gamma API fields may arrive as stringified JSON or pre-parsed lists — handle both via Pydantic `field_validator(mode="before")`
- **Decimal-first:** Use string numeric fields from APIs, parse to `Decimal`. Never trust float variants.
- **ASCII output:** Avoid Unicode arrows/symbols in print statements (Windows cp1252 encoding)
- **Double-entry bookkeeping:** Every wallet operation writes both the balance update AND a ledger entry — verify `SUM(entries) == balance` for integrity
- **Pessimistic locking:** `SELECT ... FOR UPDATE` inside `AsyncSession.begin()` for all wallet state mutations
- **Lock ordering:** Always sort account IDs before acquiring FOR UPDATE locks on multiple rows
- **State machine validation:** Market status derived from `closed` + `umaResolutionStatus` combination, never from a single field
- **Settlement accounting:** Winners draw from pot (market_liability). Losers' stakes already in pot — no separate debit. Remaining pot -> house_revenue. `settled_at IS NULL` = idempotency gate.
- **SETTLING status guard:** Market status must transition OPEN -> SETTLING atomically before querying bets (prevents late-bet pot imbalance)
- **WebSocket broadcast:** Redis pub/sub (`prices:{market_id}` channel) + FastAPI native WebSocket + ConnectionManager per market. Zero new deps needed.

## Tools & Libraries
- `sqlalchemy>=2.0.43` + `asyncpg>=0.30` — proven for concurrent wallet operations + settlement transactions
- `pydantic>=2.10` — proven for Gamma API parsing with `extra='allow'` + custom validators
- `httpx>=0.28` — proven for Gamma API requests
- `json` (stdlib) — for parsing stringified JSON from Gamma API
- `redis.asyncio` (from `redis>=5.0`) — proven for WebSocket pub/sub broadcast (sub-ms latency)
- testcontainers >=4.8 — for disposable Postgres in concurrency spikes
