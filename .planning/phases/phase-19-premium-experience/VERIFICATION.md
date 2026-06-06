# Phase 19 — Premium Experience: Verification

> Frontend-only premium redesign of XPredict on top of v1.2. Branch
> `gsd/phase-19-premium-experience`. Backend / APIs / settlement / catalog /
> white-label runtime branding / backoffice contract: **unchanged**.

## What shipped

A dark-first "Obsidian & Spark" design system + a **platform-first public
landing** (XPredict positioned as a white-label, API-first prediction-market
platform — run native markets, integrate external ones, launch your own), with
the live app moved **behind authentication** and the backoffice premium-restyled
and kept separate at `/admin/*`.

- **Design system:** semantic dark tokens via Tailwind v4 `@theme inline`
  (surface/card/popover/muted/border/ring/radius + gradient/glow/aurora
  utilities); identity primitives `XMark` / `Spark` / `Aurora`; Space Grotesk
  (display) + Inter (body); all 17 shadcn primitives retoned.
- **Landing (`/`):** Hero (node-graph) → Pillars (run/integrate/launch) →
  Capabilities → API section → Demo (real `/catalog` stats + featured) → How it
  works → CTA. Resilient (best-effort backend reads; renders if backend is down).
- **App behind auth:** catalog → `/markets`; edge middleware gates
  `/markets,/events,/portfolio,/wallet` → `/login`; nav splits logged-out vs in;
  login → `/markets`, logout → `/`.
- **Player premium:** market/event detail, oversized live odds, dark gradient
  charts, portfolio performance hero, wallet big-number balance + dated rows.
- **Admin:** dark-first brand-aware shell (no more double header) + tokenized
  backoffice + dark charts.

## Verification (this worktree, pnpm 9.15.0)

| Gate | Command | Result |
|------|---------|--------|
| Typecheck | `pnpm typecheck` (`tsc --noEmit`) | ✅ clean |
| Lint | `pnpm lint` (`eslint src`) | ✅ 0 errors (22 pre-existing warnings) |
| Tests | `pnpm vitest run` | ✅ **194/194** (37 files) |
| Production build | `next build --webpack` | ✅ compiled, 15/15 pages, all routes + middleware |

> The default Turbopack `next build`/`next dev` cannot resolve the `@sentry` /
> some `@radix` pnpm symlinks on this Windows worktree (documented env quirk —
> CI Linux Turbopack is green). The webpack build is the local source of truth;
> visual QA was done by serving that build + Playwright (landing / login /
> admin-login screenshots).

## Invariants preserved (multi-agent adversarial review, 5 lenses — no HIGH/regression)

White-label runtime branding pipeline (brand vars + `@theme` mapping +
`/branding/current` no-store injection + `<img src=/branding/logo>`); money/odds
as STRINGS (display-only parsing); framing-LOCK (independent per-outcome YES bars
+ exact aria-label formats); single live-socket cap; escaped justification
(no `dangerouslySetInnerHTML`); A-LOSS-NEUTRAL (loss neutral, never red); default
Button `bg-brand-primary` + destructive `bg-red-500`. Lockstep test updates:
`player-nav`, `middleware` (+player gating), `auth` (login→/markets),
`market-status-badge`, `market-resolution-panel`.

Review findings (a11y contrast/focus rings, emerald-600→400 on player surfaces,
reduced-motion, /admin boundary, dead tokens, redundant aria) were all applied;
re-verified green.

## Main drift reconciled (v1.3 Live-Bets)

While this phase was in flight, `main` advanced (v1.2 milestone archival + the
**v1.3 Live-Bets demo**). Merged `origin/main` into the branch:
- `player-nav` conflict resolved: kept the Phase 19 redesign + **added the "Live"
  destination**; test merged.
- The new **`/live`** route (v1.3) was restyled to the Obsidian dark system and
  added to the auth gate (it is trading → behind auth, like the rest of the app).
- `api.ts` / `live-actions.ts` / `live/*` taken from main. **238/238** frontend
  tests green; webpack build green (16 routes incl. `/live`).

## CI status (PR #33)

- ✅ **`frontend`** — PASS (CI Linux). This phase's deliverable is green.
- ✅ security / pip-audit / pnpm-audit / bandit / gitleaks — PASS.
- ❌ **`backend`** — RED, but **pre-existing on `main`, NOT from this PR** (which
  is frontend-only). Confirmed: the "Merge gsd/livebets-demo → main" run already
  failed `backend-ci`. Two pre-existing v1.3 Live-Bets backend issues:
  1. **Ruff format** on the 5 `livebets` files — **fixed here** (pure formatting,
     no logic) so the check could proceed.
  2. **Divergent alembic migration tree** — `0011_livebets_bridge` and
     `0011_phase13_market_groups` BOTH chain from `0010` ⇒ two heads ⇒
     `test_migration_0011` fails. **Deliberately NOT touched** (backend migration
     architecture + a v1.3 "LOCKED" chaining decision + not locally validatable on
     this Windows worktree; the mandate is to keep the backend intact). Resolution
     is a backend/v1.3 owner call (an `alembic merge` migration, or re-point
     `0011_livebets_bridge` onto the v1.2 head + update the test).

## Status

**Frontend MERGE READY** — `frontend` CI green, all invariants preserved, review
clean. The PR's only red is the **pre-existing v1.3 backend migration-tree
conflict on `main`** (unrelated to this frontend work). Full-green + merge needs
that backend fix on `main` (backend owner / Pol), after which this branch — which
already merged `main` — goes green. Only Pol merges.
