# Phase 19 Audit — Quality, Tests & Build/Infra Constraints

**Scope:** What CI checks the frontend, how fragile the existing tests are to a restyle, and the guardrails needed so a large dark-first premium redesign keeps CI green. READ-ONLY audit; no source modified.

All paths relative to repo root (`frontend/...`). Worktree: `.claude/worktrees/loving-meitner-387810`.

---

## 1. Test runner setup

**Runner:** Vitest 2.1 (`frontend/vitest.config.ts`).

- `@vitejs/plugin-react` for JSX/TSX transform.
- Path alias `@` → `frontend/src` mirrors `tsconfig.json` (`@/*` → `./src/*`).
- **Dual environment** via `environmentMatchGlobs`:
  - `src/**/*.test.tsx` → `jsdom` (React component tests, RTL).
  - `src/**/*.test.ts`  → `node` (API-route / lib helper tests).
- `globals: true` (no per-file `describe`/`it` import needed, though files import them anyway).
- `include: ["src/**/*.test.ts", "src/**/*.test.tsx"]`.
- `setupFiles: ["./vitest.setup.ts"]`.

**Global setup** (`frontend/vitest.setup.ts`): one line — `import "@testing-library/jest-dom/vitest"` — registers jest-dom matchers (`toBeInTheDocument`, `toHaveTextContent`, `toHaveClass`, `toHaveStyle`, `toHaveAttribute`, ...).

**Libraries:** `@testing-library/react` 16, `@testing-library/user-event` 14, `@testing-library/jest-dom` 6, `jsdom` 25.

**No snapshot tests exist.** `Glob frontend/**/__snapshots__/**` → no files; no `toMatchSnapshot`/`toMatchInlineSnapshot` anywhere. This is GOOD for a restyle — there is no auto-generated DOM/markup snapshot to churn.

**Test count:** 38 test files total (`*.test.ts` + `*.test.tsx`). The task-named sample (market-card, event-card, event-detail-view, order-entry-form, price-history-chart, player-nav, market-resolution-panel, market-status-badge, kpi-card, branding-form, volume-chart, button, catalog-controls, bet-placed-success) was read in full.

---

## 2. Assertion style — how fragile is each kind to a restyle?

Tests fall into three fragility tiers. The dominant style is **text/role/aria** (restyle-safe). A minority assert **classNames / inline styles** (restyle-fragile). There are NO markup snapshots.

### Tier A — RESTYLE-SAFE (text / role / aria / testid). The large majority.
These survive any visual change as long as the literal copy, ARIA labels, roles, `data-testid`s, and `href`s are preserved.
- `market-card.test.tsx` — `getByText("Will ETH hit $5000?")`, `getByText("63%")`, `getByText("Polymarket")`, and one structural `getByRole("img")` with `aria-label="YES 63%, NO 37%"`.
- `catalog/event-card.test.tsx` — `getByRole("link", { name })` + `getByText("Event · 6 outcomes")`, `getByText("+2 more")`, per-outcome `getByText("50%")`.
- `event/event-detail-view.test.tsx` — `getByRole("button", { name: "Alice, 60% YES" })`, `getByTestId("order-form" | "live-odds")` with `toHaveTextContent`. Heavy children are stubbed by `data-testid`.
- `order-entry-form.test.tsx` — `findByTestId("bet-error")`, `getByRole("alert")`, `getByRole("button", { name: "Place bet" | "Confirm bet" })`, `getByLabelText(/stake/i)`, exact inline-copy strings.
- `player-nav.test.tsx` — `getByText("Markets"|"Wallet"|"Log out")`, `toHaveAttribute("aria-current", "page")`.
- `catalog/catalog-controls.test.tsx` — `getByRole("button", { name })`, `getByLabelText("Search markets")`, `toHaveAttribute("aria-pressed", "true")`.
- `bet-placed-success.test.tsx` — `getByRole("status")`, `data-testid="bet-success"`.
- `price-history-chart.test.tsx` (toggle tests) — `getByRole("button", { name: "24h"|"7d"|"30d" })`, `aria-pressed`.

**Implication:** keep the DOM contract — text content, `role`, `aria-label`, `aria-pressed`, `aria-current`, `data-testid`, `<a href>` — and a full visual reskin (colors, spacing, typography, motion, dark mode) does NOT touch these. This is the bulk of the suite.

### Tier B — RESTYLE-FRAGILE (className / inline style / Tailwind class strings). Must be tracked.
These assert SPECIFIC Tailwind utility classes or inline `background-color`. A restyle that changes these classes will turn them red. Enumerated exhaustively:

| File | Line(s) | Asserts | Risk under reskin |
|---|---|---|---|
| `components/ui/button.test.tsx` | 15-16 | `className` contains `bg-brand-primary` + `text-brand-primary-foreground` | HIGH — pins the brand-token classes on the default Button. The reskin MUST keep the default Button consuming `bg-brand-primary`. |
| `components/ui/button.test.tsx` | 22 | default variant `not.toContain("bg-zinc-900")` | MEDIUM — forbids reverting to a hardcoded zinc CTA. |
| `components/ui/button.test.tsx` | 28-29 | destructive variant `not.toContain("bg-brand-primary")` + contains `bg-red-500` | MEDIUM — destructive stays semantic red, not brand. |
| `components/admin/__tests__/market-status-badge.test.tsx` | 36-44 | `toHaveClass("inline-flex","items-center","rounded-full","px-2.5","py-0.5","text-xs","font-semibold")` | HIGH — pins the EXACT chip inset/spacing. Restyling the badge geometry breaks it. |
| `market-status-badge.test.tsx` | 49-52 | OPEN → `toHaveClass("bg-emerald-100","text-emerald-700")` | HIGH — pins status palette (light-mode emerald). A dark-first badge palette WILL break this. |
| `market-status-badge.test.tsx` | 57-60 | RESOLVED → `toHaveClass("bg-zinc-900","text-zinc-50")` | HIGH — same. |
| `market-status-badge.test.tsx` | 65-68 | CANCELLED → `toHaveClass("bg-red-100","text-red-700")` | HIGH — same. |
| `market-status-badge.test.tsx` | 73 | `className="ml-2"` merged via `cn()` | LOW — merge behavior, not visual. |
| `components/admin/kpi-card.test.tsx` | 50, 57, 66 | P&L sign color → `text-red-500` (neg) / `text-emerald-600` (pos/zero) | HIGH — pins semantic money colors. A dark-first KPI palette WILL break this unless these exact classes are retained. |
| `components/__tests__/market-resolution-panel.test.tsx` | 124 | WON P&L `toHaveClass("text-emerald-600")` | HIGH — semantic positive green. |
| `market-resolution-panel.test.tsx` | 133-134 | LOST P&L `toHaveClass("text-zinc-700")` AND `className not match /text-red/` (A-LOSS-NEUTRAL: loss is neutral, never red) | HIGH — pins a deliberate design invariant: a loss must NOT be red. |
| `components/admin/branding-form.test.tsx` | 88-89, 100-102 | swatch `toHaveStyle({ backgroundColor: "#4f46e5" / "#0ea5e9" / "#112233" })` | MEDIUM — inline style from the typed hex value (data-driven, not theme). Survives reskin as long as the swatch keeps `style={{ backgroundColor: value }}`. |
| `components/admin/volume-chart.test.tsx` | 95 | `container.querySelector(".h-64")` not null (empty state same height) | MEDIUM — pins the `h-64` fixed chart box. Don't drop/rename `h-64` on the empty state. |

**The brand-token classes (`bg-brand-primary`, `text-brand-primary-foreground`, `ring-brand-primary`, `border-brand-primary`) are load-bearing AND aligned with the redesign goal** — they ARE the white-label theming hook (see §6). The fragile classes that genuinely constrain the dark redesign are the **status/semantic palettes** (`bg-emerald-100`/`text-emerald-700`, `bg-zinc-900`/`text-zinc-50`, `bg-red-100`/`text-red-700`, `text-red-500`, `text-emerald-600`, `text-zinc-700`) and the **status badge inset spacing**.

### Tier C — STRUCTURAL DOM queries (querySelector on SVG / element tag). Restyle-tolerant but render-sensitive.
- `price-history-chart.test.tsx` 79-84 and `volume-chart.test.tsx` 78-83 — the **react-is sentinel**: `container.querySelector("svg path")` not null + `path.recharts-line-curve` / `path.recharts-area-area` not null. These assert Recharts actually painted (proves the `react-is` pnpm override collapsed to React 19; if mismatched Recharts renders nothing). They depend on the `recharts-line-curve` / `recharts-area-area` CLASS NAMES which Recharts emits internally — NOT on our styling. Safe to reskin the chart container; do NOT swap charting libraries or break the `react-is` override.
- `market-resolution-panel.test.tsx` 108 — `document.querySelector("b")` is null (XSS guard: justification renders as escaped text, never injected HTML). Unrelated to styling; do not start `dangerouslySetInnerHTML` the justification.

---

## 3. The framing-LOCK tests (per-outcome YES bars must NOT sum to 100)

This is a **product-correctness invariant**, not a style rule, and the redesign MUST preserve it. It is enforced by tests AND by component structure. The locked behavior: each event outcome shows its OWN independent YES probability on its OWN bar (YES vs that outcome's OWN NO complement); it is NEVER a single segmented bar normalized to 100% across outcomes.

Tests that assert it:
- `components/catalog/event-card.test.tsx:71-78` — "shows each outcome's OWN YES percent (independent — not summed to 100)": renders 3 outcomes at `0.50 / 0.45 / 0.40` and asserts `getByText("50%")`, `getByText("45%")`, `getByText("40%")` all present (sum = 135% ⇒ proof they are not a normalized distribution). Comment in the test header explicitly states the LOCK.
- `components/event/event-detail-view.test.tsx:98-117` — "renders one independent row per outcome with its own YES % (not summed to 100)": 3 outcomes at `0.60 / 0.40 / 0.20` (sum 120%), asserted via `getByRole("button", { name: "Alice, 60% YES" })` etc.
- `event-detail-view.test.tsx:119-131` — the **WS cap**: exactly ONE live socket on screen (`getAllByTestId("live-odds")).toHaveLength(1)`), targeting the selected child. A redesign that mounts a live-odds widget per outcome row would break this storm-proof cap.

Source that encodes the LOCK (restyle these but keep the semantics):
- `components/event/outcome-row.tsx` — header comment + the bar is `width: ${yesPct}%` of an independent track, `aria-label="${label}, ${yesPct}% YES"` on the button and `aria-label="${label}: ${yesPct}% YES"` on the `role="img"` bar. **This `aria-label` text is asserted verbatim by the EventDetailView test — preserve the exact format `"{label}, {pct}% YES"`.**
- `components/odds-display.tsx` (binary markets) — the YES bar (`bg-brand-primary`, `width: ${yes}%`) and NO bar (`bg-zinc-200 dark:bg-zinc-700`, `width: ${no}%`) DO sum to 100 — but this is a single BINARY market (YES + its own NO), which is correct. The LOCK is about MULTI-outcome events, not binary YES/NO. `role="img"` + `aria-label="YES ${yes}%, NO ${no}%"` is asserted by `market-card.test.tsx:86-93` — preserve that exact aria-label format.

**Guardrail:** when redesigning event/multi-outcome visuals (a likely premium target — fancy bars, sparklines), keep per-outcome bars INDEPENDENT (each its own YES%), never a stacked 100%-normalized bar, and keep the `aria-label` text formats above.

---

## 4. Lint / typecheck / build commands (the exact CI gates)

CI: `.github/workflows/frontend-ci.yml` — runs on PRs/pushes touching `frontend/**`. Ubuntu, Node 20, **pnpm 9.15.0**, `pnpm install --frozen-lockfile`, then in order:

1. `pnpm lint`     → `eslint src`
2. `pnpm typecheck`→ `tsc --noEmit`
3. `pnpm build`    → `next build`
4. `pnpm test`     → `vitest run`

`timeout-minutes: 15`. All four must pass. (`package.json` scripts confirm the exact mappings.)

### Lint (`frontend/eslint.config.mjs`, ESLint 9 flat config)
- `eslint-config-next/core-web-vitals` + `eslint-config-next/typescript` (Next 16 native flat arrays; the old FlatCompat shim was removed because it crashed under ESLint 9.39).
- **One rule downgrade:** `react-hooks/set-state-in-effect` is set to `"warn"` (react-hooks@7 / React Compiler era ships it as ERROR; existing setState-at-effect-start fetch pattern predates it). New redesign code should still avoid setState-in-effect where possible, but it will not fail CI.
- Ignores: `.next/**`, `out/**`, `build/**`, `next-env.d.ts`, `node_modules/**`.
- Lint reskin gotchas: `@next/next/no-img-element` is active — raw `<img>` requires an `eslint-disable-next-line` (see `brand-logo.tsx:55`). The white-label logo MUST stay a raw `<img src=...>` (cross-origin dynamic asset, per-navigation no-store), so keep that disable comment. Unused imports / `any` will fail lint (`@typescript-eslint`).

### Typecheck (`frontend/tsconfig.json`)
- `strict: true`, `noEmit`, `moduleResolution: "bundler"`, `jsx: "react-jsx"`, path alias `@/*`. New components must be fully typed (no implicit any). framer-motion 12, recharts 3.8, lucide-react are all typed deps already in `package.json`.

### Build (`next build`, Next 16.2)
- `frontend/next.config.ts` wraps config with `withSentryConfig`. Sentry source-map upload is DISABLED (`sourcemaps.disable: true`), `tunnelRoute: undefined`, `silent: !process.env.CI`. No `SENTRY_AUTH_TOKEN` needed; the plugin no-ops without it.
- Default `next build` on CI Linux uses Turbopack (Next 16 default) and is GREEN there.

---

## 5. Windows-worktree build caveats (do NOT trust local build/test failures)

Documented and re-verified; codified here so the redesign isn't derailed by phantom local failures:

- **Turbopack build fails on the Windows worktree.** `next build` (Turbopack default) fails locally due to a pnpm symlink-resolution issue interacting with `@sentry/nextjs`. **Workaround for LOCAL verification only: `next build --webpack`.** CI (Linux) runs the default Turbopack build GREEN. Never "fix" a Turbopack-only-on-Windows error by changing config that would break CI.
- **pnpm:** use the standalone/Corepack-pinned **pnpm 9.15.0** ONLY. NEVER `corepack pnpm`/`pnpm@latest` (resolves to 11.x which is destructive: wipes `node_modules`, rewrites the lockfile). The Dockerfile pins `corepack prepare pnpm@9.15.0`; CI uses `pnpm/action-setup@v4 version: 9.15.0`. Local install recipe that works: `corepack pnpm@9.15.0 install --frozen-lockfile`.
- **typecheck/lint/test work fine locally** with pnpm 9.15.0 (`pnpm typecheck`, `pnpm lint`, `pnpm vitest run`). Only the Turbopack BUILD is the Windows problem.
- **react-is pin is load-bearing:** `package.json` has `pnpm.overrides.react-is: "$react-is"` (collapsed to `react-is@19.2.6`). If a dep update or lockfile rewrite breaks this, Recharts renders nothing and the two chart sentinel tests go red. Do NOT let a careless `pnpm install` (wrong pnpm version) rewrite the lockfile.
- **Sentry:** `@sentry/nextjs@^10.53.0`. `instrumentation.ts` (server, `NEXT_RUNTIME === "nodejs"` guard) + `instrumentation-client.ts` (browser) both guard on an empty-string DSN and no-op without one. The redesign does not need to touch Sentry; leave the instrumentation files alone.

---

## 6. White-label runtime branding — what the tests + CSS lock (preserve verbatim)

The redesign MUST keep the runtime branding system. Tests and CSS pin its contract:

- `frontend/src/app/globals.css` — `:root` declares `--brand-primary: #4f46e5`, `--brand-primary-foreground: #fafafa`, `--brand-secondary: #0ea5e9` (the indigo/sky fallback), and `@theme inline` maps them to Tailwind utilities `bg/text/border/ring-brand-primary`, `-brand-primary-foreground`, `-brand-secondary`. **The redesign should re-theme via these tokens (and add dark-mode values), NOT by hardcoding the new logo's royal-blue.** The root layout injects per-navigation `<style>:root{...}</style>` from `/branding/current` to override them — keep that injection point.
- `lib/branding-public.test.ts` pins: `GET /branding/current` returns `{ brand_name, primary_hex, secondary_hex, logo_url }`; fetched with `cache: "no-store"` (per-navigation freshness — a reskin applies on the player's NEXT navigation, never a build-time static cache); non-2xx THROWS so layout falls back; and `DEFAULT_BRANDING === { brand_name: "XPredict", primary_hex: "#4f46e5", secondary_hex: "#0ea5e9", logo_url: null }`. **If the redesign changes the default fallback palette, this test (lines 84-93) must be updated in lockstep — it asserts the exact indigo/sky default.**
- `lib/brand-color.test.ts` pins `pickReadableForeground(hex)`: dark brand → `#fafafa`, light brand → `#18181b`, accepts hash-less hex. This is the WCAG contrast helper that keeps CTA labels legible on any operator brand. Preserve it.
- `components/admin/branding-form.test.tsx` pins the admin branding editor: labels `Brand name` / `Primary color` / `Secondary color` / `Logo`, swatch `data-testid="color-swatch-primary_hex"` / `-secondary_hex` with `style.backgroundColor`, `logo-preview` `<img>`, exact validation/toast copy.
- `components/brand-logo.tsx` — logo served ONLY via `<img src="${NEXT_PUBLIC_API_URL}${logoUrl}">` (`/branding/logo`), never inlined as markup (XSS guard); falls back to a brand-color accent dot + wordmark. The redesign's official "X" logo must flow through this same component / `/branding/logo` path so white-label operators can still override it.

---

## 7. Other CI workflows (not gated by frontend changes, but present)
- `backend-ci.yml` — backend (pytest/ruff/mypy), unaffected by a frontend reskin.
- `security.yml` / `security-scan.yml` — security scans; a reskin should not trip these but avoid introducing `dangerouslySetInnerHTML` or new raw HTML sinks.
- Frontend CI only triggers on `frontend/**` + its own workflow file path — a pure frontend reskin runs exactly the 4 gates in §4.

---

## 8. Guardrail checklist — keep CI green during a large dark-first restyle

**DOM contract (Tier-A tests — preserve, the bulk of the suite):**
- [ ] Keep all asserted **text/copy strings** verbatim (e.g. "Event · N outcomes", "+N more", "Place bet", "Confirm bet", "Not enough play balance…", "No activity yet", "Bet volume — last 30 days", "Why this resolved", "Resolved by Operator", "Settled May 25, 2026", "You didn't bet on this market.").
- [ ] Keep `role` / `aria-*` exactly: `role="img"` odds bars, `role="alert"` bet errors, `role="status"` success, `aria-pressed` on toggles/chips, `aria-current="page"` on active nav.
- [ ] Keep the exact `aria-label` FORMATS: binary `"YES {x}%, NO {y}%"` (OddsDisplay), event outcome `"{label}, {pct}% YES"` (button) and `"{label}: {pct}% YES"` (bar), status badge `"Status: {STATUS}"`, `aria-label={market.question}` stretched link.
- [ ] Keep all `data-testid`s: `bet-error`, `bet-success`, `market-closed`, `order-form`, `live-odds`, `price-history`, `kpi-value`, `kpi-pnl-today`, `kpi-pnl-all-time`, `color-swatch-primary_hex`/`-secondary_hex`, `logo-preview`.
- [ ] Keep `<a href>` targets: `/events/{slug}`, `/markets/{slug}`, `/login`, `/verify-email`, source-badge external links.

**Theming (do it the supported way):**
- [ ] Re-theme through the `--brand-*` CSS variables + Tailwind `*-brand-primary` tokens in `globals.css`; ADD dark-mode token values rather than hardcoding the new logo's royal-blue into components.
- [ ] Keep the default `Button` variant using `bg-brand-primary` + `text-brand-primary-foreground` (button.test.tsx) and `ring-brand-primary` focus ring.
- [ ] Keep destructive `bg-red-500` (never brand). Keep `pickReadableForeground` + `DEFAULT_BRANDING` contract; if you change the fallback palette, update `branding-public.test.ts` lines 84-93 in the SAME PR.
- [ ] Logo only via `<img src=/branding/logo>` through `brand-logo.tsx`; keep the `no-img-element` eslint-disable; do not inline SVG markup from branding.

**Semantic-color / spacing classes that ARE asserted (update test + component together if you must change them):**
- [ ] Status badge palette: OPEN `bg-emerald-100 text-emerald-700`, RESOLVED `bg-zinc-900 text-zinc-50`, CANCELLED `bg-red-100 text-red-700` (market-status-badge.test.tsx). A dark badge restyle requires editing both the component AND these `toHaveClass` assertions in lockstep.
- [ ] Status badge inset: `inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold` (asserted) — change ⇒ update test.
- [ ] Money sign colors: positive/zero `text-emerald-600`, negative `text-red-500` (kpi-card.test.tsx); WON `text-emerald-600`, LOST `text-zinc-700` and **never red** (market-resolution-panel.test.tsx A-LOSS-NEUTRAL). Preserve the "loss is neutral, not red" invariant.
- [ ] Volume-chart empty state keeps a `.h-64` box.

**Product invariants (not negotiable):**
- [ ] Framing LOCK: multi-outcome event bars stay INDEPENDENT per-outcome YES% (never a single 100%-normalized stacked bar). Tests at event-card.test.tsx:71 and event-detail-view.test.tsx:98.
- [ ] WS cap: exactly ONE `live-odds` socket mounted on the event detail (the selected child). Don't mount a live widget per outcome row.
- [ ] Justification renders as ESCAPED text — no `dangerouslySetInnerHTML` (market-resolution-panel.test.tsx:108).
- [ ] Keep `react-is` pnpm override (`$react-is` → 19.2.6) so Recharts paints (`recharts-line-curve` / `recharts-area-area` sentinels). Don't swap charting libs casually.

**Toolchain:**
- [ ] Only pnpm 9.15.0 (`corepack pnpm@9.15.0`), `--frozen-lockfile`. Never `pnpm@latest`/`corepack pnpm` (11.x destroys node_modules + lockfile, breaks react-is).
- [ ] Verify build LOCALLY with `next build --webpack` (Windows worktree Turbopack+Sentry symlink bug); trust Linux CI Turbopack build. Run `pnpm lint && pnpm typecheck && pnpm vitest run` locally — those work on Windows.
- [ ] No new `any` / unused imports (strict TS + next-lint will fail). New animated components (framer-motion) must be fully typed.
- [ ] Don't touch `instrumentation*.ts` / `next.config.ts` Sentry wiring as part of the reskin.
