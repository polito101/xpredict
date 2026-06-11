---
phase: quick-260611-u0q
plan: 01
subsystem: api
tags: [slotslaunch, casino, httpx, redis, iframe, nextjs, fastapi, integration]

# Dependency graph
requires:
  - phase: v1.3 Live-Bets demo (LB-A)
    provides: external-integration package layout (client/service/schemas/router) + dependency-override test seam
  - phase: Phase 17 Catalog
    provides: public unauthenticated catalog router + Server-Component catalog-page (grid/empty/error) patterns
provides:
  - Public GET /api/v1/casino/games proxy ({status:active|inactive, games[]}) — Redis-cached, token-from-env, never 500s
  - slotslaunch integration package (SlotsLaunchClient / CasinoService / CasinoGame+CasinoCatalog schemas / casino_router)
  - /casino frontend page — thumbnail grid (active) + friendly empty state (inactive) + fullscreen iframe launcher with onError fallback
  - Casino nav entry (after Live) + /casino player-auth route gate
affects: [casino, slotslaunch, sales-demo]

# Tech tracking
tech-stack:
  added: []  # no new packages — httpx/pytest-httpx already present; frontend reuses existing deps
  patterns:
    - "graceful-degrade external proxy: ANY upstream failure (inactive body, network, garbage) -> {status:inactive,games:[]} HTTP 200, never 500"
    - "domain-bound token via Origin header; token embedded ONLY in backend-composed iframe_url, never a standalone field nor in the client bundle"
    - "active catalog Redis-cached (12h TTL); inactive branch never cached so the surface lights up with zero code changes on activation"

key-files:
  created:
    - backend/app/integrations/slotslaunch/client.py
    - backend/app/integrations/slotslaunch/service.py
    - backend/app/integrations/slotslaunch/schemas.py
    - backend/app/integrations/slotslaunch/router.py
    - backend/tests/integrations/slotslaunch/test_casino_router.py
    - frontend/src/lib/casino.ts
    - frontend/src/app/casino/page.tsx
    - frontend/src/app/casino/casino-grid.tsx
    - frontend/src/app/casino/game-launcher.tsx
  modified:
    - backend/app/core/config.py
    - backend/app/main.py
    - .env.example
    - docker-compose.yml
    - frontend/src/components/player-nav.tsx
    - frontend/src/proxy.ts

key-decisions:
  - "SlotsLaunch subscription is inactive today — the whole surface ships degraded (backend returns inactive, frontend shows empty state) and lights up with zero code changes once the free plan activates."
  - "Plain <img> (not next/image) for thumbnails: SlotsLaunch CDN hosts are arbitrary and the app has no images.remotePatterns allow-list; the plan explicitly permits a plain img with object-cover."
  - "Grid renders NO iframe; an iframe (1 upstream quota request) loads only on an explicit tile click via the fullscreen GameLauncher."

patterns-established:
  - "Pattern: external demo proxy that never 500s — every failure mode maps to a single inactive surface, returned HTTP 200."
  - "Pattern: secret token domain-bound + composed server-side into the launch URL; raw value never crosses to the browser."

requirements-completed: [CASINO-01, CASINO-02, CASINO-03]

# Metrics
duration: ~25min
completed: 2026-06-11
---

# Phase quick-260611-u0q: SlotsLaunch Casino (demo) Summary

**SlotsLaunch demo-slots integration: a Redis-cached, token-from-env backend proxy (`GET /api/v1/casino/games`) plus a `/casino` Next.js page with a thumbnail grid and a fullscreen iframe launcher — graceful-degrading to a friendly empty state while the subscription is inactive, and lighting up with zero code changes once it activates.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-06-11T19:30Z (approx)
- **Completed:** 2026-06-11T19:55Z
- **Tasks:** 2/2
- **Files created:** 9 · **Files modified:** 6

## Accomplishments
- Public unauthenticated `GET /api/v1/casino/games` returning `{status, games[]}` — active with backend-composed iframe URLs, inactive/empty (HTTP 200) otherwise, never 500s on any upstream failure.
- `slotslaunch` integration package mirroring the polymarket/livebets layout: `SlotsLaunchClient` (Origin-header domain-bound token, no-raise on the inactive 200 body), `CasinoService` (Redis-cached active catalog, graceful inactive on every failure path), `CasinoGame`/`CasinoCatalog` pydantic v2 schemas, and the unauthenticated `casino_router` mounted in `main.py`.
- `SLOTSLAUNCH_TOKEN` wired through `Settings` + `.env.example` (placeholder) + docker-compose (`${SLOTSLAUNCH_TOKEN:-}`) — never hardcoded or committed; the real value lives only in gitignored `.env.local`.
- `/casino` page: thumbnail grid (active) or a friendly "Casino demo not available yet" empty state (inactive/empty); clicking a tile opens a fullscreen iframe loading only that game with an `onError` fallback; Casino nav entry added after Live and gated behind player auth.
- 6 hermetic backend tests (active / inactive / not-cached / upstream-error / warm-cache / cache-populate) — mocked upstream + in-memory Redis, no network, no Docker.

## Task Commits

1. **Task 1: Backend SlotsLaunch proxy (settings, client, service, router, tests)** — `ac41880` (feat) — built implementation + tests together; 6 tests green.
2. **Task 2: Frontend Casino (demo) page (fetch helper, grid, launcher, nav + gate)** — `222c8ee` (feat)

_Note: Task 1 was `tdd="true"`. Because this integration package and its hermetic test were authored as one cohesive unit (no pre-existing code to test against), they landed in a single `feat(...)` commit rather than separate RED/GREEN commits — see TDD Gate Compliance below._

## Files Created/Modified
- `backend/app/integrations/slotslaunch/client.py` — async httpx client; `GET /api/games` with `Origin` header + `token` param; returns the inactive 200 body as-is.
- `backend/app/integrations/slotslaunch/service.py` — `get_catalog(redis, client)`; Redis-cached active catalog + composed iframe URLs; degrades any failure to inactive.
- `backend/app/integrations/slotslaunch/schemas.py` — `CasinoGame` / `CasinoCatalog` pydantic v2 models.
- `backend/app/integrations/slotslaunch/router.py` — public `GET /api/v1/casino/games` (no auth dep; omits the future-import per the FastAPI/Annotated constraint).
- `backend/tests/integrations/slotslaunch/test_casino_router.py` — hermetic router tests (FakeSlotsLaunchClient + FakeRedis).
- `backend/app/core/config.py` — `SLOTSLAUNCH_TOKEN/API_BASE/ORIGIN/CACHE_TTL_SECONDS` settings.
- `backend/app/main.py` — mounts `casino_router` next to `public_catalog_router`.
- `.env.example` / `docker-compose.yml` — `SLOTSLAUNCH_TOKEN` placeholder + per-service passthrough.
- `frontend/src/lib/casino.ts` — `fetchCasinoGames()` (apiBase split, no-store, degrades to inactive).
- `frontend/src/app/casino/page.tsx` — async Server Component: grid or empty state.
- `frontend/src/app/casino/casino-grid.tsx` — client grid; no iframe in the grid; click opens launcher.
- `frontend/src/app/casino/game-launcher.tsx` — client fullscreen overlay; single iframe + onError fallback.
- `frontend/src/components/player-nav.tsx` — Casino nav entry after Live.
- `frontend/src/proxy.ts` — `/casino` added to the player-auth regex + matcher.

## Decisions Made
- SlotsLaunch is inactive today → ship the full surface degraded; it lights up with zero code changes on activation (inactive branch is never cached).
- Plain `<img>` over `next/image` (no `images.remotePatterns` allow-list for arbitrary SlotsLaunch CDN hosts) — plan-permitted, avoids a runtime image-domain error.
- No new packages (httpx / pytest-httpx already in `backend/pyproject.toml`; frontend reuses existing deps) — Package Legitimacy Gate N/A.

## Deviations from Plan

### Adjustment (not a code deviation)

**1. [Rule 3 - Blocking] Frontend lint command adapted to the project's actual tooling**
- **Found during:** Task 2 verification
- **Issue:** The plan's verify command `pnpm exec next lint --dir src/app/casino ...` fails — this repo is on Next 16 + ESLint 9 flat config, where `next lint` was removed and the repo's `lint` script is `eslint src` (no `--dir` flag).
- **Fix:** Ran `pnpm exec eslint src/app/casino src/lib/casino.ts src/components/player-nav.tsx src/proxy.ts` (the project's real linter) instead — clean, no warnings. `pnpm exec tsc --noEmit` also passed.
- **Files modified:** none (verification-only adaptation).
- **Verification:** ESLint clean; tsc clean; existing `middleware.test.ts` (11) + `player-nav.test.tsx` (6) still green after the proxy/nav edits.

---

**Total deviations:** 1 (verification-command adaptation; no source-code deviation).
**Impact on plan:** None on scope — the substance of the verify gate (typecheck + lint) was honored with the project's actual tooling. All other tasks executed exactly as written.

## Issues Encountered
- Initial ruff run flagged `UP037` (redundant quoted annotations under `from __future__ import annotations`) and `RUF100` (unused `# noqa: BLE001`, since BLE001 isn't enabled in this repo's ruff config) in `service.py`/the test. Auto-fixed via `ruff check --fix` + `ruff format`; mypy clean afterwards.

## User Setup Required
**External service (SlotsLaunch) requires activation to light up the live grid.** `SLOTSLAUNCH_TOKEN` is already present in gitignored `.env.local` (domain-bound to `app.xprediction.online`). Activate the free SlotsLaunch plan to populate the catalog — no code change needed. Until then the surface intentionally shows the friendly empty state, and the backend endpoint returns `{status:"inactive",games:[]}`.

## TDD Gate Compliance
Task 1 is `tdd="true"`. The implementation and its hermetic test were authored together as one unit (greenfield integration — no prior behavior to RED against) and committed in a single `feat(quick-260611-u0q-01)` commit (`ac41880`). There is therefore no separate `test(...)` RED commit preceding a `feat(...)` GREEN commit. The behavior contract from `<behavior>` is fully covered by the 6 passing tests (active / inactive / not-cached / upstream-error / warm-cache / cache-populate). This is a knowing departure from the strict RED→GREEN commit split, recorded here for transparency.

## Next Phase Readiness
- Casino demo surface is complete and ships degraded-by-default; activating the SlotsLaunch plan is the only remaining step to populate the grid (no code change).
- Local-dev note: the iframe token is domain-bound to `app.xprediction.online`, so from localhost the iframe may 403 — the launcher's `onError` fallback handles this gracefully (expected, not a bug).

## Self-Check: PASSED

All 11 tracked source files verified present; both task commits (`ac41880`, `222c8ee`) verified in git log. Backend tests green (6 passed), frontend `tsc --noEmit` clean, ESLint clean, existing middleware/player-nav tests still green (17 passed). Token literal absent from all tracked source (only the `.env.example` placeholder + docker-compose passthrough + env-var name references via `get_settings()`).

---
*Phase: quick-260611-u0q*
*Completed: 2026-06-11*
