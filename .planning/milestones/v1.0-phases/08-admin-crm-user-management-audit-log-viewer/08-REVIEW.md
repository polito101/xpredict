---
phase: 08-admin-crm-user-management-audit-log-viewer
reviewed: 2026-05-30T00:00:00Z
depth: deep
files_reviewed: 44
files_reviewed_list:
  - backend/alembic/versions/0008_phase8_user_created_at.py
  - backend/app/admin/__init__.py
  - backend/app/admin/csv_export.py
  - backend/app/admin/export_router.py
  - backend/app/admin/router.py
  - backend/app/admin/schemas.py
  - backend/app/admin/service.py
  - backend/app/auth/manager.py
  - backend/app/core/audit/router.py
  - backend/app/core/audit/schemas.py
  - backend/app/main.py
  - backend/app/wallet/admin_router.py
  - backend/tests/admin/__init__.py
  - backend/tests/admin/_helpers.py
  - backend/tests/admin/conftest.py
  - backend/tests/admin/test_audit_log.py
  - backend/tests/admin/test_auth_negative.py
  - backend/tests/admin/test_ban_unban.py
  - backend/tests/admin/test_csv_export.py
  - backend/tests/admin/test_user_detail.py
  - backend/tests/admin/test_user_list.py
  - frontend/src/app/admin/audit-log/page.tsx
  - frontend/src/app/admin/layout.tsx
  - frontend/src/app/admin/users/[id]/page.tsx
  - frontend/src/app/admin/users/page.tsx
  - frontend/src/components/admin/admin-nav.tsx
  - frontend/src/components/admin/admin-search-input.tsx
  - frontend/src/components/admin/audit-log-table.tsx
  - frontend/src/components/admin/audit-payload-viewer.tsx
  - frontend/src/components/admin/ban-confirm-dialog.tsx
  - frontend/src/components/admin/bets-tab.tsx
  - frontend/src/components/admin/date-range-filter.tsx
  - frontend/src/components/admin/export-csv-button.tsx
  - frontend/src/components/admin/pagination-controls.tsx
  - frontend/src/components/admin/profile-tab.tsx
  - frontend/src/components/admin/recharge-form.tsx
  - frontend/src/components/admin/unban-confirm-dialog.tsx
  - frontend/src/components/admin/user-detail-tabs.tsx
  - frontend/src/components/admin/user-status-badge.tsx
  - frontend/src/components/admin/users-data-table.tsx
  - frontend/src/components/admin/wallet-tab.tsx
  - frontend/src/lib/admin-api.ts
  - frontend/src/lib/admin-format.ts
  - frontend/src/lib/admin-types.ts
findings:
  critical: 3
  warning: 4
  info: 2
  total: 9
status: issues_found
---

# Phase 8: Code Review Report

**Reviewed:** 2026-05-30
**Depth:** deep
**Files Reviewed:** 44
**Status:** issues_found

## Summary

Phase 8 ships a complete admin CRM surface: user list/detail/ban/unban, wallet recharge, CSV export, and an audit-log viewer. The overall architecture is sound — every endpoint carries the `current_active_admin` dependency, the ILIKE wildcard escape is correctly implemented, ban enforcement touches all three required points (login / bet / recharge), and the money discipline (string/Decimal throughout, no float) is strictly maintained.

Three blockers require pre-ship fixes:

1. The `Content-Disposition` header in CSV responses is malformed — filenames with spaces (or any special character) are not RFC 6266 quoted, which will cause some clients to misparse or reject the header.
2. The `sort_by` query parameter on `GET /users` accepts arbitrary strings; the whitelist lookup silently falls back to the default column but the parameter itself carries no server-side validation constraint, leaving a small information-disclosure surface (an attacker can probe column names by observing sort behaviour differences).
3. The `seed_transaction` test helper interpolates a user-controlled string (`reason`) directly into a raw SQL JSONB literal without quoting, creating a SQL injection vector in the test DB path.

Four warnings require attention before or shortly after ship.

---

## Structural Findings (fallow)

No structural pre-pass was provided for this review.

---

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: Unquoted filename in Content-Disposition header (CSV injection / RFC violation)

**File:** `backend/app/admin/export_router.py:49`

**Issue:** The `_csv_response` helper constructs the `Content-Disposition` header by string-formatting the filename directly into an unquoted token position:

```python
headers={"Content-Disposition": f"attachment; filename={filename}"},
```

RFC 6266 requires the filename parameter value to be a quoted-string when it contains any character outside the US-ASCII token set (spaces, commas, semicolons, non-ASCII). The filenames here (`users.csv`, `transactions.csv`, `bets.csv`) are hardcoded literals, so no actual exploit exists today. However:

- Any future caller that passes a user-influenced filename would be able to inject a semicolon and append arbitrary header directives (e.g., `filename=x; filename*=utf-8''evil`).
- Several HTTP clients (including Python's `email.headerregistry` and some browser versions) already mis-parse the unquoted form; RFC 6266 §5 explicitly requires quoting for `filename`.
- The `adminApiExport` frontend helper parses the disposition with a regex: `disposition.match(/filename="?([^"]+)"?/i)` — this regex works for both quoted and unquoted forms, but only accidentally.

**Fix:**
```python
def _csv_response(content: str, filename: str) -> Response:
    # RFC 6266: always quote the filename parameter value.
    safe_name = filename.replace('"', '\\"')
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )
```

---

### CR-02: `sort_by` parameter accepts arbitrary strings — no server-side validation constraint

**File:** `backend/app/admin/router.py:59`

**Issue:** The `sort_by` query parameter is declared as a plain `str` with no `pattern=` constraint:

```python
sort_by: str = Query(default="created_at"),
```

The whitelist (`_SORTABLE` dict in `service.py`) correctly prevents SQL injection by falling back to `User.created_at` for unknown values. However:

- The endpoint silently accepts and ignores any `sort_by` value. An attacker can probe: `?sort_by=hashed_password` produces the same result as `?sort_by=created_at`, but `?sort_by=created_at` differs from `?sort_by=email`. The differing result sets can be used to infer whether a given string matches a valid column name — a minor information-disclosure oracle.
- The silent fallback also means client-side bugs (typos in `sort_by`) produce a "works but wrong" result with no error feedback, which is a maintainability hazard.
- The companion `sort_order` parameter does have a `pattern=` constraint (line 60), making the asymmetry a code-smell that suggests the validation was forgotten.

**Fix:** Add a `pattern=` constraint mirroring the whitelist:

```python
sort_by: str = Query(
    default="created_at",
    pattern="^(created_at|email|display_name|banned_at)$",
),
```

This returns a 422 for unknown sort columns instead of silently falling back.

---

### CR-03: SQL injection via string interpolation in test helper `seed_transaction`

**File:** `backend/tests/admin/_helpers.py:103`

**Issue:** The `seed_transaction` helper constructs the `metadata` JSON value by raw string interpolation of the `reason` argument:

```python
{"id": transfer_id, "k": TRANSFER_RECHARGE, "meta": f'{{"reason": "{reason}"}}'},
```

This is passed to `CAST(:meta AS jsonb)` as a bound parameter — the `:meta` placeholder prevents SQLi at the Postgres protocol level for that variable. However, the string itself is hand-rolled JSON: if `reason` contains a double-quote or backslash (e.g., `reason='"; DROP TABLE users; --'`), the resulting string is malformed JSON and `CAST` raises a Postgres error. With a crafted `reason` such as `x", "injected": true, "x": "x`, the final JSONB silently gains an extra key.

While this is test code (not production), this helper is shared across all Phase 8 integration tests and could produce confusing test failures or subtly wrong audit payloads during future test development. Proper JSON serialization should always be used.

**Fix:**
```python
import json

async def seed_transaction(
    engine: AsyncEngine,
    wallet_id: UUID,
    *,
    amount: Decimal,
    reason: str = "test recharge",
) -> None:
    transfer_id = uuid4()
    meta = json.dumps({"reason": reason})   # safe serialization
    async with engine.connect() as conn:
        await conn.execute(
            text(
                "INSERT INTO transfers (id, kind, metadata) "
                "VALUES (:id, :k, CAST(:meta AS jsonb))"
            ),
            {"id": transfer_id, "k": TRANSFER_RECHARGE, "meta": meta},
        )
        ...
```

---

## Warnings

### WR-01: `rechargeWallet` targets wrong URL prefix — `/admin/wallets` instead of `/api/v1/admin/wallets`

**File:** `frontend/src/lib/admin-api.ts:203`

**Issue:** The `rechargeWallet` Server Action calls:

```typescript
return adminApiFetch(`/admin/wallets/${userId}/recharge`, { ... });
```

The backend router for `wallet_admin_router` is mounted at the prefix `/admin/wallets` (declared in `backend/app/wallet/admin_router.py:46`), and `app.include_router(wallet_admin_router)` in `main.py` mounts it as-is — so the effective path is `/admin/wallets/{user_id}/recharge` (no `/api/v1/` prefix), which matches the URL in the frontend.

However, every other admin API call in `admin-api.ts` uses the `/api/v1/admin/` prefix. This asymmetry means:
- The recharge call bypasses any future API versioning middleware or route prefix applied to the `/api/v1` mount.
- A fix commit (77b1ad4) already changed this from `/api/v1/admin/wallets` to `/admin/wallets`, suggesting the URL was wrong in both directions at different points. The current URL **does** match the backend router but the asymmetry with every other endpoint is a latent maintenance hazard — if the wallet router is ever re-prefixed consistently with the other admin routers, this will silently 404.

**Fix:** Either align `wallet_admin_router`'s prefix with the other admin routers (add `/api/v1` prefix in `admin_router.py`) or leave the current behaviour but add a comment explaining the asymmetric prefix. A regression test asserting the recharge URL would also catch future drift.

---

### WR-02: `buildUsersQuery` is an async Server Action but contains no async logic — callers `await` it unnecessarily

**File:** `frontend/src/lib/admin-api.ts:113-126`

**Issue:** `buildUsersQuery` is exported from a `"use server"` file and returns `Promise<string>`, but its implementation is a pure synchronous operation (builds a `URLSearchParams` object):

```typescript
export async function buildUsersQuery(params: UserListParams): Promise<string> {
  return buildQuery({ ... });  // buildQuery is sync
}
```

Because the file is `"use server"`, every exported function is a Server Action. `buildUsersQuery` is called from `export-csv-button.tsx` (a client component) with `await buildUsersQuery(...)`. This means a pure string-construction operation crosses the client→server network boundary on every export click, adding unnecessary round-trip latency for something that could run in the client bundle.

**Fix:** Move `buildQuery` and `buildUsersQuery` to a separate non-server file (e.g., `lib/admin-query.ts`) and import them directly in both `admin-api.ts` and `export-csv-button.tsx`. This eliminates the unnecessary Server Action round-trip.

---

### WR-03: Ban check in `wallet/admin_router.py` does not 404 for non-existent users

**File:** `backend/app/wallet/admin_router.py:88-96`

**Issue:** The ban check resolves `User.banned_at` for the path `user_id`:

```python
target_banned_at = (
    await session.execute(
        select(User.banned_at).where(User.id == user_id)
    )
).scalar_one_or_none()
if target_banned_at is not None:
    ...raise 403...
```

`scalar_one_or_none()` returns `None` both when the user does not exist AND when the user exists and is not banned (`banned_at IS NULL`). A recharge request targeting a non-existent UUID silently passes the ban check and proceeds to `WalletService.recharge`, which raises `NoResultFound` (caught and re-raised as 404). The behaviour is ultimately correct but the path is misleading: the 404 comes from a completely different code path than expected, and if `WalletService.recharge` is ever refactored to handle missing wallets differently, the non-existent user case would silently regress.

**Fix:** Explicitly 404 when the user is not found:

```python
result = (
    await session.execute(
        select(User.id, User.banned_at).where(User.id == user_id)
    )
).one_or_none()
if result is None:
    raise HTTPException(status_code=404, detail="User not found.")
if result.banned_at is not None:
    raise HTTPException(status_code=403, detail="Account suspended. Cannot recharge a banned user.")
```

---

### WR-04: `formatMoney` misplaces the `$` sign for negative values — "-$100" instead of standard display

**File:** `frontend/src/lib/admin-format.ts:20-41`

**Issue:** The docstring example shows:

```
formatMoney("-100.1234")   -> "-$100.1234"
```

The minus sign is placed before the dollar sign. Financial display conventions and standard locale formatting place the minus after the currency symbol: `$-100.1234` or `(100.1234)`. The current output `-$100.1234` is non-standard and will look wrong on the wallet tab and P&L column to financial operators.

While this is a display issue, the admin surface handles real (play) money and is used by operators making financial decisions. The format is confusing enough that an operator might misread a negative P&L row.

**Fix:**
```typescript
return `${sign}$${withSeparators}${decimals > 0 ? "." + fracPart : ""}`;
// Change to:
return `$${sign}${withSeparators}${decimals > 0 ? "." + fracPart : ""}`;
```

And update the docstring example accordingly.

---

## Info

### IN-01: `get_user_detail` executes 4 sequential DB round-trips for a single user detail fetch

**File:** `backend/app/admin/service.py:381-439`

**Issue:** `get_user_detail` issues four separate `await session.execute(...)` calls in sequence: user lookup → wallet id → balance → transaction count, plus a fifth for bet count. All five could be collapsed into a single query with JOINs and `func.count()` subqueries, mirroring the far more efficient `list_users` implementation in the same file. The current implementation is functionally correct but is O(5) round-trips per user-detail page load.

This is noted as INFO because performance is out of v1 review scope — but the inconsistency with `list_users` (which correctly uses a single query with LEFT JOINs and subqueries) is a design smell that could bite as user volumes grow.

---

### IN-02: `KNOWN_EVENT_TYPES` is a `list[str]` mutable module-level constant — should be a tuple or frozenset

**File:** `backend/app/core/audit/schemas.py:30`

**Issue:**

```python
KNOWN_EVENT_TYPES: list[str] = [
    "auth.player_registered",
    ...
]
```

This is a mutable list exposed via the endpoint `GET /audit-log/event-types`. Any module that imports it and appends to it mutates the canonical list for the entire process. A `tuple[str, ...]` or `frozenset[str]` would prevent accidental mutation. The endpoint currently returns it directly (`return KNOWN_EVENT_TYPES`), which in FastAPI serializes it correctly regardless — but a future `KNOWN_EVENT_TYPES.append(...)` call elsewhere would silently corrupt the dropdown list for all concurrent requests.

**Fix:**
```python
KNOWN_EVENT_TYPES: tuple[str, ...] = (
    "auth.player_registered",
    ...
)
```

And in the endpoint: `return list(KNOWN_EVENT_TYPES)`.

---

_Reviewed: 2026-05-30_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
