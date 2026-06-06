# Phase 19 Audit — Visual System & Design Tokens

Scope: the frontend token layer (Tailwind v4 `@theme`, CSS vars), the shadcn primitive set, the
runtime white-label branding pipeline, and the exact hard-coded color classes that fight a dark
theme. Read-only audit. All paths are relative to repo root unless noted.

---

## 1. Executive summary

The frontend is a **light-mode-first** Tailwind v4 + shadcn ("new-york") system. There is **no
design-token layer beyond two semantic vars** (`--background`, `--foreground`) plus the three
runtime brand vars (`--brand-primary`, `--brand-primary-foreground`, `--brand-secondary`). Surfaces,
borders, text ink, muted text, and inputs are painted with **literal zinc/white utility classes**
(`bg-white`, `bg-zinc-100`, `text-zinc-900`, `border-zinc-200`, etc.), not semantic tokens. Dark mode
exists only as a **CSS `@media (prefers-color-scheme: dark)`** switch that flips `--background` /
`--foreground` — but those two vars are barely consumed (only `body` and a handful of components),
and **most components carry their own `dark:` variant pairs** inconsistently. The result: in OS-dark
the body goes near-black but the **header and footer stay pure white** (no `dark:` on them) and the
brand accent is a generic indigo `#4f46e5`. There is **no identity** — no metallic blue/silver, no
star/lens-flare motif, no premium depth.

A dark-first premium redesign is **very feasible without breaking white-label injection** because the
brand pipeline is cleanly isolated: the server injects `--brand-primary/-foreground/-secondary` into
`:root` per navigation, and components reference them only via `bg-brand-primary` / `text-brand-primary`
/ `ring-brand-primary` (Tailwind v4 `@theme inline` already maps them). The redesign should (a) make
dark the default in `:root` (not behind `prefers-color-scheme`), (b) introduce a proper **semantic
surface/ink token set** (`--surface`, `--surface-elevated`, `--border`, `--muted-foreground`, `--ring`,
`--card`) wired through `@theme inline`, (c) replace the ~440 literal zinc/white utilities with those
tokens, and (d) add the metallic-X identity layer (gradients, glow, star motif) — all **additive** to
the untouched brand-var contract.

---

## 2. How Tailwind v4 + theming is wired (the plumbing)

### 2.1 Build chain
- `frontend/postcss.config.mjs` — single plugin `@tailwindcss/postcss` (Tailwind v4, CSS-first config;
  **no `tailwind.config.js`** exists — everything is in CSS via `@theme`).
- `frontend/next.config.ts` — wrapped in `withSentryConfig`; no design-relevant config. Sourcemaps
  disabled, no Turbopack-specific theming.
- `frontend/src/lib/utils.ts` — the canonical `cn()` = `twMerge(clsx(...))`. Every primitive uses it;
  `tailwind-merge` resolves conflicting utilities last-wins, so a redesign can override component
  classes from the call site cleanly.
- Fonts: `frontend/src/app/layout.tsx` loads **Inter** via `next/font/google` and exposes it as the
  CSS var `--font-sans` (`variable: "--font-sans"`, `display: "swap"`). `globals.css` `body` consumes
  it: `font-family: var(--font-sans), ui-sans-serif, ...`. There is **only one typeface** (Inter) and
  **no display/mono/heading face** — no `--font-display`, no `--font-mono`.

### 2.2 The token surface (`frontend/src/app/globals.css`, 40 lines total)
```css
@import "tailwindcss";
@import "tw-animate-css";   /* provides animate-in/out, fade, zoom, slide keyframes */

:root {
  --background: #ffffff;
  --foreground: #171717;
  --brand-primary: #4f46e5;            /* indigo-600 fallback */
  --brand-primary-foreground: #fafafa;
  --brand-secondary: #0ea5e9;          /* sky-500 fallback */
}

@theme inline {
  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --color-brand-primary: var(--brand-primary);
  --color-brand-primary-foreground: var(--brand-primary-foreground);
  --color-brand-secondary: var(--brand-secondary);
}

@media (prefers-color-scheme: dark) {
  :root { --background: #0a0a0a; --foreground: #ededed; }
}

body {
  background: var(--background);
  color: var(--foreground);
  font-family: var(--font-sans), ui-sans-serif, system-ui, ...;
}
```

Key facts:
- `@theme inline` is the **only** place custom color tokens enter Tailwind. It exposes exactly 5
  color utilities: `background`, `foreground`, `brand-primary`, `brand-primary-foreground`,
  `brand-secondary`. Everything else (`zinc-*`, `red-*`, `emerald-*`, `amber-*`, `rose-*`, `white`,
  `black`) is **Tailwind's stock palette**, used as literals.
- `--background` / `--foreground` flip under `prefers-color-scheme: dark`, but **the brand vars do
  NOT have dark values** — and the dark media query only touches those two vars.
- There is **no `.dark` class strategy** and **no `next-themes`**. `frontend/src/components/ui/sonner.tsx`
  documents this explicitly: "This project uses CSS-only dark mode … there is no `next-themes`
  provider" and hardcodes `theme="system"`. So today dark mode = pure OS preference, no toggle.

### 2.3 The runtime white-label brand pipeline (MUST be preserved)
- **Endpoint:** `GET /branding/current` (public, no auth). Response shape (4 fields, no bytes) per
  `frontend/src/lib/branding-public.ts` `interface BrandingPublic`:
  - `brand_name: string`
  - `primary_hex: string`   (server-validated `^#[0-9a-fA-F]{6}$`)
  - `secondary_hex: string` (same validation)
  - `logo_url: string | null` (backend-relative, e.g. `/branding/logo`)
- **Logo asset:** `GET /branding/logo` served as raw bytes; rendered ONLY via
  `<img src="{NEXT_PUBLIC_API_URL}{logo_url}">` in `frontend/src/components/brand-logo.tsx` (never
  inlined as markup; backend sets `X-Content-Type-Options: nosniff`).
- **Injection point:** `frontend/src/app/layout.tsx` (async Server Component) awaits
  `fetchBrandingPublic()` (`cache:"no-store"` — fresh per navigation) and injects, in `<head>`:
  ```html
  <style>:root{--brand-primary:${b.primary_hex};--brand-primary-foreground:${pickReadableForeground(b.primary_hex)};--brand-secondary:${b.secondary_hex};}</style>
  ```
  This `:root` block overrides the globals.css defaults at runtime. `pickReadableForeground()` lives in
  `frontend/src/lib/brand-color.ts` and returns `#fafafa` or `#18181b` based on WCAG luminance (cutoff
  0.179) — it picks the legible ink for text placed ON the brand color.
- **Fallback:** `DEFAULT_BRANDING` (indigo `#4f46e5` / sky `#0ea5e9`) applies on fetch failure; mirrors
  the `:root` defaults so the UI is never unbranded-broken.
- **Consumption surface:** `bg-brand-primary`, `text-brand-primary`, `border-brand-primary`,
  `ring-brand-primary`, and the CSS var directly (`var(--brand-primary, #059669)` in the charts).
  `--brand-secondary` is mapped but **currently almost unused** in components — a latent slot the
  redesign can adopt for the metallic blue→silver gradient endpoints.

**Constraint for the redesign:** these 3 vars + the 2 endpoints + `pickReadableForeground` + the
`<img src=/branding/logo>` pattern are the white-label contract. Do NOT rename them, do NOT statically
inline brand colors, do NOT move them off `:root`, and keep `cache:"no-store"` so a palette change
re-skins on next navigation.

---

## 3. Current token system, enumerated

| Dimension | Current state |
|-----------|---------------|
| **Background / surface** | `--background` (`#ffffff` light / `#0a0a0a` dark) consumed only by `body`. Surfaces in components are literal `bg-white` (17×), `bg-zinc-50` / `bg-zinc-100` / `bg-zinc-200` (54×). No `--surface` / `--card` / `--popover` token. |
| **Foreground / ink** | `--foreground` (`#171717` / `#ededed`) consumed only by `body`. Component ink is literal `text-zinc-900` / `text-zinc-950` / `text-zinc-700`; muted text is `text-zinc-500` / `text-zinc-400` (357 `text-zinc-*` usages total). No `--muted-foreground` token. |
| **Brand accent** | `--brand-primary` (`#4f46e5` default), `--brand-primary-foreground`, `--brand-secondary` (`#0ea5e9`). Runtime-injected. This is the ONLY real semantic color layer. |
| **Border** | Literal `border-zinc-200` (28×) light / `dark:border-zinc-800`. No `--border` token. |
| **Focus ring** | Two competing idioms: brand ring `ring-brand-primary` (button, cards) and literal `ring-zinc-950` (7×, in input/select/textarea/tabs/dialog/badge). Plus `ring-offset-background` (5×) which references a `background` color **that is not exposed via `@theme`** — `--color-background` exists but `ring-offset-background` expects a `--color-background` utility match; this is a latent inconsistency. |
| **Radius** | No `--radius` token. Literal scale: `rounded-md` (31×, default), `rounded-full` (13×, bars/dots/badges), `rounded-lg` (11×, Card), `rounded-sm` (7×, menu items), `rounded-xl` (3×). |
| **Shadow** | No shadow token. Literal `shadow-sm` (2×, Card resting), `shadow-md` (5×, hover + popovers), `shadow-lg` (3×, dialog/toast). All are Tailwind's neutral gray shadows — invisible/wrong on near-black. |
| **Spacing / layout** | No custom spacing scale. Page shell convention is `w-full max-w-6xl mx-auto px-4 sm:px-6 py-12` (player) / `max-w-6xl` (admin). Card internal padding is `p-6`. Header height `h-14`. |
| **Typography scale** | Inter only, via stock Tailwind `text-*`. Observed scale: `text-2xl` (CardTitle), `text-xl` (page H1), `text-lg` (DialogTitle / section H2), `text-base` (card question), `text-sm` (body/labels), `text-xs` (meta/badges/table heads). Weights: `font-semibold` (headings), `font-medium` (labels/nav), `font-normal`. Tracking: `tracking-tight` (headings/logo), `tracking-wide` / `tracking-wider` (uppercase eyebrows/table heads). **No display face, no fluid/clamp sizes, no letter-spacing tokens.** |
| **Dark mode** | `@media (prefers-color-scheme: dark)` flips only `--background`/`--foreground`. Components self-handle dark via inconsistent `dark:` pairs (259 `dark:` utilities across the codebase). |
| **Motion** | framer-motion 12 present (2 components). `tw-animate-css` provides the Radix enter/exit keyframes. See §6. |

---

## 4. The exact hard-coded classes that fight a dark theme

Counts via ripgrep over `frontend/src/**/*.tsx`:
- `bg-white` — **17** occurrences
- `bg-zinc-50|100|200` — **54**
- `text-zinc-{n}` — **357**
- `border-zinc-200` — **28**
- `ring-zinc-950` (hard focus ring) — **7**
- `dark:` variants present — **259** (so dark is partially handled, but unevenly)

### 4.1 CRITICAL — surfaces with NO `dark:` variant (will stay white in any dark theme)
4 files use `bg-white` with **zero** `dark:` anywhere in the file. The worst offender is the global
chrome:

- `frontend/src/app/layout.tsx`
  - `<header className="border-b border-zinc-200 bg-white">` — **no dark variant**
  - `<footer className="border-t border-zinc-200 bg-white">` — **no dark variant**
  - footer text `text-zinc-500`, links `hover:text-zinc-700` — no dark variant
  - **Effect today:** even in OS-dark the global header/footer are pure white on a near-black body —
    the single most visible break. This is the first thing the redesign must fix.
- `frontend/src/components/brand-logo.tsx` — wordmark `text-zinc-900`, no dark variant.
- `frontend/src/components/player-nav.tsx` — `text-zinc-600 hover:text-zinc-900`, divider
  `bg-zinc-200`, no dark variant (active state correctly uses `text-brand-primary`).
- `frontend/src/components/odds-display.tsx` — eyebrows `text-zinc-500` (no dark), YES value has
  `dark:text-zinc-50` but the NO value `text-zinc-500` does not; NO-bar track is
  `bg-zinc-200 dark:bg-zinc-700` (handled).

### 4.2 Primitives whose **default light branch** is literal (dark handled, but light-first)
These have `dark:` variants but the base class is a light literal — fine for a `.dark`-class strategy,
but they still bake assumptions that a token swap would remove:
- `frontend/src/components/ui/card.tsx` — `bg-white text-zinc-950 border-zinc-200 shadow-sm` +
  `dark:bg-zinc-950 dark:border-zinc-800 dark:text-zinc-50`. **This is the base surface for every
  card/grid/admin panel** — top-priority tokenization target (`--card` / `--card-foreground`).
- `frontend/src/components/ui/input.tsx` — `border-zinc-200 bg-white text-zinc-950 …
  ring-zinc-950` (**no `dark:` at all** — input is light-only).
- `frontend/src/components/ui/button.tsx` — `outline` = `border-zinc-200 bg-white …`,
  `secondary` = `bg-zinc-100 text-zinc-900`, `ghost`/`link` = zinc; **none have `dark:`** (the player
  CTA `default` correctly uses `bg-brand-primary`). So in dark mode every secondary/outline/ghost
  button is a light chip.
- `frontend/src/components/ui/textarea.tsx`, `select.tsx`, `dialog.tsx`, `dropdown-menu.tsx`,
  `tabs.tsx`, `tooltip.tsx`, `table.tsx`, `badge.tsx`, `separator.tsx`, `skeleton.tsx`,
  `sonner.tsx` — all carry `dark:` pairs (the "good" pattern), but every one hardcodes the zinc scale
  and the `ring-zinc-950` focus ring rather than tokens.

### 4.3 Semantic colors (KEEP — they are intentionally not brand-coupled)
- Success: `emerald-*` (bet success `bg-emerald-50/600/700`, live indicator, dark pairs present).
- Warning: `amber-*` (live "Stale"/"Reconnecting").
- Destructive: `red-500` (button destructive, form errors `text-red-500`).
- Error H2: `text-rose-700` (`frontend/src/app/page.tsx` CatalogError — **light-only, no dark**).
These should be preserved as a semantic palette but re-toned for dark legibility.

### 4.4 The generic indigo accent (identity gap)
`#4f46e5` (indigo-600) appears as the brand fallback in: `globals.css` (`--brand-primary`),
`frontend/src/lib/branding-public.ts` (`DEFAULT_BRANDING`), `frontend/src/app/admin/branding/page.tsx`
(seed), and 3 test files. This is the "generic, no identity" accent. The redesign's metallic royal-blue
default would change these **default** values only (the runtime injection path is untouched) — note the
tests assert `#4f46e5`, so changing the default ripples into `brand-color.test.ts`,
`branding-public.test.ts`, `branding-form.test.ts`.

---

## 5. shadcn primitives present and how they're themed

All in `frontend/src/components/ui/` ("new-york" style, `cn` from `@/lib/utils`):

| File | Radix dep | Themed via | Pure-presentational? | Notes for restyle |
|------|-----------|-----------|----------------------|-------------------|
| `button.tsx` | `react-slot` + cva | `bg-brand-primary` (default), zinc (other variants), `ring-brand-primary` focus | Presentational (variants) | Already brand-coupled on default; add dark to secondary/outline/ghost; `active:scale-[0.97]` micro-interaction present. |
| `card.tsx` | none | literal white/zinc + dark pairs | Pure | The base surface. Tokenize first. |
| `badge.tsx` | cva | zinc + dark pairs, `ring-zinc-950` focus | Pure | |
| `input.tsx` | none | literal `bg-white`/`ring-zinc-950`, **no dark** | Pure | Light-only; needs dark + token. |
| `textarea.tsx` | none | zinc + dark pairs | Pure | |
| `label.tsx` | `react-label` | cva, color inherited | Pure | |
| `form.tsx` | `react-hook-form` | error `text-red-500`, desc `text-zinc-500` | **Logic-coupled** (Controller/context) — restyle classes only, do not touch logic | |
| `select.tsx` | `react-select` | zinc + dark pairs, `ring-zinc-950` | Presentational wrapper | |
| `dialog.tsx` | `react-dialog` | overlay `bg-black/80`, content white/zinc + dark; `tw-animate-css` enter/exit | Presentational | `"use client"`. |
| `dropdown-menu.tsx` | `react-dropdown-menu` | zinc + dark pairs | Presentational | `"use client"`. |
| `tabs.tsx` | `react-tabs` | `bg-zinc-100` list, active `bg-white`, dark pairs | Presentational | |
| `table.tsx` | none | zinc heads/rows + dark pairs | Pure | Admin data tables. |
| `tooltip.tsx` | `react-tooltip` | white/zinc + dark, `tw-animate-css` | Presentational | `"use client"`. |
| `separator.tsx` | `react-separator` | `bg-zinc-200 dark:bg-zinc-800` | Pure | |
| `skeleton.tsx` | none | `bg-zinc-100 dark:bg-zinc-800 animate-pulse` | Pure | |
| `sonner.tsx` | `sonner` | hardcoded classNames white/zinc + dark; `theme="system"` | Presentational | Documents the no-`next-themes` decision. |

App-level presentational components (safe to restyle; all reference brand via tokens):
- `market-card.tsx`, `catalog/event-card.tsx` — Card-based, hover `-translate-y-0.5 hover:shadow-md`,
  `focus-within:ring-brand-primary`. Pure presentational (Server Components).
- `odds-display.tsx` — the YES/NO bar; YES segment `bg-brand-primary`, NO `bg-zinc-200`. Pure.
- `source-badge.tsx` (`"use client"`, click-stop logic — mostly presentational), `live-indicator.tsx`
  (semantic emerald/amber, presentational), `brand-logo.tsx` (presentational + brand accent dot).
- Charts: `price-history-chart.tsx` + `admin/volume-chart.tsx` (recharts 3) hardcode axis colors
  `#e4e4e7` grid / `#71717a` ticks but use `var(--brand-primary, #059669)` for the line/area — so the
  **series re-skins with brand but the grid/ticks are light-only** and will be near-invisible on dark.

---

## 6. Motion — current state

- **Library:** framer-motion `^12.40.0` (installed). Used in **exactly 2 components**:
  - `frontend/src/components/market-grid.tsx` — staggered card entrance (`staggerChildren: 0.05`,
    animates `y` + `scale`, **never opacity** for SSR safety), respects `useReducedMotion()`.
  - `frontend/src/components/bet-placed-success.tsx` — spring check + fade-in on bet confirm.
- **Radix/CSS motion:** `tw-animate-css` (`^1.4.0`) supplies the `data-[state=open]:animate-in` /
  `fade`/`zoom`/`slide` keyframes used by dialog, dropdown, select, tooltip.
- **Micro-interactions:** `button.tsx` `active:scale-[0.97]`; card hover `transition-all duration-200
  hover:-translate-y-0.5 hover:shadow-md`; nav `transition-colors`; `animate-pulse` on live dot +
  skeletons.
- **Gap for premium:** no page-transition layer, no logo/lens-flare animation, no shimmer/glow on the
  metallic accent, no scroll/reveal beyond the single grid stagger, no shared-layout transitions. The
  star/lens-flare crossing motif of the logo has **no animated presence** anywhere.

---

## 7. Structural changes a dark-first premium theme requires (without breaking brand injection)

1. **Make dark the default in `:root`** (not behind `prefers-color-scheme`). Move the near-black
   surface + light ink into the base `:root`; if a light variant is still wanted, gate it behind a
   `.light` class or an explicit `prefers-color-scheme: light` block. Keep `body { background/color }`
   reading the vars. **Brand vars stay exactly as-is.**
2. **Introduce a semantic token set** in `:root` and map it through `@theme inline` so utilities exist:
   `--surface` / `--surface-elevated` (→ `--color-surface`…), `--card` + `--card-foreground`,
   `--border`, `--muted-foreground`, `--popover`/`--popover-foreground`, `--ring` (default to
   `var(--brand-primary)`), `--radius`, plus a dark-tuned semantic set (`--success`, `--warning`,
   `--destructive`). This is the layer that does NOT exist today.
3. **Replace literal zinc/white utilities with the new tokens** across ~440 usages — prioritized:
   (a) `layout.tsx` header/footer (the critical white-stay bug), (b) `card.tsx` (base surface),
   (c) `button.tsx` non-default variants + `input.tsx` (light-only), (d) the rest of `ui/*`,
   (e) app components, (f) charts' grid/tick colors (`#e4e4e7`/`#71717a` → CSS var or `currentColor`).
4. **Unify the focus ring** to `ring-[--ring]` (= brand by default), removing the `ring-zinc-950`
   idiom (7×) and fixing the undefined-`background` `ring-offset-background` (5×) by adding a real
   `--color-ring-offset` / using the surface token.
5. **Add the metallic-X identity layer (purely additive):** a royal-blue→silver gradient utility
   (using `--brand-primary` → `--brand-secondary`, which is currently the unused secondary slot), a
   glow/lens-flare treatment for the logo and key CTAs, a near-black layered background (subtle radial
   from the X crossing). Change the **default** brand hexes from indigo `#4f46e5` to the metallic
   royal blue — touching only `globals.css` + `branding-public.ts` `DEFAULT_BRANDING` + the admin seed
   + the 3 tests that assert `#4f46e5`. The runtime injection path, the 4-field `/branding/current`
   contract, `pickReadableForeground`, and the `<img src=/branding/logo>` rendering remain untouched.
6. **Add a display typeface** (`--font-display`) for headings/hero alongside Inter for body, wired the
   same way Inter is (`next/font` → CSS var → `@theme`).
7. **Decide the dark strategy explicitly** — since there's no `next-themes`, a dark-first `:root` with
   no toggle is the lowest-friction path and matches the existing "no manual toggle" decision in
   `sonner.tsx`. If a light/dark toggle is desired later, a `.dark` class strategy + `next-themes`
   would be a follow-on, but is NOT required for dark-first.

---

## 8. Reusable assets (do not duplicate)

- `cn()` (`frontend/src/lib/utils.ts`) — every restyle goes through it; last-wins merge lets the
  redesign override component defaults from call sites.
- The runtime brand pipeline: `lib/branding-public.ts`, `lib/brand-color.ts`, `components/brand-logo.tsx`,
  `app/layout.tsx` injection. Reuse the 3 vars; the **`--brand-secondary` slot is free** for the
  silver/blue gradient endpoint.
- `@theme inline` block in `globals.css` — the one extension point; add new `--color-*` mappings here.
- The shadcn primitive set (17 files) + `tw-animate-css` keyframes — restyle in place, do not re-scaffold.
- The semantic emerald/amber/red/rose palette — re-tone, do not invent a parallel one.
- The existing motion patterns (`useReducedMotion`, SSR-safe non-opacity entrances) — extend, don't
  replace.

---

## 9. Constraints the redesign must NOT break

- Do not rename / remove / statically-inline `--brand-primary`, `--brand-primary-foreground`,
  `--brand-secondary`, or move them off `:root`.
- Keep `GET /branding/current` (4 fields) + `GET /branding/logo` + the `<img>` rendering + the
  `<style>:root{…}</style>` per-navigation injection with `cache:"no-store"`.
- Keep `pickReadableForeground()` deriving the on-brand text color (WCAG luminance), so any operator
  palette stays legible on top of the brand color.
- Preserve accessibility guardrails already in code: brand color never used as the background of
  legibility-critical text (logo wordmark stays ink); `≥44px` touch targets (chart window toggle
  `h-11`); `role="img"` + `aria-label` on odds bars; `aria-live` on toasts/live indicator; reduced-motion
  honoring in `market-grid.tsx`.
- Preserve the per-outcome odds framing LOCK (`event-card.tsx`): independent YES bars, never summing to
  100% across outcomes.
- Keep semantic colors semantic (emerald=success, amber=warn, red=destructive) — not brand-coupled.
- Do not touch the `react-is` pin or chart smoke tests (Recharts-blank-on-React-19 sentinel).
- The default-hex change will break `brand-color.test.ts`, `branding-public.test.ts`,
  `branding-form.test.ts` (they assert `#4f46e5`) — update those tests in lockstep.
