---
phase: LB-B-frontend-surface
plan: 01
subsystem: frontend
tags: [livebets, server-actions, api-helpers, nav, env]
requires:
  - "LB-A backend /api/live/* routes (session, tables, bets/{id}/placed, bets/{id}/settled) — DONE"
provides:
  - "api.ts: LiveSession, LiveTable, LiveMirrorResult types + LiveTableUnconfigured error"
  - "api.ts: fetchLiveSession(session, tableId?), fetchLiveTables(session) — cookie-forwarded read helpers"
  - "live-actions.ts: recordLivePlaced, recordLiveSettled, mintLiveSession Server Actions"
  - "player-nav: Live nav entry → /live"
  - "frontend/.env.example: NEXT_PUBLIC_LIVEBETS_WIDGET_SRC documented"
affects:
  - "LB-B-02 (/live page + live-table client consume these helpers/actions/types)"
tech-stack:
  added: []
  patterns:
    - "Cookie-forwarding server-side fetch (Cookie: xpredict_session=...) mirrored from bet-actions.ts / wallet/page.tsx"
    - "Discriminated-union Server Action results ({ok:true,...} | {ok:false,reason})"
    - "Typed error class for a specific backend status (LiveTableUnconfigured ← LB-A 400), mirrors MarketNotFound"
key-files:
  created:
    - frontend/src/lib/live-actions.ts
    - frontend/.env.example
  modified:
    - frontend/src/lib/api.ts
    - frontend/src/components/player-nav.tsx
decisions:
  - "money/identifiers stay strings on the wire (SP-1); applied:false is a benign idempotent no-op, not an error (design §8)"
  - "force-added frontend/.env.example (frontend/.gitignore .env* opts it in for committing; placeholders only)"
metrics:
  duration: "~12 min"
  completed: 2026-06-06
  tasks: 3
  files: 4
---

# Phase LB-B Plan 01: Live-bets frontend foundation Summary

Cookie-forwarding LB-A `/api/live/*` helpers + types in `api.ts`, the placed/settled/mint Server Actions in a new `live-actions.ts`, a "Live" nav entry, and a new `frontend/.env.example` documenting `NEXT_PUBLIC_LIVEBETS_WIDGET_SRC` — the interface seam the `/live` page and client widget (LB-B-02/03) build against.

## What was built

- **`api.ts` (Task 1)** — Added `LiveSession`, `LiveTable`, `LiveMirrorResult` interfaces (mirroring LB-A `SessionResponse` / `TableItem` / `MirrorResult`), a typed `LiveTableUnconfigured` error (mirrors `MarketNotFound`) for the LB-A 400 no-table case, and two server-side read helpers `fetchLiveSession(session, tableId?)` (POST `/api/live/session`) and `fetchLiveTables(session)` (GET `/api/live/tables`). Both forward the HttpOnly `xpredict_session` cookie as a `Cookie:` header and use `apiBase()` + `cache:"no-store"`. The session body omits `table_id` when undefined so LB-A defaults from `LIVEBETS_DEFAULT_TABLE_ID`.
- **`live-actions.ts` (Task 2)** — New `"use server"` module exposing `recordLivePlaced(betId)`, `recordLiveSettled(betId)`, and `mintLiveSession(tableId?)`. Reads the cookie via `next/headers` `cookies()`, short-circuits to `{ok:false,reason:"unauthenticated"}` when absent, forwards the cookie to a server-only `getBackendUrl()` (no `NEXT_PUBLIC_`), wraps each fetch in try/catch → `error`, and maps LB-A statuses (200 ok / 401 unauthenticated / 404 not_found / 409 conflict / other error) to a discriminated union. Confirmed LB-A returns **200** for all success cases (no `status_code=201` on any route). `LiveSession` is imported (not redeclared) since `"use server"` forbids non-async value exports.
- **`player-nav.tsx` + `.env.example` (Task 3)** — Added `{ href: "/live", label: "Live" }` to `DESTINATIONS` right after Markets (existing `isActive` prefix-match already handles `/live`). Created `frontend/.env.example` documenting `NEXT_PUBLIC_LIVEBETS_WIDGET_SRC` (LB-C dev value `http://localhost:8080/static/widget.js`) plus `NEXT_PUBLIC_API_URL` and the server-only `BACKEND_URL`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `frontend/.env.example` was gitignored**
- **Found during:** Task 3 commit.
- **Issue:** `frontend/.gitignore:34` has a broad `.env*` rule that also catches `.env.example`, so `git add` refused it. The file is a mandated plan deliverable (`files_modified` + a `must_haves.artifacts` entry).
- **Fix:** Force-added the single file with `git add -f frontend/.env.example`. This is the documented opt-in path — the gitignore line is literally commented "env files (can opt-in for committing if needed)", and the repo already tracks a root-level `.env.example`. The file contains only placeholder values (no secrets). `.gitignore` itself was NOT modified (out of `files_modified` scope).
- **Files modified:** `frontend/.env.example`
- **Commit:** 365df43

### Stack note (not a deviation, but worth recording)
- `frontend/CLAUDE.md` and `CONTEXT.md` say "Next 15", but the installed stack is **Next 16.2.6 + React 19.2.6** (`package.json` / lockfile). The task brief's authoritative override (Next 16) is correct. No code impact in this plan (no custom-element/JSX work here — that lands in LB-B-02).

## Authentication gates
None. All actions are designed to forward the player's existing session; no interactive auth was needed during the build.

## Verification

All commands run from `frontend/` with standalone **pnpm 9.15.0** (verified `pnpm --version` = `9.15.0`; never `corepack`).

- `pnpm install --frozen-lockfile` → Done in 35.2s (node_modules was absent; installed clean, no lockfile change).
- `pnpm exec tsc --noEmit` → **exit 0** (clean).
- `pnpm lint` (`eslint src`) → **exit 0** — 19 pre-existing warnings (0 errors), **none in the LB-B-01 files**. The warnings live in untouched files (`verify-email/page.tsx`, `admin-search-input.tsx`, `use-market-socket.ts`, etc.) and are the `react-hooks/set-state-in-effect` rule the repo's `eslint.config.mjs` deliberately downgraded to "warn".
- Scope: `git diff` over the three commits shows exactly the 4 plan files changed; **`backend/` untouched**.

## Self-Check: PASSED

- Files exist: `frontend/src/lib/api.ts` (FOUND), `frontend/src/lib/live-actions.ts` (FOUND), `frontend/src/components/player-nav.tsx` (FOUND), `frontend/.env.example` (FOUND, tracked).
- Commits exist: `51b07fa` (Task 1), `6637f39` (Task 2), `365df43` (Task 3) — all on `gsd/livebets-demo`.
