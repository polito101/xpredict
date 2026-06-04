# Phase 09 — Deferred Items (out of scope for the current plans)

Discoveries logged during execution that are NOT caused by the current task's
changes. Per the executor scope boundary, these are recorded but NOT fixed here.

## Pre-existing `pnpm typecheck` failure — `src/__tests__/middleware.test.ts`

- **Found during:** Plan 09-03 Task 3 (running `pnpm typecheck`).
- **Error:** `src/__tests__/middleware.test.ts(32,28): error TS2307: Cannot find
  module '../middleware' or its corresponding type declarations.`
- **Root cause (pre-existing):** The Edge middleware file was renamed
  `src/middleware.ts` → `src/proxy.ts` (Next.js 16 renamed the `middleware`
  convention to `proxy`), but `src/__tests__/middleware.test.ts` still imports
  `../middleware`. Last touched in commit `8a9c186` (Phase 02-05) — well before
  Phase 09; not introduced by any 09-03 change.
- **Impact:** `pnpm typecheck` exits non-zero on this one pre-existing error.
  All Phase 09 new files (`price-history-chart.tsx`, `live-indicator.tsx`,
  `use-market-socket.ts`, `lib/api.ts`, `ui/dialog.tsx`, `ui/select.tsx`) are
  type-clean (verified: zero tsc errors attributable to them).
- **Recommendation:** Update `middleware.test.ts` to import `../proxy` (or rename
  the test) in a dedicated fix — out of scope for Phase 09's market-detail /
  real-time work.

## Pre-existing Sentry build notice — `instrumentation-client.ts`

- **Found during:** Plan 09-03 Task 2 (`pnpm build`).
- **Notice:** `[@sentry/nextjs] ACTION REQUIRED: ... export an
  onRouterTransitionStart hook from your instrumentation-client.(js|ts) file.`
- **Impact:** Informational only — `pnpm build` still exits 0. Pre-existing
  (Sentry was wired in Phase 1); unrelated to Phase 09.
- **Recommendation:** Add `export const onRouterTransitionStart =
  Sentry.captureRouterTransitionStart;` to `instrumentation-client.ts` in a
  Sentry-maintenance task — out of scope for Phase 09.
