---
phase: 04-markets-domain-houseadapter
plan: 01
status: complete
commit: 377ece3
tests_passed: 24
tests_total: 24
---

# Plan 04-01 Summary — Domain Models, Protocol & Migration

## What was built

1. **Enums** (`backend/app/markets/enums.py`): `MarketStatus` (DRAFT/OPEN/CLOSED/RESOLVED/CANCELLED) and `MarketSourceEnum` (HOUSE/POLYMARKET) as `str, enum.Enum`.

2. **ORM Models** (`backend/app/markets/models.py`): `Market`, `Outcome`, `OddsSnapshot` with UUID PKs, `lazy="raise"` relationships, CHECK constraints on status/source columns (String + CHECK avoids ACCESS EXCLUSIVE lock vs native ENUM), `generate_slug()` via python-slugify + 6-char UUID suffix.

3. **MarketSource Protocol** (`backend/app/integrations/market_source.py`): `@runtime_checkable Protocol` with `fetch_active_markets`, `fetch_market`, `detect_resolution`. Dict-based `REGISTRY` with `register_source()`/`get_adapter()`. `HouseAdapter` auto-registered at import time.

4. **Alembic migration 0003** (`backend/alembic/versions/0003_phase4_markets.py`): Creates `markets`, `outcomes`, `odds_snapshots` tables. Adds `check_binary_outcomes()` Postgres trigger function (BEFORE INSERT, raises if >= 2 outcomes). Includes downgrade.

5. **Test infrastructure** (`backend/tests/markets/conftest.py`): `admin_user`, `sample_market`, `market_with_bets` fixtures with proper cleanup. Rate-limit reset autouse fixture.

## Key decisions

- String + CHECK constraint over native Postgres ENUM (avoids DDL locks on ALTER TYPE)
- `bet_count` integer column for criteria locking (Phase 5 increments atomically)
- Savepoint pattern for IntegrityError tests (`begin_nested()`)
- `lazy="raise"` on all relationships to prevent N+1 queries

## Tests: 24 passing

- 18 model tests (enums, columns, slug, creation, constraints, trigger, lazy raise)
- 6 protocol tests (isinstance, registry, adapter methods)
