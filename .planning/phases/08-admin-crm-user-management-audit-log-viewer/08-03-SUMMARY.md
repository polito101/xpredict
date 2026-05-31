---
phase: 08-admin-crm-user-management-audit-log-viewer
plan: 03
subsystem: ui
tags: [nextjs, react, tanstack-table, shadcn, sonner, server-actions, admin]

requires:
  - phase: 08-01
    provides: admin CRM backend API (users list/detail/ban/unban) under /api/v1/admin
  - phase: 08-02
    provides: CSV export + read-only audit-log API under /api/v1/admin
  - phase: 03
    provides: wallet recharge primitive at POST /admin/wallets/{id}/recharge
provides:
  - Admin CRM frontend surface (Next.js 16 App Router)
  - User list page (TanStack Table v8) with search/status/date filters, sort, pagination, CSV export
  - User detail page with Profile/Wallet/Bets tabs, ban/unban dialogs, wallet recharge form
  - Read-only audit-log viewer with collapsible JSONB payload + event-type/actor/date filters
  - admin-api.ts server-action client (HttpOnly admin_jwt forwarded as Bearer)
affects: [phase-09-user-app-ux, phase-10-admin-dashboard-branding]

tech-stack:
  added: ["@tanstack/react-table@8.21.3", "sonner@2.0.7", "shadcn/ui primitives (table, tabs, dialog, dropdown-menu, select, textarea, separator, tooltip)"]
  patterns:
    - "Server Actions as the only admin API surface (admin_jwt read server-side, never reaches client JS)"
    - "Money values rendered verbatim as strings (never parseFloat/Number) via admin-format helpers"
    - "Idempotency-Key (crypto.randomUUID) generated client-side per recharge submit"

key-files:
  created:
    - frontend/src/lib/admin-api.ts
    - frontend/src/lib/admin-types.ts
    - frontend/src/lib/admin-format.ts
    - frontend/src/app/admin/users/page.tsx
    - frontend/src/app/admin/users/[id]/page.tsx
    - frontend/src/app/admin/audit-log/page.tsx
    - frontend/src/components/admin/* (15 components)
    - frontend/src/components/ui/* (9 shadcn primitives)
    - frontend/src/lib/__tests__/admin-api.test.ts
  modified:
    - frontend/package.json
    - frontend/pnpm-lock.yaml
    - frontend/src/app/layout.tsx
    - frontend/src/app/admin/layout.tsx

key-decisions:
  - "Next.js is v16 (not 15): cookies()/headers() are async — matched the existing await cookies() pattern; no change needed."
  - "shadcn installed manually (no components.json) per UI-SPEC; sonner Toaster wired in app/layout.tsx."
  - "Recharge endpoint is the ONE admin call NOT under /api/v1 (Phase 3 mounts /admin/wallets); admin-api targets it directly."

patterns-established:
  - "URL-contract regression tests: assert each Server Action's backend path (recharge on /admin/wallets, CRM on /api/v1/admin)."
  - "Collapsible JSONB audit payload viewer with aria-expanded/role=region (D-12)."

requirements-completed: [ADU-01, ADU-02, ADU-04, ADU-05, ADU-06, ADD-04]

duration: ~2h (across 3 agent sessions + UAT fix)
completed: 2026-05-30
---

# Phase 8 / Plan 03: Admin CRM Frontend Summary

**Complete Next.js 16 admin CRM surface — TanStack-Table user list, tabbed user detail with ban/unban + wallet recharge, CSV export, and a read-only collapsible-JSONB audit-log viewer — wired to the 08-01/08-02 backend via HttpOnly-cookie Server Actions.**

## Performance

- **Tasks:** 5 (package gate → deps → list → detail/audit → human-verify)
- **Files created/modified:** 38
- **Verification:** `pnpm build` PASS; 41/41 frontend tests pass (the lone failing *file* is the pre-existing orphan `src/__tests__/middleware.test.ts`, DEF-FE-01); admin source type-clean.

## Accomplishments
- User list (TanStack Table v8): email/name search (debounced), status + signup-date filters, column sort, pagination, CSV export dropdown.
- User detail: Profile/Wallet/Bets tabs; ban (mandatory reason) / unban (optional reason) dialogs; wallet recharge form (Idempotency-Key, disabled when banned).
- Audit-log viewer: read-only, event-type/actor/date filters, collapsible JSONB payload, page_size 50.
- admin-api.ts: every admin call funnels through Server Actions; admin_jwt forwarded server-side as Bearer (never exposed to client JS).

## Task Commits
1. **Task 2: deps + shadcn primitives + Toaster** - `8c4ebc0` (feat)
2. **Task 3: admin-api helper, nav, user list + export** - `d159a11` (feat)
3. **Task 4a: user detail tabs + ban/unban dialogs + recharge** - `d7d08e1` (feat)
4. **Task 4b: audit-log page + table + payload viewer** - `15c6394` (feat)
5. **UAT fix: recharge URL prefix** - `77b1ad4` (fix)

_Task 1 was the package-legitimacy human-verify gate (approved). Task 5 was the final human-verify checkpoint (approved after the UAT fix below)._

## Decisions Made
- Followed UI-SPEC; money rendered as strings throughout; recharge sends a fresh `crypto.randomUUID()` Idempotency-Key per submit.

## Deviations from Plan

### Auto-fixed / UAT Issues

**1. [UAT fix - Rule 1 Bug] Recharge Server Action targeted the wrong backend prefix**
- **Found during:** Task 5 human verification (Pol: "no se puede recargar wallet").
- **Issue:** `rechargeWallet()` posted to `/api/v1/admin/wallets/{id}/recharge`, but the Phase 3 recharge endpoint is mounted at `/admin/wallets/{id}/recharge` (no `/api/v1`, unlike the 08-01/08-02 CRM endpoints). Backend returned 404 → Server Action surfaced 500.
- **Fix:** Aligned the path to the real backend mount; added `admin-api.test.ts` URL-contract regression tests (recharge on `/admin/wallets`, CRM on `/api/v1/admin`).
- **Verification:** RED→GREEN unit test; end-to-end recharge → HTTP 200, wallet balance 0→25; full suite 41/41.
- **Committed in:** `77b1ad4`.

**2. [Env finding] Next.js 16 + dockerized-frontend dep install**
- `next` is pinned at v16 (async cookies/headers — already matched). The dockerized frontend image needed the new deps (@tanstack/react-table, sonner); for UAT the frontend was run on the host. Durable follow-up (out of scope): `docker compose build --no-cache frontend`.

---

**Total deviations:** 1 UAT bug fix + 1 environment finding. **Impact:** recharge fix essential for ADU functionality; no scope creep.

## Issues Encountered
- Test users created outside the registration flow (admin/admin2/pol/pruebatest) have no wallet account → recharge returns 404 "wallet not found" for them (expected; real registered players always get a wallet via Phase 3). Verified recharge works on a real registered player (`player2@yopmail.com`).

## User Setup Required
None — admin login uses the existing Phase 2 `/admin/auth/login`; first admin via `backend/bin/create_admin.py` (FIRST_ADMIN_EMAIL/PASSWORD).

## Next Phase Readiness
- Admin CRM frontend complete; all phase-8 requirements (ADU-01/02/04/05/06, ADD-04) have a UI surface.
- Backend prefix inconsistency noted: admin endpoints split between `/api/v1/admin` (08-01/02) and `/admin/*` (Phase 1-3 auth/wallet) — a future hardening pass could unify them.

---
*Phase: 08-admin-crm-user-management-audit-log-viewer*
*Completed: 2026-05-30*
