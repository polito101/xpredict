# Phase 11 — Deferred / out-of-scope items (logged during execution)

## DEF-FE-BUILD-01 — `pnpm build` fails on pristine HEAD (Turbopack + pnpm symlink resolution, Windows)

**Discovered:** 2026-06-02, during plan 11-04 Task 2 verification.

**Symptom:** `pnpm build` (Next.js 16.2.6 Turbopack) exits 1 with 10
`Module not found` errors:

- `@radix-ui/react-dialog`, `@radix-ui/react-dropdown-menu`, `@radix-ui/react-label`,
  `@radix-ui/react-select`, `@radix-ui/react-separator`, `@radix-ui/react-tabs`,
  `@radix-ui/react-tooltip`
- `@sentry/nextjs` (x3 — instrumentation.ts / instrumentation-client.ts / sentry-test route)

**Root cause (evidence):** The packages ARE present in `node_modules` (verified
`node_modules/@sentry/nextjs` and `node_modules/@radix-ui/react-*` exist) and ARE
declared in `frontend/package.json`. `pnpm typecheck` (`tsc --noEmit`) exits 0.
The same 10 errors reproduce on the **clean committed HEAD** (both layouts reverted
to their pre-11-04 state) — i.e. the failure exists independently of plan 11-04's
two `next/link` footer edits. This is the documented pnpm-symlink / Turbopack module
resolution issue on Windows (`node_modules/.pnpm` store not resolved by Turbopack),
the same class of false module-not-found that CLAUDE.md flags for the PMS project.

**Why out of scope for 11-04:** Plan 11-04 is a markup-only footer + docs scaffold.
The errors are entirely in unrelated files (Sentry instrumentation + shadcn UI
primitives) that 11-04 never touches. Phase 11 CONSTRAINT 1/3 forbid refactors and
architecture changes; touching the toolchain or lockfile to chase this would violate
scope. Per the executor SCOPE BOUNDARY rule, pre-existing failures in unrelated files
are logged here, not fixed.

**11-04 gate satisfied via typecheck:** Plan 11-04 Task 2 acceptance criteria
explicitly anticipate an out-of-scope build-graph problem (cites DEF-FE-01) and pin
the real gate to "both layouts are type-clean." `pnpm typecheck` exits 0 with the
footer edits applied, confirming both layouts compile cleanly.

**Owner / next step:** Frontend/CI track (not plan 11-04). Likely needs a Turbopack
resolution fix, a clean `pnpm install` on a non-symlink-hostile FS, or running the
build inside CI's Linux environment (frontend CI is green on Linux per 11-CONTEXT).
Do NOT alter the lockfile to work around it without Pol's sign-off.
