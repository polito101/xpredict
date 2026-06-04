---
phase: 08-admin-crm-user-management-audit-log-viewer
verified: 2026-05-30T08:30:00Z
status: passed
score: 18/18 must-haves verified
overrides_applied: 0
---

# Phase 8: Admin CRM — User Management & Audit Log Viewer Verification Report

**Phase Goal:** Admin CRM — paginated user list with search/filters, user detail (profile + balance + history + bets), ban/unban state machine with frozen-balance semantics, CSV export, immutable audit-log viewer.
**Verified:** 2026-05-30T08:30:00Z
**Status:** PASSED
**Re-verification:** No — initial verification
**UAT:** Pol (PM) approved via live-stack browser testing on 2026-05-30; recharge URL bug found + fixed in commit 77b1ad4 with regression test before approval.

---

## Goal Achievement

### Observable Truths

All truths drawn from the three plan `must_haves` blocks (08-01, 08-02, 08-03).

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Admin can list users with pagination, search by email/display_name, filter by status and signup date | VERIFIED | `AdminUserService.list_users` with ILIKE `_escape_like`, `status`/`signup_after`/`signup_before` filters, whitelisted sort; `test_user_list.py` 16 tests green |
| 2 | Admin can view user detail including profile fields, wallet balance, transaction count, and bet count | VERIFIED | `AdminUserService.get_user_detail` returns dict with all fields; `GET /api/v1/admin/users/{id}` → `UserDetail`; `test_user_detail.py` green |
| 3 | Admin can ban a user with mandatory reason; banned user cannot log in, place bets, or receive recharges | VERIFIED | `ban_user` sets `banned_at`; `BanRequest.reason` min_length=1 extra="forbid"; 3 enforcement points: `UserManager.assert_not_banned` in auth router (line 163), pre-existing `current_betting_player` gate, inline `target_banned_at` check in `wallet/admin_router.py` lines 80-96; `test_ban_unban.py` 9 tests green |
| 4 | Admin can unban a user; wallet balance is restored as-is (never modified during ban) | VERIFIED | `unban_user` clears `banned_at`; balance untouched across ban→unban cycle (D-03 frozen-balance semantics); `test_banned_user_frozen_balance` passes |
| 5 | Ban/unban actions produce audit log entries (admin.user_banned, admin.user_unbanned) | VERIFIED | `ban_user` and `unban_user` both call `AuditService.record(event_type="admin.user_banned"/"admin.user_unbanned")`; key_link pattern `AuditService\.record.*admin\.user_(banned|unbanned)` confirmed in `service.py` lines 606-612 and 637-643 |
| 6 | Every /api/v1/admin/* endpoint returns 401 without Bearer and 403 with a non-admin Bearer | VERIFIED | `Depends(current_active_admin)` on all 6 CRM endpoints, 3 export endpoints, and the audit-log endpoint; `test_auth_negative.py` tests all routes |
| 7 | Admin can export filtered users to CSV with formula-injection protection | VERIFIED | `sanitize_csv_cell` prefixes `'` to any cell beginning with `FORMULA_TRIGGERS = {"=", "+", "-", "@", "\t", "\r"}`; `export_users` reuses `_apply_user_filters`; `test_csv_export.py` 16 unit + 8 integration tests green |
| 8 | Admin can export filtered transactions to CSV with money values as plain strings | VERIFIED | `build_transactions_csv` renders `_money(amount)` = `str(Decimal)` (no float); timestamps via `_iso_utc`; unit tests confirm |
| 9 | Admin can export filtered bets to CSV | VERIFIED | `build_bets_csv` with P&L computation; `GET /api/v1/admin/export/bets` returns `text/csv` |
| 10 | CSV cells beginning with = + - @ tab CR are prefixed with single quote | VERIFIED | `FORMULA_TRIGGERS` frozenset exact match; `sanitize_csv_cell` implementation confirmed; 6 unit tests (one per trigger + normal + empty) green |
| 11 | Admin can view paginated audit log entries filtered by event_type, actor, and date range | VERIFIED | `audit_admin_router GET ""` with `event_type` exact match, `actor` ILIKE via `_escape_like`, `date_from`/`date_to` range; default `page_size=50`; ordered `occurred_at DESC`; `test_audit_log.py` 11 integration tests green |
| 12 | Audit log is strictly read-only — no edit/delete affordance and no mutation endpoints | VERIFIED | `audit_admin_router` has only `GET ""` and `GET /event-types`; no POST/PUT/PATCH/DELETE routes; test asserts 405 on mutation attempts; DB-level trigger (Phase 1) backs this up |
| 13 | JSONB payload is included in audit log response as a raw JSON object | VERIFIED | `AuditLogItem.payload: dict[str, Any]`; INET `ip` normalised to `str`; `test_audit_log.py` confirms payload field present |
| 14 | Admin sees paginated user list at /admin/users with search, status filter, date filter, and sort | VERIFIED | `frontend/src/app/admin/users/page.tsx` Server Component; `UsersDataTable` with `AdminSearchInput` (300ms debounce), `Select` status filter, `DateRangeFilter`, TanStack Table v8 `manualPagination + manualSorting`; filter changes reset to page 1 |
| 15 | Admin can click a user row to navigate to /admin/users/{id} detail page | VERIFIED | `TableRow` has `onClick={() => router.push('/admin/users/${row.original.id}')}`; `role="link"` + keyboard handler |
| 16 | Admin user detail page has Profile, Wallet, and Bets tabs | VERIFIED | `user-detail-tabs.tsx` renders 3 shadcn Tabs; `profile-tab.tsx`, `wallet-tab.tsx`, `bets-tab.tsx` all present and substantive |
| 17 | Admin can ban a user via dialog with mandatory reason; can unban via dialog with optional reason | VERIFIED | `ban-confirm-dialog.tsx`: reason validated client-side (trim length ≥ 1), destructive variant, spinner during submission; `unban-confirm-dialog.tsx`: reason optional; both call `banUser`/`unbanUser` Server Actions |
| 18 | Recharge form calls Phase 3 endpoint /admin/wallets/{user_id}/recharge with Idempotency-Key; disabled when banned | VERIFIED | `recharge-form.tsx` calls `rechargeWallet` which POSTs to `/admin/wallets/${userId}/recharge` (UAT bug at `/api/v1/admin/wallets` fixed in commit 77b1ad4 + regression test); `crypto.randomUUID()` idempotency key per submit; form is `disabled={banned}` with tooltip; frontend test confirms URL contract |

**Score: 18/18 truths verified**

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/app/admin/router.py` | 6 CRM endpoints, exports `admin_crm_router` | VERIFIED | 6 endpoints confirmed; `__all__ = ["admin_crm_router"]`; no `from __future__ import annotations` |
| `backend/app/admin/schemas.py` | UserListItem, UserDetail, BanRequest, UnbanRequest, UserTransactionItem, UserBetItem | VERIFIED | All 6 schema classes present; `balance: MoneyStr`; `status` computed_field; PaginatedResponse/MoneyStr reused from markets/wallet |
| `backend/app/admin/service.py` | AdminUserService with list/detail/ban/unban/export methods, _escape_like | VERIFIED | All static methods present; LEFT JOIN wallet balance (no N+1); `_escape_like` wildcard guard; export_users/transactions/bets with MAX_EXPORT_ROWS |
| `backend/tests/admin/test_ban_unban.py` | Ban/unban + 3 enforcement points integration tests | VERIFIED | 9 tests; all pass |
| `backend/app/admin/csv_export.py` | sanitize_csv_cell, build_* functions, MAX_EXPORT_ROWS, FORMULA_TRIGGERS | VERIFIED | All exports present; `FORMULA_TRIGGERS = frozenset({"=", "+", "-", "@", "\t", "\r"})`; `MAX_EXPORT_ROWS = 10000` |
| `backend/app/admin/export_router.py` | 3 GET export endpoints, exports `admin_export_router` | VERIFIED | 3 GET endpoints; `__all__ = ["admin_export_router"]`; no `from __future__ import annotations` |
| `backend/app/core/audit/router.py` | GET-only audit endpoints, exports `audit_admin_router` | VERIFIED | Only `GET ""` and `GET /event-types`; `__all__ = ["audit_admin_router"]`; no `from __future__ import annotations` |
| `backend/app/core/audit/schemas.py` | AuditLogItem with payload: dict[str, Any], KNOWN_EVENT_TYPES (19 entries) | VERIFIED | `payload: dict[str, Any]`; 19 event types confirmed |
| `backend/alembic/versions/0008_phase8_user_created_at.py` | users.created_at migration | VERIFIED | File present; additive migration |
| `frontend/src/lib/admin-api.ts` | adminApiFetch, adminApiExport, typed query builders | VERIFIED | "use server"; reads `admin_jwt` HttpOnly cookie; all typed wrappers present; recharge targets `/admin/wallets/` (correct after UAT fix) |
| `frontend/src/app/admin/users/page.tsx` | User list page | VERIFIED | Server Component; calls `fetchUsers`; passes to `UsersDataTable` |
| `frontend/src/app/admin/users/[id]/page.tsx` | User detail page | VERIFIED | Server Component; async params; calls `fetchUserDetail`; passes to `UserDetailTabs` |
| `frontend/src/app/admin/audit-log/page.tsx` | Audit log viewer page | VERIFIED | Server Component; parallel `fetchAuditLog` + `fetchAuditEventTypes`; passes to `AuditLogTable` |
| `frontend/src/components/admin/users-data-table.tsx` | TanStack Table v8 with manualPagination | VERIFIED | Imports from `@tanstack/react-table`; `manualPagination: true`; `manualSorting: true`; all columns present |
| `frontend/src/components/admin/audit-payload-viewer.tsx` | Collapsible JSONB with aria-expanded | VERIFIED | `aria-expanded` on button; `role="region"` + `aria-label="Audit event payload"` on expanded pre block |
| `frontend/src/components/admin/recharge-form.tsx` | Disabled when banned, Idempotency-Key, posts to correct endpoint | VERIFIED | `disabled={banned}` on all form elements; `crypto.randomUUID()` per submit; `rechargeWallet` calls `/admin/wallets/${userId}/recharge` |
| `frontend/src/components/admin/ban-confirm-dialog.tsx` | Mandatory reason, destructive variant, spinner | VERIFIED | Client-side validation `reason.trim().length < 1`; `variant="destructive"`; `Loader2` spinner during submit |
| `frontend/src/components/admin/admin-nav.tsx` | Users and Audit log active links; Markets placeholder | VERIFIED | `Link` for `/admin/users` and `/admin/audit-log` with `usePathname()` active styling; Markets is `<span>` |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `backend/app/admin/router.py` | `backend/app/admin/service.py` | AdminUserService static methods | WIRED | `AdminUserService.list_users`, `.get_user_detail`, `.ban_user`, `.unban_user` all called |
| `backend/app/admin/service.py` | `backend/app/core/audit/service.py` | AuditService.record for ban/unban | WIRED | `AuditService.record(event_type="admin.user_banned")` line 606; `admin.user_unbanned` line 638 |
| `backend/app/admin/router.py` | `backend/app/auth/deps.py` | current_active_admin dependency | WIRED | `Depends(current_active_admin)` on all 6 endpoints |
| `backend/app/admin/export_router.py` | `backend/app/admin/csv_export.py` | build_users/transactions/bets_csv | WIRED | All 3 builder functions imported and called in the 3 export endpoints |
| `backend/app/core/audit/router.py` | `backend/app/core/audit/models.py` | `select(AuditLog)` | WIRED | `base = select(AuditLog)` in `list_audit_log`; `AuditLog` model used directly |
| `frontend/src/app/admin/users/page.tsx` | `frontend/src/lib/admin-api.ts` | adminApiFetch for initial data load | WIRED | `fetchUsers({page:1, page_size:20, ...})` called in Server Component |
| `frontend/src/components/admin/recharge-form.tsx` | `frontend/src/lib/admin-api.ts` | adminApiFetch POST to recharge endpoint | WIRED | `rechargeWallet(userId, ...)` → `adminApiFetch('/admin/wallets/${userId}/recharge', ...)` |
| `frontend/src/components/admin/ban-confirm-dialog.tsx` | `frontend/src/lib/admin-api.ts` | adminApiFetch POST to ban endpoint | WIRED | `banUser(userId, reason)` → `adminApiFetch('/api/v1/admin/users/${id}/ban', ...)` |
| `backend/app/main.py` | All Phase 8 routers | app.include_router | WIRED | `admin_crm_router`, `admin_export_router`, `audit_admin_router` all included in main.py lines 146-148 |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| `users-data-table.tsx` | `data.items` (UserListItem[]) | `fetchUsers` Server Action → `AdminUserService.list_users` → DB SELECT with LEFT JOINs | Yes — real DB query with balance via wallet LEFT JOIN | FLOWING |
| `wallet-tab.tsx` | `balance`, `transactions` | `fetchUserDetail` / `fetchUserTransactions` Server Actions → `get_user_detail` / `get_user_transactions` → DB queries | Yes — balance from accounts table; entries from ledger | FLOWING |
| `audit-log-table.tsx` | `data.items` (AuditLogItem[]) | `fetchAuditLog` Server Action → `audit_admin_router` → `select(AuditLog)` DB query | Yes — real append-only audit_log table | FLOWING |
| `backend/app/admin/csv_export.py` | rows dicts | `AdminUserService.export_users/transactions/bets` → real DB queries capped at MAX_EXPORT_ROWS | Yes — real DB data; not static | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 60 admin backend tests green | `uv run pytest tests/admin/ -q --tb=no` | `60 passed in 31.58s` | PASS |
| Ban/unban 9 tests green | `uv run pytest tests/admin/test_ban_unban.py -q --tb=short` | `9 passed in 16.72s` | PASS |
| Admin-api frontend unit tests | `pnpm exec vitest run src/lib/__tests__/admin-api.test.ts` | `4 tests passed` | PASS |
| Backend lint (Phase 8 modules) | `uv run ruff check app/admin/ app/core/audit/router.py app/core/audit/schemas.py` | `All checks passed!` | PASS |
| Frontend typecheck (admin source) | `pnpm typecheck` (only failure is pre-existing `middleware.test.ts` DEF-FE-01) | No admin-source type errors | PASS |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| ADU-01 | 08-01, 08-03 | Paginated user list with search (email, display name) and filters (status, signup date, last activity) | SATISFIED | `list_users` ILIKE search + status/date filters + balance; `UsersDataTable` with search/filter/sort/pagination |
| ADU-02 | 08-01, 08-03 | User detail page — profile, wallet balance, full transaction history, all bets, ban status | SATISFIED | `get_user_detail` + paginated transactions/bets; Profile/Wallet/Bets tabs in frontend |
| ADU-04 | 08-01, 08-03 | Ban state machine (active → banned); banned user cannot log in or bet; balance frozen | SATISFIED | `ban_user` + `assert_not_banned` in login proxy + `current_betting_player` gate + recharge inline check; `BanConfirmDialog` with mandatory reason |
| ADU-05 | 08-01, 08-03 | Unban; frozen balance restored as-is | SATISFIED | `unban_user` clears `banned_at`; balance never modified by ban/unban; `UnbanConfirmDialog` with optional reason |
| ADU-06 | 08-02, 08-03 | CSV export — users / transactions / bets from admin UI | SATISFIED | `csv_export.py` + `export_router.py` (3 GET endpoints); `ExportCsvButton` with DropdownMenu (3 options); formula-injection protection |
| ADD-04 | 08-02, 08-03 | Audit log — chronological, filterable by event_type and actor, immutable (read-only UI + DB trigger) | SATISFIED | `audit_admin_router` GET-only; KNOWN_EVENT_TYPES 19 entries; `AuditLogTable` + `AuditPayloadViewer` with collapsible JSONB |

**All 6 required requirements: SATISFIED**

No orphaned requirements. REQUIREMENTS.md traceability row shows ADU-01, ADU-02, ADU-04, ADU-05, ADU-06, ADD-04 → Phase 8: Complete.

Note: ADU-03 (manual recharge) is assigned to Phase 5 in REQUIREMENTS.md and is NOT a Phase 8 deliverable. The Phase 3 recharge primitive (`POST /admin/wallets/{id}/recharge`) is consumed by Phase 8's frontend but the requirement itself belongs to Phase 5.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | — | — | — | — |

No TBD/FIXME/XXX markers in any Phase 8 modified file. No stub returns (return null/[]/{}). No hardcoded empty data in rendering paths. No TODO comments in implementation files.

**Pre-existing non-issues (do NOT fail on these):**
- `src/__tests__/middleware.test.ts` typecheck error (DEF-FE-01 — orphan test, pre-existing before Phase 8)
- Full-backend-suite test isolation collapse on Windows (DEF-03-01 — pre-existing; admin tests pass in isolation/group)
- `test_banned_user_betting_returns_403` relies on the Phase 5 `current_betting_player` ban gate which was pre-existing; Phase 8 merely tests it

---

### Human Verification Required

None. All automated checks and behavioral spot-checks passed. UAT was conducted by Pol (PM) on 2026-05-30 against a live stack covering all UI flows (user list, search/filter/sort, user detail tabs, ban/unban dialogs, recharge, CSV export, audit log with collapsible JSONB). The single UAT gap (wrong recharge URL prefix) was fixed in commit 77b1ad4 before UAT approval. No remaining items require human verification.

---

### Gaps Summary

No gaps. All 18 must-have truths are VERIFIED, all 9 key commits confirmed in git history, all artifacts exist and are substantive (no stubs), all key links are wired, data flows to real DB queries, and the full test suite (60 backend + 4 frontend tests) passes. Requirements ADU-01, ADU-02, ADU-04, ADU-05, ADU-06, ADD-04 are all satisfied.

---

_Verified: 2026-05-30T08:30:00Z_
_Verifier: Claude (gsd-verifier)_
