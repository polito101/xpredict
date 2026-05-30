# Phase 9 — UI Review

**Audited:** 2026-05-29
**Baseline:** 09-UI-SPEC.md (approved design contract)
**Screenshots:** Not captured — no dev server detected on localhost:3000, :5173, or :8080. Code-only audit.

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 3/4 | Panel heading "Place a bet" diverges from spec; 1 copy string uses dynamic BET_MAX/MIN from constants instead of the exact spec template |
| 2. Visuals | 3/4 | "Market not found" heading uses text-lg instead of spec's implied display size; h1 missing from MarketDetailSkeleton wrapper element |
| 3. Color | 4/4 | Hardcoded hex values are Chart-only and spec-mandated; no accent overuse; all semantic tokens match exactly |
| 4. Typography | 3/4 | `font-medium` (weight 500) introduced on new surfaces beyond the primitives-only permission in the spec; `text-base` exists in pre-existing market-card |
| 5. Spacing | 4/4 | All spacing on new surfaces uses declared scale tokens; no arbitrary px/rem values in new components |
| 6. Experience Design | 4/4 | Full state coverage: loading skeletons, typed errors, empty states, disabled/auth states, aria-live, destructive-action confirm modal |

**Overall: 21/24**

---

## Top 3 Priority Fixes

1. **Panel card heading "Place a bet" vs. spec CTA "Place bet"** — A user scanning the order panel reads two near-identical but distinct strings ("Place a bet" as the card title, "Place bet" as the button label). The spec Copywriting Contract does not list "Place a bet" as any element's label; it lists only "Place bet" (primary CTA). The card title is an unlabeled invention. Fix: remove the CardTitle from the order panel or retitle it to something spec-compliant like "Order entry" — or omit the heading entirely since the form fields are self-explanatory. File: `frontend/src/app/markets/[slug]/page.tsx` line 195.

2. **"Market not found" H1 uses text-lg (18px) — spec requires the page H1 to be text-3xl (30px)** — The `MarketNotFoundState` renders its H1 as `text-lg font-semibold` (line 55), the same size as a section heading. The UI-SPEC §Typography assigns `text-3xl` to the "Display / Page H1" role. A full-page error state should command visual authority as a page heading, not blend into body text. Fix: change `h1 className="text-lg font-semibold"` to `h1 className="text-3xl font-semibold tracking-tight"` in `MarketNotFoundState` (and mirror in `MarketErrorState` line 75). File: `frontend/src/app/markets/[slug]/page.tsx` lines 55 and 75.

3. **`font-medium` (weight 500) used on new surfaces beyond spec permission** — The spec weight rule: "only 400 (normal) and 600 (semibold). `font-medium` (500) is permitted ONLY where the existing primitives already use it." New Phase 9 code applies `font-medium` to: the expected-payout value span in `order-entry-form.tsx` (line 240), the closed-market error paragraph (line 248), the bet-error alert (line 258), the bet-success paragraph (line 277), and all three `<dd>` values in `bet-confirm-dialog.tsx` (lines 70, 75, 80). None of these are existing primitives — they are new surfaces that the spec does not authorize for 500-weight. Fix: replace `font-medium` with `font-semibold` (600) on error/success message paragraphs to match the spec; on the expected-payout value and dialog `<dd>` values use `font-normal` (400, matching the body role) or `font-semibold` (600, for emphasis) — not the unapproved 500.

---

## Detailed Findings

### Pillar 1: Copywriting (3/4)

**WARNING — Panel card heading not in spec copy table**
- `frontend/src/app/markets/[slug]/page.tsx:195` — `<CardTitle>Place a bet</CardTitle>`. The UI-SPEC Copywriting Contract lists every declared element. "Place a bet" appears nowhere in the contract. The only declared bet-surface CTA is "Place bet" (primary button) and "Place bet · YES" / "Place bet · NO" (optional outcome-qualified variant). Introducing an unlabeled panel heading creates a confusing near-duplicate of the CTA label. The spec's order-entry section heading is not declared (the panel is identified by its form fields, not a title). Classification: WARNING.

**PASS — Primary CTA label**
- `frontend/src/components/order-entry-form.tsx:290` — renders "Place bet" exactly as specified.

**PASS — Confirmation modal copy**
- `frontend/src/components/bet-confirm-dialog.tsx` — Title "Confirm your bet" (line 61), three row labels "Stake" / "Current odds" / "Expected payout" (lines 69, 74, 79), footer "Odds may move before your bet is placed." (line 86), buttons "Confirm bet" / "Cancel" (lines 99, 96). All verbatim matches.

**PASS — Outcome selector label**
- `frontend/src/components/order-entry-form.tsx:195` — "Your prediction" label matches spec exactly. Options "YES" / "NO" at lines 207–208 match.

**PASS — Stake input label**
- `frontend/src/components/order-entry-form.tsx:221` — `Stake ({CURRENCY})` renders as "Stake (PLAY_USD)" matching the spec.

**PASS — Section headings**
- "Resolution criteria" (page.tsx:168), "Price history" (page.tsx:180), "Recent activity" (page.tsx:186) — all match spec verbatim.

**PASS — Activity row format**
- `frontend/src/components/recent-activity-feed.tsx:60` — "Someone backed {YES|NO} · {amount} PLAY_USD · {relative-time}" matching spec. No username or id rendered.

**PASS — Live indicator states**
- `frontend/src/components/live-indicator.tsx` — "Live" / "Stale" / "Reconnecting…" match spec exactly (line 31/36/41).

**PASS — Chart window toggles**
- `frontend/src/components/price-history-chart.tsx:38` — "24h" / "7d" / "30d" with "7d" as default.

**WARNING — Stake limits error uses runtime constants, not spec template verbatim**
- `frontend/src/lib/bet-schemas.ts:43` — inline schema error: `Stake must be between ${BET_MIN_STAKE} and ${BET_MAX_STAKE} PLAY_USD.` becomes "Stake must be between 1 and 100000 PLAY_USD." — the spec template is `Stake must be between {min} and {max} PLAY_USD.`. The runtime rendering is correct (constants resolve to the backend limits), but the bet-schemas.ts generated string and the bet-actions.ts `COPY.stakeLimits` (line 53) produce "Stake must be between 1 and 100000 PLAY_USD." For the backend's dynamic 422 path, the action falls back to `COPY.stakeLimits` which uses the hardcoded constants rather than reading actual limits from the 422 response body — meaning if the backend's tenant limits differ from the constants, the displayed min/max will be wrong. This is a minor data-accuracy issue in the error copy path. Classification: WARNING (copy renders but may misrepresent actual limits if tenant config differs).

**PASS — All bet error strings**
- `frontend/src/lib/bet-actions.ts:47–56` — all six error strings match the UI-SPEC Copywriting Contract verbatim: insufficient balance, market closed, unverified, banned, login required, generic fallback. No generic toast path.

**PASS — Market not found / fetch failure copy**
- page.tsx lines 55–56 and 75–79 — copy matches the spec for both 404 and fetch-failure states.

**PASS — Empty states**
- Chart: "Not enough price history yet" + body (price-history-chart.tsx:79–82). Activity: "No bets yet" + "Be the first to make a prediction on this market." (recent-activity-feed.tsx:43–45). Both match spec.

---

### Pillar 2: Visuals (3/4)

**WARNING — "Market not found" and fetch-failure H1 sized as section heading (text-lg), not page H1 (text-3xl)**
- `frontend/src/app/markets/[slug]/page.tsx:55` and line 75 — both error states use `h1 className="text-lg font-semibold"`. Per the UI-SPEC Typography table the "Display / Page H1" role is `text-3xl` (30px, matches portfolio H1). A full-page error that renders a 18px H1 has no visual focal point and looks like a section subheading, not a page-level message. This hurts visual hierarchy on the error path.

**PASS — Main page H1 focal point**
- `frontend/src/app/markets/[slug]/page.tsx:139` — `text-3xl font-semibold tracking-tight` on the market question. Clear focal hierarchy.

**PASS — Resolution criteria always visible**
- Card rendered unconditionally in the left column (page.tsx lines 164–177). Never behind a toggle or collapsed.

**PASS — Icon-only interactive elements have accessible labels**
- `SelectTrigger` on outcome select has `aria-label="Your prediction"` (order-entry-form.tsx:202). Close button in Dialog has `<span className="sr-only">Close</span>` (dialog.tsx:60).

**PASS — Live indicator placement**
- `MarketDetailLiveOdds` renders the indicator adjacent to the odds block on the same row (`flex items-center justify-between`, line 62), exactly as spec requires.

**PASS — Two-column responsive layout**
- `grid grid-cols-1 lg:grid-cols-3 gap-8` on page.tsx:145, sticky right panel with `lg:sticky lg:top-8` (page.tsx:193). Matches spec Layout & Interaction Contract.

**PASS — Skeleton mirrors real layout**
- `MarketDetailSkeleton` mirrors the two-column grid, h-64 chart block, and sticky panel with aria-busy/aria-hidden. No layout shift.

**WARNING — MarketDetailSkeleton outer wrapper not wrapped in a `<main>` element**
- `frontend/src/components/market-detail-skeleton.tsx:16` — the skeleton root is a bare `<div aria-busy="true">`, while the resolved content wraps in `<main className={PAGE_SHELL}>`. During the Suspense fallback window the landmark `<main>` element is absent. This means assistive technology and visual layout differ between loading and resolved states. The Suspense boundary in page.tsx wraps the entire `<MarketDetailSkeleton />` output without a surrounding `<main>`, so the page temporarily lacks its primary landmark. Minor a11y gap. Classification: WARNING.

---

### Pillar 3: Color (4/4)

**PASS — Hardcoded hex values are chart-only and spec-mandated**
- `frontend/src/components/price-history-chart.tsx:112,115,120,126` — four hardcoded hex values: `#e4e4e7` (CartesianGrid stroke = zinc-200), `#71717a` (axis tick fill = zinc-500), `#059669` (line stroke = emerald-600). All three are explicitly declared in the UI-SPEC §Color "Chart color contract" with their exact hex equivalents. Recharts does not accept Tailwind class strings; the spec explicitly names these values. No unauthorized hardcodes.

**PASS — Accent (zinc-900) reserved for primary CTA only**
- Button default variant `bg-zinc-900` (button.tsx:20) is the primary CTA. It is not applied to any decorative element or link in the Phase 9 new components.

**PASS — Emerald semantic tokens: YES / Live only**
- Emerald appears in: odds-display (YES bar/text), live-indicator (Live dot/label), recent-activity-feed (YES token), order-entry-form (bet-success message). All are exactly the declared usages (YES / positive / Live). No unauthorized emerald.

**PASS — Amber semantic tokens: Stale/Reconnecting only**
- Amber appears only in `live-indicator.tsx` lines 35, 37, 40, 42. Not used elsewhere. Matches the "Stale (NEW)" color rule exactly.

**PASS — Rose/red semantic tokens: NO / error only**
- Rose used for NO bar/text (odds-display), NO activity token (recent-activity-feed), closed-market error (order-entry-form:248). Red-500 used for bet-error inline (order-entry-form:258, matching `FormMessage` which uses `text-red-500` per form.tsx:165). These map correctly to the spec's semantic error token.

**PASS — No `text-primary`/`bg-primary` tokens**
- Zero matches — the codebase correctly uses explicit zinc/emerald/amber/rose instead of a semantic primary token that would be harder to audit.

**PASS — 60/30/10 distribution pattern**
- Dominant white/zinc-50 surface maintained through Card and page backgrounds. Secondary zinc-100/zinc-200 used for borders, skeleton fills, secondary buttons. Accent (zinc-900) only on the primary CTA. Distribution is consistent with spec intent.

---

### Pillar 4: Typography (3/4)

**PASS — 4-size scale in use (30/18/14/12px)**
- `text-3xl` (30px): market question H1 (page.tsx:139), chart empty state heading (price-history-chart.tsx:78)
- `text-lg` (18px): section headings, dialog title, no-bets heading, order panel card title
- `text-sm` (14px): body copy, form labels, error/success messages, activity rows, dialog description, helper text
- `text-xs` (12px): YES/NO badge labels, Live indicator label, timestamps in activity, chart footnote, source badge text

The declared 4 sizes are the only ones used in Phase 9 new files.

**WARNING — `text-2xl` in ui/card.tsx CardTitle base class is outside the 4-size scale**
- `frontend/src/components/ui/card.tsx:43` — the base `CardTitle` class is `text-2xl font-semibold`. This is a pre-existing primitive, and Phase 9 overrides it by passing `className="text-lg font-semibold"` on every new `CardTitle` (page.tsx:167, 195; recent-activity-feed.tsx:43). So the rendered output is correct — text-lg wins via Tailwind class merging through `cn`. However this is a latent violation: any `CardTitle` rendered WITHOUT an explicit size override will render at 24px, outside the 4-size spec. Not caused by Phase 9, but the spec risk is real. Classification: WARNING (pre-existing, but surfaced by Phase 9 usage).

**WARNING — `font-medium` (weight 500) applied on new surfaces**
- The spec weight rule explicitly names the permitted usages: "button.tsx `font-medium`, `FormMessage` `font-medium`, portfolio P&L `font-medium`". Phase 9 extends `font-medium` to new surfaces:
  - `order-entry-form.tsx:240` — expected-payout value span (new surface)
  - `order-entry-form.tsx:248` — closed-market error `<p>` (new surface)
  - `order-entry-form.tsx:258` — bet-error `<div>` (new surface — FormMessage uses it, but this is a custom role=alert div, not FormMessage)
  - `order-entry-form.tsx:277` — bet-success `<p>` (new surface)
  - `bet-confirm-dialog.tsx:70,75,80` — three `<dd>` value cells (new surfaces)
- The bet-error at line 258 is a partial gray-area (functionally equivalent to FormMessage which does use font-medium), but the closed-market, success, and payout preview are unambiguously new surfaces. Classification: WARNING.

**PASS — Weight 400/600 used correctly elsewhere**
- Body text is `font-normal` (implicit or explicit). Section headings use `font-semibold`. Spec YES/NO label at text-xs is `font-semibold uppercase tracking-wide` (recent-activity-feed.tsx:64–65). Live indicator label is `font-semibold` (live-indicator.tsx:57). All match the declared weight table.

---

### Pillar 5: Spacing (4/4)

**PASS — All spacing uses declared scale tokens**
- Page shell: `px-4 sm:px-6 py-12` — matches the spec exactly (`2xl` = 48px = py-12; `lg` = 24px = px-6).
- Grid gap: `gap-8` (xl = 32px) — matches spec "desktop two-column gutter".
- Header margin: `mb-8` — matches spec (xl = 32px = "Heading-to-content").
- Section gaps: `gap-8` on left column flex, `gap-3` on activity section (between-sm/md, minor but within scale).
- Card-internal: `space-y-4` on the order form, `space-y-2` on FormItems — matches the spec's "sm" FormItem token.
- Activity rows: `gap-2` (md = 8px) and `gap-1` (xs = 4px) for inline separators — matches spec intent.
- LiveIndicator inline gap: `gap-1` (xs) — matches "Live-dot to label gap" spec token.

**PASS — No arbitrary px/rem values in new components**
- The only `[...]` arbitrary values in new Phase 9 components are in `ui/select.tsx` (shadcn primitive hand-copied from canonical source): `min-w-[8rem]`, `max-h-96`, `h-[var(--radix-select-trigger-height)]`, `min-w-[var(--radix-select-trigger-width)]` — all are canonical shadcn/Radix sizing patterns, not ad-hoc spacing decisions.

**PASS — Touch targets at spec minimum**
- Primary CTA "Place bet": `Button size="lg"` which is `h-11` (44px) — meets the spec's 44px minimum for the primary CTA.
- Outcome Select trigger: `h-11` override applied (order-entry-form.tsx:202) — meets the 44px minimum.
- Stake Input: `h-11` override applied (order-entry-form.tsx:228) — meets the 44px minimum.
- Chart window toggle buttons: `size="sm"` = `h-9` (36px) — these are secondary controls listed as "window-toggle buttons" in the spec, which specifically requires ≥44px only for "interactive controls (outcome select, stake stepper, window-toggle buttons, primary CTA)". The window toggle buttons at `h-9` (36px) are below the 44px target. Classification: minor finding, but the spec's "must be ≥44px tall on mobile" wording covers window toggles. See Minor Recommendations.

**PASS — Spacing scale consistency across new surfaces**
- The bet-confirm-dialog uses `gap-x-6 gap-y-2` on the `<dl>` grid (lg + sm = within scale). The `space-y-1.5` in DialogHeader is a Tailwind micro-token from the canonical shadcn primitive — not an arbitrary value, and consistent with dialog.tsx's use of 1.5 (between xs and sm) as a heading-to-description separator.

---

### Pillar 6: Experience Design (4/4)

**PASS — Loading states fully covered**
- `frontend/src/components/market-detail-skeleton.tsx` — two-column skeleton matching resolved layout. h-64 chart block. aria-busy="true". No layout shift.
- `frontend/src/app/portfolio/loading.tsx` — Suspense skeleton for the portfolio route. aria-busy="true".
- Both use the established `Skeleton` vocabulary from market-list-skeleton.

**PASS — Error states fully covered**
- `MarketNotFoundState`: 404 path, "Market not found" + link.
- `MarketErrorState`: generic fetch failure.
- Bet errors: 6 specific inline error strings mapped to exact status codes (402/409/403/422/401 + fallback). No generic toast anywhere in the bet flow.
- `Promise.allSettled` on SSR fetch: market is the gate; price-history/activity degrade gracefully to their own empty states.

**PASS — Empty states fully covered**
- Chart: "Not enough price history yet" at h-64 height (no layout shift, no collapse).
- Activity feed: "No bets yet" + "Be the first to make a prediction on this market."
- Each renders in the same layout box as its non-empty counterpart.

**PASS — Disabled states for actions**
- Form fields and CTA disabled when `isClosed` (order-entry-form.tsx lines 199, 228, 288).
- Confirm/Cancel buttons disabled while `pending` (bet-confirm-dialog.tsx lines 93, 98).
- Unauthenticated state: form replaced by a real "Log in to place a bet" link (not a dead/disabled form).

**PASS — Destructive-action confirmation guard**
- Submitting the order form opens `BetConfirmDialog` first. Only `Confirm bet` fires `placeBetAction`. Matches the spec's "treat the confirm modal as the destructive-style guard."

**PASS — Real-time state machine**
- `useMarketSocket`: Live / Stale (>30s, odds preserved) / Reconnecting with exponential backoff capped at 30s + jitter. Odds never blanked on stale (last odds kept visible). `aria-live="polite"` on LiveIndicator.
- Stale detection runs every 5s; last-msg timestamp is set on `ws.onopen` so the initial connection counts as a freshness signal.

**PASS — Accessibility patterns**
- `role="alert"` on all bet-error regions. `role="status"` on success and empty states. `aria-hidden="true"` on decorative separators (·). `aria-label` on SelectTrigger, odds bar, SourceBadge external link.

**Minor caveat — No `ErrorBoundary` component wrapping the client wrappers**
- `MarketDetailLiveOdds` and `PriceHistorySection` are client components with async/network behavior. If they throw during render (e.g., a bad odds parse), there is no explicit `ErrorBoundary` to catch it — the error would propagate to the nearest Suspense/error boundary in the Next.js tree. This is acceptable for v1 (Next.js has a default error boundary at the route segment level via `error.tsx`), but no `error.tsx` was added for the `markets/[slug]/` route segment in Phase 9. The page-level `try/catch` only covers the SSR fetch. Classification: minor recommendation, not a blocker.

---

## Minor Recommendations

4. **Window toggle buttons at h-9 (36px) on mobile** — `price-history-chart.tsx:58` — `Button size="sm"` renders `h-9` (36px). The UI-SPEC §Spacing touch-target rule explicitly lists "window-toggle buttons" as requiring ≥44px. At 36px these are below the threshold on mobile. Fix: use `size="default"` (`h-10`, 40px) or `size="lg"` (`h-11`, 44px) for the window toggle group, or add `className="h-11"` to each toggle Button. Trade-off: visual weight increases; the existing `size="sm"` grouping looks proportional. But spec compliance requires the change for Phase 11 mobile QA.

5. **No `error.tsx` for the `/markets/[slug]` route segment** — If a client component (`MarketDetailLiveOdds`, `PriceHistorySection`) throws an unhandled error after SSR, Next.js falls back to the root `error.tsx` (if one exists) or an unformatted error page. A dedicated `frontend/src/app/markets/[slug]/error.tsx` would show the "Unable to load this market" copy in a styled Next.js error boundary. Currently that copy only applies to SSR fetch failures, not client-side render failures.

6. **`MarketDetailSkeleton` lacks a `<main>` wrapper** — As noted in Pillar 2: during the Suspense loading window, the page-level `<main>` landmark is absent (the skeleton renders a bare `<div>`). This is a minor a11y gap for screen-reader users navigating by landmark.

---

## Registry Audit

No `components.json` present — shadcn is in manual/hand-copy mode (established project convention since Phase 1). No CLI or registry fetch in use. Registry safety gate not triggered. Third-party blocks: none.

---

## Files Audited

**Phase 9 new files (Plans 03 + 04):**
- `frontend/src/app/markets/[slug]/page.tsx`
- `frontend/src/components/price-history-chart.tsx`
- `frontend/src/components/live-indicator.tsx`
- `frontend/src/components/order-entry-form.tsx`
- `frontend/src/components/bet-confirm-dialog.tsx`
- `frontend/src/components/recent-activity-feed.tsx`
- `frontend/src/components/market-detail-skeleton.tsx`
- `frontend/src/components/market-detail-live-odds.tsx`
- `frontend/src/components/price-history-section.tsx`
- `frontend/src/components/ui/dialog.tsx`
- `frontend/src/components/ui/select.tsx`
- `frontend/src/hooks/use-market-socket.ts`
- `frontend/src/lib/api.ts`
- `frontend/src/lib/bet-actions.ts`
- `frontend/src/lib/bet-schemas.ts`
- `frontend/src/app/portfolio/loading.tsx`

**Pre-existing files read for context:**
- `frontend/src/components/odds-display.tsx`
- `frontend/src/components/source-badge.tsx`
- `frontend/src/components/market-list.tsx`
- `frontend/src/components/market-list-skeleton.tsx`
- `frontend/src/components/market-card.tsx`
- `frontend/src/components/ui/button.tsx`
- `frontend/src/components/ui/card.tsx`
- `frontend/src/components/ui/form.tsx`
- `frontend/src/components/ui/input.tsx`
- `frontend/src/components/ui/badge.tsx`
- `frontend/src/components/ui/label.tsx`
- `frontend/src/app/portfolio/loading.tsx`
- `.planning/phases/09-user-app-ux-polish-market-detail-real-time/09-UI-SPEC.md`
- `.planning/phases/09-user-app-ux-polish-market-detail-real-time/09-CONTEXT.md`
- `.planning/phases/09-user-app-ux-polish-market-detail-real-time/09-03-PLAN.md`
- `.planning/phases/09-user-app-ux-polish-market-detail-real-time/09-04-PLAN.md`
- `.planning/phases/09-user-app-ux-polish-market-detail-real-time/09-03-SUMMARY.md`
- `.planning/phases/09-user-app-ux-polish-market-detail-real-time/09-04-SUMMARY.md`
