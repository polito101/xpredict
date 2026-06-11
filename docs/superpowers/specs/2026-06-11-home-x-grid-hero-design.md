# Home X-Grid Hero — Design

**Date:** 2026-06-11 · **Status:** Approved (pending spec review) · **Branch:** `gsd/home-x-grid-hero`

## Goal

Replace the current 7-section landing page with a single-viewport, highly visual,
interactive hero. The landing is the "pretty face" for sales demos — minimal text,
maximum visual impact. Concept chosen by Pol after interactive prototyping:
**C′ — particle X over a grid of mini brand-X glyphs, with a click-triggered ripple wave**
(no big-bang explosion).

## What the page becomes

Exactly one screen, zero scroll: the section is `h-[calc(100svh-4rem)]` (header is
`h-16`; svh — not dvh — so the mobile URL bar collapsing never resizes the
hero/canvas) and **SiteFrame renders no footer on `/`** (header stays; footer and
its legal links remain on every other route). The interactivity is the page.

- **Canvas layer** (absolute, full-bleed, `aria-hidden`): the interactive effect.
- **Overlay content** (centered, on top): ONLY the H1 «The core that **connects**
  every prediction market.» (gradient on "connects", `font-display`) and the CTAs.
  With `demoMode` (NEXT_PUBLIC_DEMO_MODE === "true", resolved in the server page —
  same gate as the login page, so the button is absent from white-label builds):
  **Probar la demo** (the PR #43 one-click ephemeral demo session, `DemoLoginButton`
  restyled primary + `glow-brand`, lands in `/markets`) and **Log in** (outline).
  Without demo mode: **Log in** (primary) and **Explore the demo** (outline,
  → `/markets`). No badge, no subtitle, no brand-name copy — the header wordmark
  carries the brand.

## Components

### `frontend/src/app/page.tsx` (rewrite)
Server Component, no backend reads at all. Resolves the demo gate
(`process.env.NEXT_PUBLIC_DEMO_MODE === "true"`) and renders
`<XGridHero demoMode={…} />`. The branding/catalog fetches are removed (the header
wordmark, fed by the root layout, carries the brand).

### `frontend/src/components/home/x-grid-hero.tsx` (new, Server Component)
The hero section: layout, headline, CTA branch; composes the client canvas
component and the PR #43 `DemoLoginButton` (extended with optional size/variant/
className props, defaults unchanged for the login page). The old `brandName`
normalization moved to the shared `lib/brand-name.ts` (used by `BrandLogo`).

### `frontend/src/components/site-frame.tsx` (modify)
Skips the footer when `pathname === "/"` so the landing is one exact screen.

### `frontend/src/components/home/x-particles.tsx` (new, Client Component)
A single `<canvas>` with the full effect. No new dependencies — hand-rolled canvas 2D.

**Mini-X grid (background):**
- Grid of small "×" glyphs (two strokes at ±45°, matching the brand mark), gap ≈ 34px,
  half-length ≈ 4px, rest opacity ≈ 0.16 (near-invisible at rest).
- Cursor within ~110px: glyphs displace away (up to ~12px, eased) and brighten.
- Click/tap: a ripple ring expands from the point (~4.5px/frame, band ~28px). As it
  passes, glyphs displace outward (~16px), brighten, and receive a rotational kick
  (spin that springs back to 0). Multiple concurrent ripples supported.

**Particle X (foreground):**
- ~230 particles with fixed targets sampled along the two diagonal strokes of the X
  (extent ≈ 36% of min(viewport w/h), perpendicular jitter ≈ 13px).
- Spring to target (k ≈ 0.016, damping ≈ 0.88). Cursor within ~90px repels (scatter +
  self-reform). Ripple bands knock particles outward as they pass.
- Network links: lines between particle pairs closer than ~32px (opacity ∝ proximity,
  max ≈ 0.5) — the X reads as a connected circuit, echoing "the core that connects".

**Engineering requirements:**
- Colors read from CSS vars at mount (`--brand-primary` via
  `getComputedStyle`; the line/dot/link tints are lightened derivatives of it), with
  hard-coded indigo fallbacks → white-label re-skinning tints the effect with no
  code change.
- DPR-aware rendering (cap 2). Resize via `ResizeObserver` on the section → rebuild
  grid + retargets the X.
- Pointer handling on the **section** (not the canvas), so events fire even over the
  overlay; mouse + touch. CTA clicks navigate normally (a ripple firing underneath is
  acceptable).
- `prefers-reduced-motion: reduce`: draw one static frame (grid at rest + formed X),
  no rAF loop, no pointer listeners. React to media-query changes.
- Single `requestAnimationFrame` loop; full cleanup on unmount (cancel rAF, remove
  listeners, disconnect observer). rAF implicitly pauses in background tabs.
- SSR-safe: all canvas work in `useEffect`; markup is just `<canvas>` (no hydration
  mismatch). `Math.random` jitter only runs client-side inside the effect.
- Perf envelope: ~230 particles → ~26k pair checks/frame worst case (squared-distance
  early-out, no sqrt on the hot path) — trivial for one canvas; grid loop is O(cells).

## Deletions

- `components/home/hero-band.tsx`, `hero-visual.tsx`, `pillars.tsx`,
  `capability-grid.tsx`, `api-section.tsx`, `demo-showcase.tsx`, `how-it-works.tsx`,
  `landing-cta.tsx`.
- `hv-*` keyframes/classes in `globals.css` that become dead — verify each for usage
  outside `hero-visual.tsx` before removing (e.g. `LogoMark`/`Spark` may use some).
- `MarketCard`/`EventCard`/catalog imports disappear from the landing only — the
  components themselves stay (used by `/markets`).

## Error handling

- Branding fetch failure → `DEFAULT_BRANDING` (existing pattern, unchanged).
- Canvas/2D context unavailable → component renders nothing visual; overlay content
  (H1 + CTAs) is independent and always renders.

## Testing

`frontend` vitest (jsdom — mock `HTMLCanvasElement.getContext`):
- `x-grid-hero` renders H1, badge, and both CTA links with correct hrefs.
- `x-particles` mounts a canvas, starts no loop under mocked
  `prefers-reduced-motion`, and unmounts cleanly (no listener leaks / errors).
- Existing tests referencing deleted components: none found (no tests import the
  removed home sections); landing-related assertions elsewhere must stay green.

## Out of scope

Nav/footer, other routes, `layout.tsx` metadata, admin, backend. No new npm deps.

## Delivery

Branch `gsd/home-x-grid-hero`, atomic commits, one PR. Only Pol merges.
