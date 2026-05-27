# Spike Conventions

Patterns and stack choices established across spike sessions. New spikes follow these unless the question requires otherwise.

## Stack
- **Backend spikes:** Python 3.12+ with project deps from `backend/pyproject.toml` (SQLAlchemy 2.0, asyncpg, Pydantic v2, httpx)
- **Database:** Postgres 16 from docker-compose (`localhost:5432`, user `xpredict`)
- **Runner:** `cd backend && uv run python <spike_script.py>`
- **No extra deps needed** — project has everything (testcontainers available but not required)

## Structure
- Each spike lives in `.planning/spikes/NNN-descriptive-name/`
- Main script: `spike_<name>.py` — standalone, runs from backend dir
- Fixtures: `fixtures/*.json` for captured test data
- Spike schema isolation: use `spike_NNN` Postgres schema, create + drop per run

## Patterns
- **Postgres isolation:** Create a temporary schema (`spike_001`, etc.) at start, drop at end
- **Dual-format validators:** Gamma API fields may arrive as stringified JSON or pre-parsed lists — always handle both via Pydantic `field_validator(mode="before")`
- **Decimal-first:** Use string numeric fields from APIs, parse to `Decimal`. Never trust float variants.
- **ASCII output:** Avoid Unicode arrows/symbols in print statements (Windows cp1252 encoding)
- **Double-entry bookkeeping:** Every wallet operation writes both the balance update AND a ledger entry — verify `SUM(entries) == balance` for integrity
- **Pessimistic locking:** `SELECT ... FOR UPDATE` inside `AsyncSession.begin()` for all wallet state mutations
- **Lock ordering:** Always sort account IDs before acquiring FOR UPDATE locks on multiple rows
- **State machine validation:** Market status derived from `closed` + `umaResolutionStatus` combination, never from a single field
- **Settlement accounting:** Winners draw from pot (market_liability). Losers' stakes already in pot — no separate debit. Remaining pot → house_revenue. `settled_at IS NULL` = idempotency gate.
- **SETTLING status guard:** Market status must transition OPEN → SETTLING atomically before querying bets (prevents late-bet pot imbalance)
- **WebSocket broadcast:** Redis pub/sub (`prices:{market_id}` channel) + FastAPI native WebSocket + ConnectionManager per market. Zero new deps needed.

## Tools & Libraries
- `sqlalchemy>=2.0.43` + `asyncpg>=0.30` — proven for concurrent wallet operations + settlement transactions
- `pydantic>=2.10` — proven for Gamma API parsing with `extra='allow'` + custom validators
- `httpx>=0.28` — proven for Gamma API requests
- `json` (stdlib) — for parsing stringified JSON from Gamma API
- `redis.asyncio` (from `redis>=5.0`) — proven for WebSocket pub/sub broadcast (sub-ms latency)
