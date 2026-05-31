---
phase: 10-admin-kpi-dashboard-configurable-branding
plan: 05
subsystem: ui
tags: [nextjs, tailwind, runtime-theming, white-label, css-variables, server-component, branding]

# Dependency graph
requires:
  - phase: 10-admin-kpi-dashboard-configurable-branding (Plan 10-01)
    provides: public GET /branding/current (4-field JSON, no bytes) + GET /branding/logo (bytes + nosniff) + server-side hex validation ^#[0-9a-fA-F]{6}$ before persist
provides:
  - Async player root layout that awaits public /branding/current per navigation (cache no-store) and injects <style>:root{--brand-primary;--brand-secondary}</style> from the server-validated hexes
  - globals.css --brand-primary/--brand-secondary tokens on :root (indigo/sky fallback) mapped through @theme inline to --color-brand-* (bg-/text-brand-primary)
  - fetchBrandingPublic() public no-store fetch helper + DEFAULT_BRANDING safe-fallback const
  - BrandLogo player-header component (logo <img> or brand-name wordmark, XPredict fallback)
  - ADD-06 fully delivered (runtime half — the live white-label re-skin with no rebuild/redeploy)
affects: [phase-11-hardening-demo-gate, future player-UI work consuming --brand-* tokens]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Runtime theming via server-injected <style>:root{--brand-*} from validated opaque hex tokens (no static color inlining)"
    - "Public (no-auth) Server-Component fetch helper mirroring lib/api.ts apiBase() + cache no-store + typed throw"
    - "Safe-fallback const (DEFAULT_BRANDING) + matching :root CSS-var defaults so a failed fetch never leaves the UI unbranded-broken"

key-files:
  created:
    - frontend/src/lib/branding-public.ts
    - frontend/src/lib/branding-public.test.ts
    - frontend/src/components/brand-logo.tsx
  modified:
    - frontend/src/app/layout.tsx
    - frontend/src/app/globals.css

key-decisions:
  - "BrandLogo <img> prefixes logo_url with NEXT_PUBLIC_API_URL (browser-public base) because the backend serves /branding/logo on a different origin — payload logo_url is backend-relative"
  - "No existing shared player header component existed; added a minimal brand header bar in the root layout (the only player chrome wrapping every page) to mount BrandLogo"
  - "Root layout's no-store branding fetch makes / (and all pages) server-rendered on demand — this is the intended ADD-06 per-navigation re-skin behavior, not a regression"

patterns-established:
  - "Player runtime theming: validated-hex tokens interpolated ONLY as b.primary_hex/b.secondary_hex into a single <style> block — never concatenate other untrusted strings (T-10-01)"
  - "Logo rendered via <img src> only (SVG-in-img, nosniff), never inlined as DOM markup (T-10-02)"
  - "Legibility-critical header text keeps zinc ink; brand color is an accent (dot) only (UI-SPEC A-PALETTE guardrail #4)"

requirements-completed: [ADD-06]

# Metrics
duration: 4min
completed: 2026-05-31
---

# Phase 10 Plan 05: Runtime Theming Consumption Summary

**Async player root layout that awaits public /branding/current per navigation and injects a `<style>:root{--brand-primary;--brand-secondary}</style>` block from server-validated hexes, with `--brand-*` Tailwind v4 tokens (safe indigo/sky fallback) and a BrandLogo header — the live white-label re-skin (ADD-06) now fully shipped.**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-05-31T08:32:07Z
- **Completed:** 2026-05-31T08:36:13Z
- **Tasks:** 3 (TDD: 1 RED + 2 implementation)
- **Files modified:** 5 (3 created, 2 modified)

## Accomplishments
- `fetchBrandingPublic()` public no-store fetch helper (mirrors `lib/api.ts` `apiBase()` + typed throw) + `DEFAULT_BRANDING` safe-fallback const — a plain module, NOT `"use server"` (the branding read is unauthenticated).
- `globals.css` gains `--brand-primary`/`--brand-secondary` on `:root` (indigo/sky fallback so the player UI is never unstyled) mapped through `@theme inline` to `--color-brand-*` (usable as `bg-brand-primary`/`text-brand-primary`).
- `layout.tsx` is now an async Server Component: `let b = DEFAULT_BRANDING; try { b = await fetchBrandingPublic(); } catch {}` (per-navigation, `cache: "no-store"`, safe fallback) and injects `<style>{`:root{--brand-primary:${b.primary_hex};--brand-secondary:${b.secondary_hex};}`}</style>` — interpolating ONLY the two validated opaque hex tokens (T-10-01), no other dynamic string.
- `BrandLogo` mounted in a new player header bar: renders `<img src=NEXT_PUBLIC_API_URL/branding/logo>` when a logo is set (SVG-in-`<img>`, nosniff, never inlined — T-10-02), else the brand-name wordmark with an XPredict fallback; the wordmark text stays zinc ink with the brand color used only as an accent dot (A-PALETTE guardrail #4).
- ADD-06 fully delivered: an operator palette change in `/admin/branding` re-skins the player on its NEXT navigation with no rebuild/redeploy (SC#5/SC#6) — `/` is now server-rendered on demand (no static color inlining).

## Task Commits

Each task was committed atomically (TDD RED → GREEN):

1. **Task 1: failing test for the public branding fetch** - `ef14654` (test)
2. **Task 2: public branding fetch helper + globals.css brand tokens** - `5bc7985` (feat, fetch test GREEN)
3. **Task 3: async root layout `<style>` injection + BrandLogo header** - `7ab5d1c` (feat, build exits 0)

**Plan metadata:** committed with this SUMMARY (docs).

## Files Created/Modified
- `frontend/src/lib/branding-public.ts` - `BrandingPublic` type, `fetchBrandingPublic()` (apiBase + `cache: "no-store"` + typed throw on `!res.ok`), `DEFAULT_BRANDING` fallback const.
- `frontend/src/lib/branding-public.test.ts` - vitest (node env): 200 → typed object, `cache: "no-store"` asserted, non-ok → throws, `DEFAULT_BRANDING` shape.
- `frontend/src/components/brand-logo.tsx` - `BrandLogo` (logo `<img>` at the backend-public origin or brand-name wordmark with XPredict fallback; brand accent dot only).
- `frontend/src/app/layout.tsx` - async root layout: per-navigation branding fetch + `<style>:root{--brand-*}` injection from validated hexes + player header mounting BrandLogo (KEEPS `<Toaster />`).
- `frontend/src/app/globals.css` - `--brand-primary`/`--brand-secondary` on `:root` + `@theme inline` `--color-brand-*` mapping.

## Decisions Made
- **Logo `<img>` resolves the backend-public origin.** The `/branding/current` payload returns `logo_url` as the backend-relative `/branding/logo`; the Next app and backend are different origins, so `BrandLogo` prefixes it with `NEXT_PUBLIC_API_URL` (browser-public base, mirroring `lib/api.ts`). The grep acceptance (`branding/logo`) still matches and the logo loads correctly cross-origin.
- **No shared player header existed** — each player page rendered its own `<main>`/`<h1>` and the root layout only wrapped `<body>{children}<Toaster/></body>`. Added a minimal brand header bar directly in the root layout (the single chrome wrapping every player page) to mount `BrandLogo`, consuming the brand name + logo from the same already-awaited payload (no extra fetch).
- **`/` becomes server-rendered on demand.** The root layout's `no-store` branding fetch opts every page out of static rendering. This is the intended ADD-06 per-navigation re-skin (SC#5), not a regression — static inlining would defeat the "no rebuild" guarantee.

## Deviations from Plan

None - plan executed exactly as written. (The two implementation choices above — backend-public origin for the logo `<img>`, and adding the header bar in the root layout — are within the plan's explicit instruction to "pass the brand name/logo_url to the player header" and "mount BrandLogo in the existing player header/nav"; no existing header component existed, so the root layout header is the correct mount point. Neither changes architecture nor scope.)

## Known Stubs

None. The `--brand-*` defaults and `DEFAULT_BRANDING` are intentional safe fallbacks (UI-SPEC A-FALLBACK / accessibility guardrail #3), not unwired stubs — they are overridden per navigation by the real server-validated payload. The logo `<img>` is fully wired to the live backend `/branding/logo` endpoint (Plan 10-01).

## Threat Flags

None. The two trust boundaries in scope (public `/branding/current` → player layout; operator hex → `<style>` `:root`) are mitigated exactly as the threat register prescribes: T-10-01 (validated opaque tokens, only `b.primary_hex`/`b.secondary_hex` interpolated), T-10-02 (logo via `<img>`+nosniff, never inlined), T-10-17 (DEFAULT_BRANDING + `:root` fallbacks). No new security surface introduced.

## Issues Encountered
- `corepack` is not on PATH in the bash tool on this Windows host (same as the Phase 09-03 closeout note); resolved by invoking `pnpm` 9.15.0 directly (it is on PATH). All tests + build ran clean.

## Verification Results
- `pnpm vitest run src/lib/branding-public.test.ts` — 4/4 GREEN (fetch parse, `cache: "no-store"`, non-ok throw, fallback shape).
- `pnpm build` — exits 0; app graph typechecks (async layout + BrandLogo); `/` now `ƒ (Dynamic)` server-rendered on demand.
- `grep -F "--brand-primary" frontend/src/app/globals.css` — 2 matches (`:root` token + `@theme inline` mapping).
- `grep -F "--brand-primary" frontend/src/app/layout.tsx` — matches inside the injected `<style>` block (line 52).
- `grep -F "no-store" frontend/src/lib/branding-public.ts` — matches (per-navigation freshness).
- `grep -F "branding/logo" frontend/src/components/brand-logo.tsx` — matches (logo `<img>` reference with brand-name fallback).
- Manual (carried to `/gsd-verify-work`): change the palette in `/admin/branding`, navigate a player page, confirm the `--brand-*` vars + colors update with no rebuild (ADD-06 / SC#5).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 10 Plan 05 of 5 complete — this is the last plan in Phase 10. With ADD-06 now fully delivered (backend half in 10-01, runtime half here), the phase is functionally complete; ready for `/gsd-verify-work 10` then code review + ship.
- No blockers introduced. The single manual-verify item (live re-skin round-trip) is documented above for the verification step.

## Self-Check: PASSED

- All 3 created files present on disk (branding-public.ts, branding-public.test.ts, brand-logo.tsx) + SUMMARY.md.
- All 3 task commits present in git log (ef14654 test, 5bc7985 feat, 7ab5d1c feat).
- All plan-level verification commands re-run and pass (4/4 vitest, build exit 0, all greps match).

---
*Phase: 10-admin-kpi-dashboard-configurable-branding*
*Completed: 2026-05-31*
