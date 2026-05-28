# Spike Conventions

Patterns established across the Phase 3 ledger concurrency spikes. New spikes follow these
unless the question requires otherwise.

## Stack

- Postgres 16 via **testcontainers** (`postgres:16-alpine`) — the same mechanism Phase 1
  integration tests use. Disposable, random host port, no conflict with Pol's `cc_postgres`.
- **SQLAlchemy 2.0 async + asyncpg**, run via `uv run --directory backend …` so the spike uses
  the EXACT Phase 3 dependency versions (dev group included). Do **not** invoke the raw
  `backend\.venv\Scripts\python.exe` — it lacks the dev-group deps (testcontainers).
- Money is `Decimal` + `NUMERIC(18,4)`; UUID PKs (ARCHITECTURE.md BIGINT model SUPERSEDED).

## Structure

- `.planning/spikes/_lib/` — shared `harness.py` (schema, concurrent load runner, invariant
  checks, all locking strategies) + `pg.py` (testcontainers → asyncpg DSN).
- `.planning/spikes/NNN-name/run.py` + `README.md` — one runnable scenario per spike; `run.py`
  prepends `../_lib` to `sys.path`.
- Run: `uv run --directory backend python .planning\spikes\NNN-*\run.py` (needs Docker running).

## Patterns

- **Concurrency reproduction:** `asyncio.gather` of N transfers, each on its OWN `AsyncSession`
  from a pool sized ≥ N (sharing one session serializes writers and hides the race). A
  `read_delay` widens the read→write window to make lost-update deterministic for naive baselines.
- **Invariant checks:** final balance, ledger drift (`balance − (SUM credit − SUM debit)`), and
  global double-entry sum (must be 0). A scenario is "correct" only if balance ≥ 0 AND drift 0
  AND final balance == opening − amount·(ok count) AND global net-zero.
- **SQLSTATE branching:** asyncpg surfaces `23505` (unique / idempotency), `23514` (CHECK),
  `40001` (serialization failure), `40P01` (deadlock) via `DBAPIError.orig.sqlstate`.
- **Per-strategy isolation:** engine-level `create_async_engine(isolation_level="SERIALIZABLE")`
  (robust) rather than a mid-transaction `SET TRANSACTION ISOLATION LEVEL`.

## Tools & Libraries

- testcontainers ≥4.8, sqlalchemy 2.0.43, asyncpg, Python 3.12 — all already in
  `backend/pyproject.toml` (dev group). **No new dependencies introduced by the spikes.**
