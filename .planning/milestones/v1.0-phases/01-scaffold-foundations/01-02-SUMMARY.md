---
phase: 01-scaffold-foundations
plan: 02
subsystem: infra
tags: [nextjs-15, react-19, typescript, tailwind-4, sentry-nextjs, vitest, pnpm, docker, route-handlers, frontend]

# Dependency graph
requires:
  - phase: 01-scaffold-foundations
    provides: "Sentry init tagging shape (service=api|worker|beat) — Plan 01-02 mirrors this with service=frontend so all 4 surfaces share a single filter"
provides:
  - "Next.js 15 + React 19 + TypeScript 5 + Tailwind 4 + ESLint 9 frontend scaffold under frontend/ (pinned next@^15.5.18 — STACK.md §4.1 locks Phase 1 on 15.x, scaffolder defaulted to 16+)"
  - "@sentry/nextjs 10.x server (instrumentation.ts) + client (instrumentation-client.ts) Sentry init with initialScope.tags.service='frontend' on BOTH surfaces"
  - "GET /api/healthz Route Handler returning {status:'ok'} 200 — docker-compose frontend healthcheck target (PLT-10)"
  - "GET /api/sentry-test Route Handler throwing new Error('sentry test from frontend') — frontend Sentry triple-trigger (D-29 / PLT-08)"
  - "Vitest 2.1 config (environment='node') + 2 passing route-handler tests"
  - "frontend/Dockerfile (node:20-alpine + corepack pnpm + EXPOSE 3000 + CMD pnpm dev) — Plan 01-03 docker-compose `frontend` service builds this"
  - "withSentryConfig wrapper around next.config.ts default export (Pattern 5c) — source-map upload disabled in Phase 1 (Phase 11 polish)"
affects: [01-03-compose-and-alembic, 01-04-ci-and-acceptance, 02-auth-identity, 09-user-ux-polish, 10-admin-dashboard]

# Tech tracking
tech-stack:
  added:
    - "next 15.5.18 (App Router, stable build, no Turbopack)"
    - "react 19.2.6 + react-dom 19.2.6"
    - "typescript 5.9.3"
    - "tailwindcss 4.3.0 (v4 CSS-first @import 'tailwindcss')"
    - "@tailwindcss/postcss 4.3.0"
    - "@sentry/nextjs 10.53.1 (>= 8.28 required for captureRequestError — RESEARCH Assumption A4)"
    - "vitest 2.1.9 + @vitest/coverage-v8 2.1.9"
    - "eslint 9.39.4 + eslint-config-next 15.5.18 + @eslint/eslintrc 3.3.5 (FlatCompat shim)"
    - "pnpm 9.15.0 (host-installed; lockfile committed)"
  patterns:
    - "Sentry server init in instrumentation.ts::register() guarded by NEXT_RUNTIME==='nodejs' (Pattern 5c)"
    - "Sentry client init in instrumentation-client.ts at module top-level (no guard)"
    - "service=frontend tag on BOTH surfaces — mirror of backend's per-service tagging shape (Plan 01-01 init_sentry)"
    - "Route Handler tests via direct GET() invocation under vitest environment=node (no fetch mock, no HTTP roundtrip)"
    - "withSentryConfig wrapper with source-map upload disabled in Phase 1 (sourcemaps.disable=true) — Phase 11 will enable for staging"
    - "Next.js scaffolder cruft purged (AGENTS.md/CLAUDE.md/Vercel-branded SVGs/favicon.ico) — Phase 1 ships ONLY what the plan demands"

key-files:
  created:
    - "frontend/package.json — pnpm scripts dev/build/start/lint/typecheck/test, deps pinned to Next 15 / React 19 / Tailwind 4 / @sentry/nextjs 10 / vitest 2"
    - "frontend/pnpm-lock.yaml — frozen-lockfile-reproducible install (553 packages)"
    - "frontend/Dockerfile — node:20-alpine + corepack pnpm + frozen install + EXPOSE 3000"
    - "frontend/next.config.ts — withSentryConfig wrapper; silent in dev, sourcemap upload off in Phase 1"
    - "frontend/tsconfig.json — strict mode, @/* alias, jsx=preserve (Next 15 default)"
    - "frontend/eslint.config.mjs — ESLint 9 flat config via FlatCompat for next/core-web-vitals + next/typescript"
    - "frontend/postcss.config.mjs — @tailwindcss/postcss plugin"
    - "frontend/vitest.config.ts — environment=node, globals=true, include=src/**/*.test.ts"
    - "frontend/instrumentation.ts — Sentry server init + onRequestError=Sentry.captureRequestError"
    - "frontend/instrumentation-client.ts — Sentry browser init"
    - "frontend/src/app/layout.tsx — minimal HTML shell, no Geist fonts (scaffolder cruft removed)"
    - "frontend/src/app/page.tsx — 'XPredict / Phase 1 scaffold OK' hello-world server component"
    - "frontend/src/app/globals.css — Tailwind 4 @import + light/dark theme tokens"
    - "frontend/src/app/api/healthz/route.ts — 4-line GET handler returning {status:'ok'}"
    - "frontend/src/app/api/sentry-test/route.ts — throws new Error('sentry test from frontend')"
    - "frontend/src/app/api/healthz/route.test.ts — 1 Vitest test (status 200 + body shape)"
    - "frontend/src/app/api/sentry-test/route.test.ts — 1 Vitest test (rejects.toThrow exact error)"
    - "frontend/.gitignore — Next.js default (node_modules, .next, .env*)"
  modified: []

key-decisions:
  - "Pinned next@^15.5.18 (NOT next@16+) — STACK.md §4.1 locks Phase 1 on 15.x; the create-next-app scaffolder defaulted to 16.2.6 and was rewritten by hand."
  - "Renamed `test` script `vitest` -> `vitest run` because pnpm 9.x parses `pnpm test --run` as an unknown pnpm option ('Unknown option: run'). Non-watch is the right CI default; `test:watch` added for the dev loop."
  - "@sentry/nextjs 10.x picked instead of 8.x — the plan requires >= 8.28 (Pattern 5c assumption A4 for captureRequestError); latest stable 10.53.1 satisfies it and is current."
  - "next.config.ts disables source-map upload in Phase 1 (sourcemaps.disable=true). Without a SENTRY_AUTH_TOKEN the plugin would no-op anyway; opting out explicitly avoids 'skipping upload' warnings in dev/CI. Phase 11 polish re-enables for staging."
  - "Dropped Geist fonts + Vercel-branded SVGs + scaffolder AGENTS.md/CLAUDE.md (which actively misdirected — they referenced Next 16). Phase 1 ships ONLY what the plan's <files_modified> list demands."

patterns-established:
  - "Sentry frontend init mirrors backend tagging shape — both surfaces use initialScope.tags.service so a single Sentry project filter scopes events per-surface (CONTEXT D-27)"
  - "Route Handler tests via direct GET() invocation — no HTTP/fetch mock layer; tests are sub-10ms each"
  - "ESLint 9 flat config + FlatCompat for Next 15's shareable configs (next/core-web-vitals, next/typescript) — pattern that downstream phases inherit"
  - "Dockerfile for dev profile (pnpm dev hot-reload via bind-mount); staging swaps to pnpm build && pnpm start without restructuring layers"

requirements-completed: [PLT-08, PLT-10]

# Metrics
duration: 12min
completed: 2026-05-26
---

# Phase 01 Plan 01-02: Frontend Next.js 15 + Sentry + healthz + Vitest Summary

**Next.js 15 + React 19 + Tailwind 4 frontend scaffold with @sentry/nextjs 10 initialised on both server (`instrumentation.ts`) and browser (`instrumentation-client.ts`) surfaces tagged `service=frontend`, plus `/api/healthz` (docker-compose healthcheck target) + `/api/sentry-test` (D-29 triple-trigger), 2 green Vitest route-handler tests, and a Node 20 + pnpm Dockerfile for Plan 01-03's `frontend` compose service.**

## Performance

- **Duration:** ~12 minutes
- **Started:** 2026-05-26T06:22:35Z
- **Completed:** 2026-05-26T06:34:46Z
- **Tasks:** 2 (executed atomically as separate commits)
- **Files modified:** 17 created (frontend/ from scratch), 0 modified

## Accomplishments

- Frontend scaffold builds, typechecks, and tests green in <2s test runtime: `pnpm install --frozen-lockfile` ✓, `pnpm typecheck` ✓, `pnpm test` ✓ (2/2), `pnpm build` ✓ (Sentry server init detected; `/api/healthz` + `/api/sentry-test` listed as dynamic ƒ routes)
- Sentry SDK live on the **4th surface** — alongside Plan 01-01's api/worker/beat surfaces, every Sentry event in XPredict now carries a `service=*` tag that scopes alerts per CONTEXT D-27 / PLT-08 (`grep -E "service.*frontend" frontend/instrumentation*.ts` returns 4 matches across both files)
- `/api/healthz` is the docker-compose `frontend` service's healthcheck target (PLT-10 frontend portion); `/api/sentry-test` is the D-29 frontend triple-trigger
- `frontend/Dockerfile` ships in the exact shape Plan 01-03's `docker-compose.yml` expects (node:20-alpine + corepack pnpm + frozen install + EXPOSE 3000 + CMD pnpm dev); passes `docker build --check`
- Vitest 2.1 wired with `environment="node"` for Route Handler tests; 2 tests collect in 134ms, execute in 8ms total — no HTTP layer or fetch mock needed

## Task Commits

Each task was committed atomically:

1. **Task 1: Next.js 15 + Tailwind 4 + TypeScript scaffold + @sentry/nextjs install + withSentryConfig wrapper + Dockerfile + hello-world page** — `f27a7ae` (feat)
2. **Task 2: Sentry instrumentation (server + client) + /api/healthz + /api/sentry-test Route Handlers + Vitest config + 2 route-handler tests (TDD)** — `bf72465` (test)

_Note: Task 2 is TDD-flagged. RED was demonstrated by running `pnpm test` with only the test files present (both failed with "Failed to load url ./route. Does the file exist?"); GREEN was demonstrated after adding the route handlers and instrumentation. Both phases land in a single commit per the project's TDD-bundle convention (Plan 01-01 used the same shape — see `9d08305`)._

**Plan metadata commit:** _added below after this summary is staged_

## Files Created/Modified

17 files created under `frontend/`:

**Build / config** — `package.json`, `pnpm-lock.yaml`, `Dockerfile`, `next.config.ts`, `tsconfig.json`, `eslint.config.mjs`, `postcss.config.mjs`, `vitest.config.ts`, `.gitignore`
**Sentry instrumentation** — `instrumentation.ts` (server, `register()` + `onRequestError`), `instrumentation-client.ts` (browser)
**App surface** — `src/app/layout.tsx`, `src/app/page.tsx`, `src/app/globals.css`
**Route Handlers** — `src/app/api/healthz/route.ts`, `src/app/api/sentry-test/route.ts`
**Tests** — `src/app/api/healthz/route.test.ts`, `src/app/api/sentry-test/route.test.ts`

## Decisions Made

1. **Pinned `next@^15.5.18` (NOT 16+)** — `create-next-app@latest` shipped Next 16.2.6 by default; STACK.md §4.1 locks Phase 1 on 15.x. Rewrote `package.json` by hand, re-installed via `pnpm install` (553 packages resolved cleanly). Also pinned `react@^19.0.0`, `eslint-config-next@^15.5.18` to align.
2. **`@sentry/nextjs@^10.53.0`** — the plan requires `>= 8.28.0` (RESEARCH Pattern 5c assumption A4 for `captureRequestError`); 10.x is the current stable line and satisfies the lower bound. Verified `Sentry.captureRequestError` + `Sentry.init` + `Sentry.withSentryConfig` are all exported.
3. **`test` script changed `vitest` → `vitest run`** — the plan's verification command is `pnpm test --run`, but pnpm 9.x parses `--run` as an unknown pnpm option (`ERROR Unknown option: 'run'`). Non-watch mode is the right CI default; `test:watch` added for the dev loop. Verifier running `pnpm test` (or `pnpm test -- --run`) gets the same green outcome.
4. **`withSentryConfig` opts out of source-map upload (`sourcemaps.disable: true`)** — without `SENTRY_AUTH_TOKEN` the plugin no-ops anyway; the explicit opt-out keeps dev/CI builds clean of "skipping upload" warnings. Phase 11 polish flips this on for staging.
5. **ESLint 9 flat config via `@eslint/eslintrc/FlatCompat`** — Next 15's shareable configs (`next/core-web-vitals`, `next/typescript`) target the legacy `.eslintrc` format; FlatCompat is the supported bridge. Added `@eslint/eslintrc@^3` as devDep.
6. **Stripped scaffolder cruft** — deleted `AGENTS.md` and `CLAUDE.md` (they referenced Next 16 features and would actively misdirect future agents), Vercel-branded SVGs in `public/`, `favicon.ico`, and `README.md`. The plan's `<files_modified>` list does not include any of these.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] `pnpm dlx create-next-app` failed with ENOENT cache race on Windows**
- **Found during:** Task 1 (scaffolding step)
- **Issue:** `pnpm dlx create-next-app@latest` repeatedly failed with `ENOENT: no such file or directory, open '...pnpm-cache/dlx/.../node_modules/create-next-app/package.json'` — a known dlx cache race on Windows. Even after `rm -rf pnpm-cache/dlx`, the issue recurred.
- **Fix:** Used `npx --yes create-next-app@latest frontend ...` (Node's bundled npm-exec) instead of `pnpm dlx`. The scaffolder ran cleanly and produced the same artifact set. The lockfile + ongoing installs use pnpm; only the one-shot scaffold used npx.
- **Files modified:** none (workflow-only)
- **Verification:** `frontend/` directory created; `pnpm install` against the generated `package.json` succeeds
- **Committed in:** `f27a7ae` (Task 1 commit)

**2. [Rule 1 — Bug fix] `create-next-app@latest` shipped Next 16, plan demands Next 15**
- **Found during:** Task 1 (post-scaffold inspection)
- **Issue:** The scaffolder defaulted to `"next": "16.2.6"` and `"eslint-config-next": "16.2.6"`. STACK.md §4.1 locks Phase 1 on Next 15 ("Stay on 15 — Next 16 removes sync access"). The plan's `<action>` block also says explicitly: "if the latest is 16+, pin to `^15.1.0`".
- **Fix:** Rewrote `frontend/package.json` from scratch — pinned `next@^15.5.18`, `react@^19.0.0`, `eslint-config-next@^15.5.18`, added `@sentry/nextjs@^10.53`, `vitest@^2.1`, `@vitest/coverage-v8@^2.1`, `@eslint/eslintrc@^3` (for FlatCompat), `typescript@^5.5`, `tailwindcss@^4`. Re-ran `pnpm install` — resolved 553 packages cleanly.
- **Files modified:** `frontend/package.json`, `frontend/pnpm-lock.yaml`
- **Verification:** `pnpm install --frozen-lockfile` succeeds; `pnpm typecheck` exits 0; `pnpm build` produces Next 15.5.18 output (`▲ Next.js 15.5.18`)
- **Committed in:** `f27a7ae` (Task 1 commit)

**3. [Rule 1 — Bug fix] ESLint 9 flat config rewrite for Next 15 shareable configs**
- **Found during:** Task 1 (post-scaffold inspection)
- **Issue:** The Next-16-scaffolder generated `eslint.config.mjs` importing `eslint-config-next/core-web-vitals` and `eslint-config-next/typescript` as flat-native modules — paths that exist in `eslint-config-next@16` but NOT in `@15.x`. With Next 15 pinned, the original config would error at lint time.
- **Fix:** Rewrote `eslint.config.mjs` to use `@eslint/eslintrc/FlatCompat` extending `next/core-web-vitals` + `next/typescript` (the Next 15 shareable-config names). Added `@eslint/eslintrc@^3` as devDep.
- **Files modified:** `frontend/eslint.config.mjs`, `frontend/package.json`
- **Verification:** `pnpm typecheck` + `pnpm build` both pass (build also runs lint as part of `Linting and checking validity of types ...`)
- **Committed in:** `f27a7ae` (Task 1 commit)

**4. [Rule 3 — Blocking] `pnpm test --run` fails in pnpm 9.x (`Unknown option: 'run'`)**
- **Found during:** Task 2 (TDD RED phase, first vitest run)
- **Issue:** The plan's verification command is `pnpm test --run` (non-watch mode). Pnpm 9.15.0 parses `--run` as an unknown pnpm-level option and exits with `ERROR Unknown option: 'run'` before even invoking the script. `pnpm test -- --run` works (the `--` forces passthrough) but that's not what the verifier will run.
- **Fix:** Changed `"test": "vitest"` → `"test": "vitest run"` (non-watch by default — the standard CI shape for vitest), and added `"test:watch": "vitest"` for the dev loop. `pnpm test` now runs once and exits, which is the behaviour `--run` was meant to invoke. `pnpm test -- --run` still also works (vitest treats the duplicate `--run` arg as harmless).
- **Files modified:** `frontend/package.json`
- **Verification:** `pnpm test` exits 0 with 2/2 green; `pnpm test -- --run` also exits 0
- **Committed in:** `bf72465` (Task 2 commit)

**5. [Rule 1 — Bug fix] `next.config.ts` deprecation warning on `disableLogger`**
- **Found during:** Task 1 (first `pnpm build`)
- **Issue:** `@sentry/nextjs` 10.x emits `DEPRECATION WARNING: disableLogger is deprecated and will be removed in a future version. Use webpack.treeshake.removeDebugLogging instead.` Phase 1 doesn't need any treeshake config, so the cleanest fix is to drop the option entirely.
- **Fix:** Removed `disableLogger: true` from the `withSentryConfig` options block.
- **Files modified:** `frontend/next.config.ts`
- **Verification:** `pnpm build` no longer emits the deprecation warning
- **Committed in:** `f27a7ae` (Task 1 commit)

**6. [Rule 3 — Blocking, scoped cleanup] Removed Next-16-scaffolder cruft**
- **Found during:** Task 1 (post-scaffold inspection)
- **Issue:** The scaffolder produced `frontend/AGENTS.md` ("This is NOT the Next.js you know... Read `node_modules/next/dist/docs/` before writing any code") and `frontend/CLAUDE.md` (`@AGENTS.md`). With Next 15 pinned, these would actively mislead future agents — they reference Next 16 breaking changes that don't apply here. Also: `public/{next,vercel,file,globe,window}.svg` + `src/app/favicon.ico` (referenced only by the original Vercel-branded placeholder page, which Task 1 replaced with a 20-line XPredict page).
- **Fix:** Deleted all of them. Phase 1 ships only what the plan's `<files_modified>` list demands.
- **Files modified:** deletions only — `frontend/AGENTS.md`, `frontend/CLAUDE.md`, `frontend/README.md`, `frontend/public/*.svg`, `frontend/src/app/favicon.ico`
- **Verification:** `pnpm build` + `pnpm typecheck` still pass with no missing-asset errors
- **Committed in:** `f27a7ae` (Task 1 commit — files were deleted before staging, so they never appear in git history)

---

**Total deviations:** 6 auto-fixed (3 Rule 3 blocking — dlx race, pnpm-9 `--run` parse, scaffolder-cruft cleanup; 3 Rule 1 bugs — Next 16 default, Next 15 eslint config shape, Sentry deprecation warning).
**Impact on plan:** All deviations are scaffold-level infrastructure — none change the interface contracts Plan 01-03+ depend on. The `instrumentation.ts` + `instrumentation-client.ts` API surface, route handler shapes, Dockerfile recipe, and Vitest layout are exactly as the plan specified.

## Issues Encountered

- **`pnpm dlx` cache race on Windows** (Rule 3 deviation #1). Workaround: `npx --yes` for the one-shot scaffolder.
- **CRLF line-ending warnings on every `git add`** — same as Plan 01-01; Plan 01-04 will add `.gitattributes` with `* text=auto eol=lf` for compose/Dockerfile/shell scripts (Pitfall 8).
- **Sentry advisory warnings during build** (`ACTION REQUIRED: To instrument navigations... export const onRouterTransitionStart = Sentry.captureRouterTransitionStart`; "global-error.js file with Sentry instrumentation"). These are recommendations, not errors. Phase 1 ships one page + no navigation surface; React render-error capture and router-transition telemetry are Phase 11 polish concerns. Not blocking.

## User Setup Required

None for this plan. `NEXT_PUBLIC_SENTRY_DSN` is optional — when unset, `Sentry.init` receives `undefined` and Sentry SDK silently no-ops (no events sent). Plan 01-04 will append `NEXT_PUBLIC_SENTRY_DSN=` to `.env.example` when it author's the root env contract. End-to-end Sentry round-trip verification (PLT-08 frontend portion: hit `/api/sentry-test` and observe the event in Sentry) requires a real DSN but is part of the phase verifier step, not this plan.

## Next Phase Readiness

**Wave 2 (Plans 01-03, 01-04) prerequisites in place from this plan:**

- **Plan 01-03 (docker-compose + Alembic baseline + integration tests)** can wire its `frontend` service to `build: ./frontend` (Dockerfile is ready) and `curl -fsS http://localhost:3000/api/healthz` for the healthcheck (route handler returns `{"status":"ok"}` 200 with no async work — Plan 01-03's smoke test won't be flaky).
- **Plan 01-04 (CI + gitleaks + README + acceptance gate)** inherits the `frontend-ci.yml` ingredients: `Node 20`, `pnpm install --frozen-lockfile`, `pnpm lint`, `pnpm typecheck`, `pnpm build`, `pnpm test`. The lockfile is committed and reproducible.

**Phase 2+ contracts:**
- Frontend Sentry surface ships with the same `service=*` tag shape as backend (Plan 01-01) — Phase 11 alert tuning can scope per-service without any retrofit.
- Tailwind 4 v4-form (`@import "tailwindcss"`) means Phase 8+ (Admin CRM, KPI Dashboard) can copy/paste shadcn/ui components without dealing with a v3→v4 migration mid-project.
- Vitest 2.1 + `environment="node"` route-handler test pattern is the template for Phase 2+ frontend tests (auth pages, market pages, admin UI all get the same shape).

**Known stubs / deferred items:**
- `instrumentation-client.ts` does not export `onRouterTransitionStart` — Phase 11 polish concern (navigation telemetry is meaningless until Phase 8+ ships multi-page navigation surface).
- `global-error.js` for React render-error capture — same Phase 11 polish.
- Source-map upload to Sentry is disabled in Phase 1 (`sourcemaps.disable: true`); Phase 11 staging config will enable it with a real `SENTRY_AUTH_TOKEN`.

## Self-Check: PASSED

Verified 17/17 files exist on disk:

- `frontend/package.json`, `frontend/pnpm-lock.yaml`, `frontend/Dockerfile`, `frontend/next.config.ts`, `frontend/tsconfig.json`, `frontend/eslint.config.mjs`, `frontend/postcss.config.mjs`, `frontend/vitest.config.ts`, `frontend/.gitignore`
- `frontend/instrumentation.ts`, `frontend/instrumentation-client.ts`
- `frontend/src/app/layout.tsx`, `frontend/src/app/page.tsx`, `frontend/src/app/globals.css`
- `frontend/src/app/api/healthz/route.ts`, `frontend/src/app/api/healthz/route.test.ts`
- `frontend/src/app/api/sentry-test/route.ts`, `frontend/src/app/api/sentry-test/route.test.ts`

Verified 2/2 task commits exist in `git log --oneline`:
- `f27a7ae` — `feat(01-02): Next.js 15 + Tailwind 4 frontend scaffold`
- `bf72465` — `test(01-02): Sentry instrumentation + healthz/sentry-test routes + Vitest`

Verified `service=frontend` tag present on both surfaces — `grep -E "service.*frontend" frontend/instrumentation*.ts` returns 4 matches (2 per file: one in code, one in comment).

Final end-to-end re-run: `pnpm install --frozen-lockfile` ✓, `pnpm typecheck` ✓, `pnpm test` ✓ (2/2 green in 1.33s), `pnpm build` ✓ (`/api/healthz` and `/api/sentry-test` listed as dynamic ƒ routes; Sentry server init detected — instrumentation-file warning gone). `docker build --check frontend/` returns "Check complete, no warnings found."

---
*Phase: 01-scaffold-foundations*
*Plan: 02*
*Completed: 2026-05-26*
