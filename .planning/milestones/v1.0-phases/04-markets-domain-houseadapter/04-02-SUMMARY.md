---
phase: 04-markets-domain-houseadapter
plan: 02
status: complete
commit: 32f1c84
tests_passed: 32
tests_total: 32
---

# Plan 04-02 Summary — Service, Routers & Schemas

## What was built

1. **Pydantic schemas** (`backend/app/markets/schemas.py`): `MarketCreate` (deadline future validator, initial_odds_yes 0-1), `MarketUpdate`, `OutcomeRead` (Decimal→str serializer), `MarketRead`, `MarketListItem`, `PaginatedResponse[T]` generic, `paginated_response()` helper.

2. **MarketService** (`backend/app/markets/service.py`): Static async methods — `create_market` (slug + 2 outcomes + 2 snapshots + audit), `update_market` (criteria lock check → 423, odds snapshot on change + audit), `close_market` (OPEN check → 409 + audit), `list_markets` (paginated, source/status/category filters), `get_market_by_id`, `get_market_by_slug`.

3. **Admin router** (`backend/app/markets/router.py`): `POST /api/v1/admin/markets` (201), `GET` list (paginated + filters), `GET /{id}`, `PATCH /{id}`, `POST /{id}/close`. All secured with `current_active_admin` Bearer JWT.

4. **Public router** (`backend/app/markets/router.py`): `GET /api/v1/markets` (OPEN only, no auth), `GET /{slug}`, `GET /{slug}/bet-check` (400 if not OPEN).

5. **App wiring** (`backend/app/main.py`): Both routers included after auth routers.

## Key decisions

- No `from __future__ import annotations` in router.py (breaks FastAPI Depends resolution)
- `OutcomeRead` uses `Decimal` type + `@field_serializer` instead of `str` type (ORM provides Decimal)
- Commit + re-fetch pattern after mutations for clean serialization
- Rate-limit reset fixture prevents 429 across router tests

## Tests: 32 passing

- 11 admin router tests (CRUD, auth 401/403, criteria lock 423, close 409)
- 5 public router tests (list, exclude closed, slug lookup, bet-check 200/400)
- 15 service tests (schema validation, serialization, CRUD, locking, pagination)
- 1 updated auth migration test (head check → includes check)
