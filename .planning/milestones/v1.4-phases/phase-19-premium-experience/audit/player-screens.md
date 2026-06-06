# Audit — Player-facing screens & UX

Scope: every player route under `frontend/src/app` that is NOT `/admin`, plus the
presentational + logic-coupled components they compose, and the data contracts
(`lib/api.ts`, `lib/catalog.ts`, `lib/branding-public.ts`) behind them.

Read-only audit for the Phase 19 premium dark-first redesign. All paths are
relative to the repo root (`frontend/...`). No source file was modified.

---

## 0. Global frame (applies to every player screen)

### `frontend/src/app/layout.tsx` — player root layout (async Server Component)
- Fetches `GET /branding/current` on EVERY navigation (`fetchBrandingPublic`,
  `cache:"no-store"`) → `BrandingPublic { brand_name, primary_hex, secondary_hex, logo_url }`.
  Falls back to `DEFAULT_BRANDING` (`#4f46e5` indigo / `#0ea5e9` sky, name "XPredict") on failure.
- Injects `<style>:root{--brand-primary;--brand-primary-foreground;--brand-secondary}</style>`
  in `<head>` from validated hex tokens. `--brand-primary-foreground` is derived by
  `pickReadableForeground(primary_hex)`. **This is the white-label runtime contract — MUST be preserved.**
- Reads HttpOnly `xpredict_session` cookie presence → `isAuthenticated` boolean → `PlayerNav`.
- Renders a hardcoded chrome: `<header class="border-b border-zinc-200 bg-white">` with
  `BrandLogo` + `PlayerNav`, then `{children}`, then a `<footer class="border-t border-zinc-200 bg-white">`
  with Terms of Service / Token policy links + "Play-money tokens have no monetary value." + `Toaster` (sonner).
- Body font: Inter via `next/font/google`, exposed as `--font-sans`.

### `frontend/src/app/globals.css` — the entire visual token system
- `:root` defaults: `--background:#ffffff`, `--foreground:#171717`, brand fallbacks indigo/sky.
- `@theme inline` maps brand tokens to Tailwind utilities (`bg-brand-primary`, `text-brand-primary`, etc.).
- Dark handling is **OS-preference only**: `@media (prefers-color-scheme: dark)` swaps ONLY
  `--background:#0a0a0a` / `--foreground:#ededed`. There is NO `.dark` class strategy, NO
  `@custom-variant dark`, NO `darkMode` config (no `tailwind.config.*` exists; `postcss.config.mjs`
  just loads `@tailwindcss/postcss`). Tailwind v4 default makes `dark:` = `prefers-color-scheme:dark`.

**Critical finding for the redesign:** the app is *light-first*. The thousands of `dark:bg-zinc-950`
/ `dark:text-zinc-400` utilities DO fire under OS dark mode, but the header, footer, and every
shadcn `Card` are **hardcoded light** (`bg-white`, see below) and never invert. So today the app is
neither cleanly light nor cleanly dark — it is light chrome + a partial media-driven dark body. A
dark-first redesign needs an explicit theme strategy (token-driven surfaces, an inverted default,
likely `@custom-variant dark` + a `.dark` class on `<html>`), not the current accidental media behavior.

### Shared visual primitives (the source of the "generic" look)
- `frontend/src/components/ui/card.tsx` — **hardcoded** `bg-white text-zinc-950 border-zinc-200
  shadow-sm` (+ `dark:bg-zinc-950`). Every player surface is a white card. **Pure-presentational, safe to restyle.**
- `frontend/src/components/ui/button.tsx` — `default` variant = `bg-brand-primary
  text-brand-primary-foreground hover:bg-brand-primary/90`; focus ring = `ring-brand-primary`.
  `secondary/ghost/outline` are neutral zinc; `destructive` is red-500. Has `active:scale-[0.97]`.
  **Pure-presentational, brand-token aware, safe to restyle.**
- `frontend/src/components/brand-logo.tsx` — renders operator `<img src="{NEXT_PUBLIC_API_URL}/branding/logo">`
  at `h-7 w-auto` when `logo_url` is set; else a brand-color **dot** + the brand name in zinc ink.
  Prop contract: `{ brandName: string; logoUrl: string|null; className? }`. **Logic-light, but the logo-serving
  mechanism MUST be preserved.** Note: the official angular-X / star-flare logo is ONLY ever shown here, tiny, in the header.
- `frontend/src/components/player-nav.tsx` (`"use client"`) — `{ isAuthenticated: boolean }`.
  Links Markets `/`, Wallet `/wallet`, Portfolio `/portfolio`; active link = `text-brand-primary`,
  inactive = `text-zinc-600 hover:text-zinc-900`. Logout (form action) vs Log in + Sign up (Button).
  **Pure-presentational. No mobile hamburger — links sit inline at all widths.**

---

## 1. Home / catalog browse — `/`

- **File:** `frontend/src/app/page.tsx` (async Server Component) · loading: `frontend/src/app/loading.tsx`.
- **Purpose:** the curated catalog grid (markets + multi-outcome events) with search/filter/sort.
- **Data:** `Promise.allSettled([ fetchCategories(), fetchCatalog({q,category,status,sort}) ])`
  → `GET /api/v1/categories` → `string[]`; `GET /api/v1/catalog?q&category&status&sort` →
  `CatalogItem[]` (bounded 100). `CatalogItem = { type:"market"|"event", id, slug, title, category,
  source, status, deadline, volume, created_at, outcomes: CatalogOutcome[] }`,
  `CatalogOutcome = { label, yes_outcome_id, yes_price }`. Reads URL `searchParams` (shareable filters).
- **Hierarchy:** `<h1>Markets</h1>` (small `text-xl`) → `CatalogControls` → `MarketGrid` of `MarketCard`
  (binary, via `catalogMarketToMarketItem` adapter) + `EventCard` (multi-outcome).
- **Interactions:** `CatalogControls` (`frontend/src/components/catalog/catalog-controls.tsx`,
  `"use client"`): debounced (300ms) search input with `lucide` Search icon, status `Select` (All/Open/
  Closing soon/Resolved), sort `Select` (Volume/Closing soonest/Newest), category chip row (active chip
  = `bg-brand-primary`). Drives URL via `router.replace`; SSR re-fetch per change.
- **States:** empty = `CatalogEmpty` ("No markets found", `role="status"`); fetch error = `CatalogError`
  ("Failed to load markets", `text-rose-700`); loading = `MarketListSkeleton` (6 grey skeleton cards).
- **Cards:** `MarketCard` (`frontend/src/components/market-card.tsx`, Server Component, pure) — stretched-link
  white card, `OddsDisplay` YES/NO bar (`bg-brand-primary` + `bg-zinc-200`), `Vol: $X | deadline`,
  `SourceBadge`. `EventCard` (`frontend/src/components/catalog/event-card.tsx`, pure) — "Event · N outcomes"
  badge + top 4 independent per-outcome YES bars (framing LOCK: never sum-to-100) + "+N more".
- **Animation:** `MarketGrid` (`"use client"`) staggers cards in on mount (y+scale only, never opacity;
  respects `useReducedMotion`).
- **UX/visual/mobile gaps:**
  - No hero, no headline, no value proposition, no featured/trending row — visitors land on a bare
    `text-xl` "Markets" label over a uniform white grid. Zero brand identity, zero "wow".
  - The `<h1>` is `text-xl font-semibold` (smaller than the `text-3xl` H1 on detail/portfolio/wallet) —
    inconsistent type scale and an under-weighted page title.
  - Odds bars are 1.5px tall, monochrome `bg-brand-primary` vs flat zinc — no YES/NO color semantics on
    cards (NO is just grey), no movement/trend cue, no sparkline.
  - Cards are visually identical regardless of source/house/volume — nothing draws the eye to high-volume
    or closing-soon markets.
  - Category chip row scrolls horizontally on mobile (`overflow-x-auto`) but has no fade/scroll affordance;
    filters wrap awkwardly (`flex-wrap` of two 44px Selects + a 72px search) on narrow screens.
  - No skeleton parity for `EventCard` (the list skeleton is binary-card shaped only).

---

## 2. Market detail — `/markets/[slug]`

- **Files:** `frontend/src/app/markets/[slug]/page.tsx` (async Server Component, Suspense + skeleton fallback)
  · `frontend/src/app/markets/[slug]/error.tsx` (route error boundary, `"use client"`, `reset()` + back link).
- **Purpose:** single binary market — odds, chart, criteria, activity, and the bet panel (or resolution panel).
- **Data:** `Promise.allSettled([ fetchMarket(slug), fetchPriceHistory(slug,"7d"), fetchActivity(slug) ])`.
  - `GET /api/v1/markets/{slug}` → `MarketDetail` = `MarketItem` + `{ resolution_criteria, winning_outcome_id,
    resolution_source, resolution_justification, resolved_at, min_stake, max_stake }`. `MarketItem` carries
    `{ id, question, slug, category, source, source_market_id, status, deadline, bet_count, created_at,
    volume, volume_24hr, source_url, outcomes: MarketOutcome[] }`; `MarketOutcome = { id, label,
    initial_odds, current_odds }`. 404 throws typed `MarketNotFound`.
  - `GET /api/v1/markets/{slug}/price-history?window=7d` → `PriceHistoryResponse { window, points:
    PricePoint[] }`; `PricePoint = { ts, probability }`.
  - `GET /api/v1/markets/{slug}/activity` → `ActivityItem[]`; `ActivityItem = { outcome:"YES"|"NO", amount,
    created_at }` (anonymized, no identity).
  - If RESOLVED: server-side cookie-forwarded `GET /bets/me/portfolio` → finds the player's own
    `SettledPosition` (self-scoped) → `myResult`.
- **Hierarchy:** header (`text-3xl` question + `SourceBadge` + `MarketStatusBadge`) → `grid lg:grid-cols-3`.
  LEFT (`lg:col-span-2`): `MarketDetailLiveOdds` (live YES/NO + `LiveIndicator`), category line, ALWAYS-VISIBLE
  "Resolution criteria" Card (trust signal), "Price history" section (`PriceHistorySection` → recharts),
  "Recent activity" (`RecentActivityFeed`). RIGHT: sticky (`lg:sticky lg:top-8`) "Order entry" Card with
  `OrderEntryForm`, OR `MarketResolutionPanel` when RESOLVED.
- **Key interactions:**
  - `OrderEntryForm` (`frontend/src/components/order-entry-form.tsx`, `"use client"`, **logic-coupled**):
    YES/NO `Select` + stake `Input` (`inputMode="decimal"`), live "Expected payout" preview, submit OPENS
    `BetConfirmDialog`; only the dialog's Confirm fires `placeBetAction` (`POST /bets`). Per-status inline
    `role="alert"` errors (no toast); unverified-email error carries a "Resend verification" link.
    Unauthenticated → "Log in to place a bet" affordance. CLOSED → disabled + closed copy.
    Props: `{ marketId, outcomes:OrderEntryOutcome[], marketStatus, isAuthenticated, minStake?, maxStake? }`.
  - `MarketDetailLiveOdds` (`"use client"`): `useMarketSocket(marketId, initialOdds)` → live odds map +
    `ConnState`; renders `OddsDisplay` + `LiveIndicator` (Live=emerald pulse / Stale=amber / Reconnecting=amber pulse).
  - `PriceHistorySection` (`"use client"`): 24h/7d/30d toggle, re-fetches client-side, keeps last good points on error.
  - `BetConfirmDialog` (shadcn Dialog): Stake / Current odds / Expected payout rows + "Odds may move…" note.
  - `BetPlacedSuccess` (`"use client"`): framer spring check + message.
- **States:** not-found = `MarketNotFoundState`; fetch error = `MarketErrorState` (`text-rose-700`) + route
  `error.tsx`; loading = `MarketDetailSkeleton` (mirrors two-column shell, no layout shift); chart <2 pts =
  `ChartEmptyState`; empty activity = "No bets yet — Be the first…".
- **UX/visual/mobile gaps:**
  - The chart (`price-history-chart.tsx`) is hardcoded recharts with light-only axis colors
    (`stroke="#e4e4e7"`, ticks `#71717a`), default white tooltip, a single thin line — **invisible/broken on
    a dark background**. Stroke uses `var(--brand-primary, #059669)` but no gradient fill, no area, no
    glow — flat and generic. This is the biggest visual liability for a premium dark redesign.
  - `OddsDisplay` is the hero number on the page yet is tiny (`text-sm` percentages, `h-1.5` bar) — the
    single most important data point (the probability) has no visual prominence.
  - No price-change indicator (▲/▼ vs 24h), no volume-over-time, no "your position" overlay on the chart.
  - Recent activity is plain grey text rows — no avatars/identicons (intentional anonymization, but it reads
    as lifeless), no live insert animation despite a live socket being present elsewhere.
  - On mobile the order-entry panel falls BELOW the chart/activity (single column) — the primary CTA
    ("Place bet") is far down the page; no sticky mobile bet bar.
  - Resolution panel and order panel both live in a plain white sticky Card — no celebratory "you won"
    moment, no confetti/animation; win is just an emerald chip.

---

## 3. Event detail (multi-outcome) — `/events/[slug]`

- **Files:** `frontend/src/app/events/[slug]/page.tsx` (async Server Component) · `frontend/src/app/events/[slug]/error.tsx`.
- **Purpose:** a multi-outcome event (MarketGroup) with N independent binary children; pick an outcome, bet on it.
- **Data:** `fetchEvent(slug)` → `GET /api/v1/events/{slug}` → `EventDetail { id, slug, title, category,
  source, status: open|partially_resolved|resolved|void, deadline, created_at, outcomes: EventOutcomeRead[] }`;
  `EventOutcomeRead = { label, yes_outcome_id, yes_price, market_id, child_slug, child_status }`. 404 (missing
  or <2 children) throws `EventNotFound`. Then SSR-fetches the default child (highest-YES OPEN) via
  `fetchMarket(child_slug)` + `fetchPriceHistory` so the bet panel is immediately actionable.
- **Hierarchy:** header (`text-3xl` title + `SourceBadge` + `EventStatusBadge`) → category line → `EventDetailView`.
- **Interactions:** `EventDetailView` (`frontend/src/components/event/event-detail-view.tsx`, `"use client"`,
  **logic-coupled**): LEFT = list of `OutcomeRow` buttons (each its OWN YES bar — framing LOCK); selecting one
  client-fetches that child + history and atomically remounts the RIGHT sticky panel (single live socket cap).
  RIGHT panel reuses `MarketDetailLiveOdds` + `OrderEntryForm` + `PriceHistorySection`. `OutcomeRow`
  (`frontend/src/components/event/outcome-row.tsx`, pure): selected row = `border-brand-primary ring-2
  ring-brand-primary`; non-OPEN shows `MarketStatusBadge`.
- **States:** not-found = `EventNotFoundState`; error = `EventErrorState`; loading panel = `opacity-60` +
  `aria-busy`; loading route = `MarketDetailSkeleton`.
- **UX/visual/mobile gaps:**
  - Inherits ALL market-detail chart/odds gaps (same reused components).
  - The outcome list is a stack of identical bordered buttons with 1.5px bars — for a 5–60 outcome event this
    is a wall of grey; no ranking emphasis, no color-coded leader, no "most likely" highlight beyond order.
  - On mobile the outcome list (`lg:col-span-2`) and the sticky bet panel stack — selecting an outcome
    updates a panel far below the tapped row, with no scroll-to or visual link between tap and panel update.
  - Selection feedback is only a brand ring; the panel swap has a faint `opacity-60` but no transition polish.

---

## 4. Portfolio — `/portfolio`

- **Files:** `frontend/src/app/portfolio/page.tsx` (async Server Component) · `frontend/src/app/portfolio/loading.tsx`.
- **Purpose:** the player's OPEN and SETTLED positions.
- **Data:** `loadPortfolio()` → cookie-forwarded `GET /bets/me/portfolio` → `{ open: OpenPosition[],
  settled: SettledPosition[] }`. `OpenPosition = { bet_id, market_id, outcome_id, stake, odds_at_placement,
  potential_payout, potential_pnl }`; `SettledPosition` adds `{ won:boolean, payout, realized_pnl }` (all money
  as strings). Discriminated result: `unauthenticated` / `error` / `ok`.
- **Hierarchy:** `max-w-2xl` (narrower than catalog/detail's `max-w-6xl`) → header (`text-3xl` "Portfolio" +
  subtitle) → "Open positions" section (Cards) → "Settled positions" section (Cards). `PnL` span: gain =
  `text-emerald-600` "+"; loss = NEUTRAL `text-zinc-700` (A-LOSS-NEUTRAL, deliberately not red).
- **States:** `SignedOutNotice` (resource="portfolio"); `RetryError`; per-section empty ("No open positions
  yet." / "No settled positions yet."); loading = skeleton position cards.
- **UX/visual/mobile gaps:**
  - This is a pure data dump — no portfolio summary header (total staked, total open P&L, win rate, # positions),
    no chart, no aggregate "net worth"/play-balance hero. The most motivating screen in a prediction product
    is completely un-gamified.
  - Each position is a generic white Card showing raw fields (`Stake X @ odds`, `Potential payout`) with NO
    link to the underlying market and NO market question/title — the player can't tell WHAT they bet on
    (only `market_id` is present in the data, never rendered). Major UX gap.
  - No tabs/filter between Open and Settled (just two stacked sections that grow unbounded), no sorting.
  - No empty-state illustration or CTA to go bet (the empty state is one grey line).

---

## 5. Wallet — `/wallet`

- **Files:** `frontend/src/app/wallet/page.tsx` (async Server Component) · `frontend/src/app/wallet/loading.tsx`.
- **Purpose:** play balance + transaction history; a disabled "Add funds" (v2 Stripe stub).
- **Data:** `loadWallet()` → `Promise.all([ GET /wallet/me/balance, GET /wallet/me/transactions ])` →
  `{ balance:string, currency:"PLAY_USD", transactions: TransactionItem[] }`. `TransactionItem =
  { kind, amount, direction:"debit"|"credit", created_at, reason:string|null }`. Discriminated result.
- **Hierarchy:** `max-w-2xl` → header (`text-3xl` "Wallet" + subtitle) → Balance Card (balance + currency +
  disabled "Add funds" + "Coming soon") → "Recent activity" list (divided rows: kind + reason | colored amount).
- **States:** `SignedOutNotice`; `RetryError`; empty = "No transactions yet."; loading = balance block + 2 row skeletons.
- **UX/visual/mobile gaps:**
  - The balance — arguably the most-looked-at number in the whole app — is rendered as a default `CardTitle`
    (`text-2xl`) with the currency in grey, in a plain white card. No hero treatment, no big-number typography,
    no brand framing, no sparkline of balance over time.
  - Transaction rows are plain text with credit=emerald / debit=neutral; `kind` is `capitalize`d raw enum
    (e.g. "Bet_placed" shows as "Bet_placed"), no icons per transaction type, no date formatting (raw
    `created_at` is in the data but only `reason` + `kind` render — the date is NOT shown to the user).
  - "Add funds" disabled button + "Coming soon" is a dead end with no explanation of the play-money model here
    (the disclaimer lives only in the global footer).

---

## 6. Auth screens — `/(auth)/*`

- **Layout:** `frontend/src/app/(auth)/layout.tsx` (Server Component) — `min-h-screen flex items-center
  justify-center bg-zinc-50 dark:bg-zinc-950 p-6` wrapping a single `max-w-md` Card (`p-8`). The auth group
  does NOT use the global header/footer chrome differently — it renders inside the root layout, so header/footer
  still appear above/below the centered card.
- **Pages (all server shells + a `"use client"` form using react-hook-form + zod + React 19 `useActionState`):**
  - `/login` — `frontend/src/app/(auth)/login/page.tsx` + `login-form.tsx`. `loginAction`. Shows
    `?registered=1` / `?reset=1` emerald notices. Links to forgot + register.
  - `/register` — `register/page.tsx` + `register-form.tsx`. Email, optional display name, password, confirm.
    `registerAction`.
  - `/forgot-password` — `forgot-password/page.tsx` + `forgot-form.tsx`. Unconditional generic success
    (enumeration mitigation T-02-38).
  - `/reset-password` — `reset-password/page.tsx` (reads `?token=`) + `reset-form.tsx` (hidden token input).
    Missing token → red "Missing or invalid reset link" alert.
  - `/verify-email` — `verify-email/page.tsx` (`"use client"`, `useSearchParams` in Suspense). Auto-calls
    `verifyEmailAction(token)` on mount; loading "Please wait…" / success emerald / error red states.
- **Form fields:** shadcn `Form`/`FormField`/`Input`; submit button is full-width brand-primary with a
  pending label ("Signing in…", "Creating account…", etc.). Errors are `role="alert" text-red-500`.
- **UX/visual/mobile gaps:**
  - Zero brand expression — a generic centered white card on a zinc-50 page. No logo inside the card, no
    product imagery, no split-panel hero, no value-prop copy. This is the FIRST impression for a new user and
    is entirely undifferentiated (looks like every shadcn starter).
  - No password-strength meter on register/reset despite the "at least 12 characters" hint; no show/hide
    password toggle.
  - The `bg-zinc-50` auth background fights the global `bg-white` header — two different "whites" stacked.

---

## 7. System screens — loading / 404 / global-error

- `frontend/src/app/loading.tsx` — homepage route skeleton ("Markets" `text-xl` + `MarketListSkeleton`).
- `frontend/src/app/not-found.tsx` — inside root layout (keeps header/footer): `text-brand-primary` "404"
  eyebrow, `text-3xl` "Page not found", "Back to markets" Button. Pure, safe to restyle.
- `frontend/src/app/global-error.tsx` (`"use client"`) — last-resort boundary; renders its OWN
  `<html>/<body>` with **hardcoded `bg-white text-zinc-900`** + a `bg-brand-primary` "Try again" button.
  **Will look broken in a dark-first redesign** (forced white) — needs token-driven surfaces.
- **Gaps:** these are competent but utilitarian; no brand personality, no illustration. The global-error
  white hardcode is a concrete dark-mode bug for the redesign.

---

## 8. Highest-leverage screens for the premium redesign (+ hero moments)

1. **Home / catalog (`/`)** — first impression, highest traffic, currently the most generic (bare
   `text-xl` label over a white grid). *Hero moment:* a dark, cinematic hero band built around the angular-X
   logo + the bright 4-point star lens-flare at the crossing, an electric-blue/silver gradient, and a
   live "trending markets" rail with animated odds bars — turning the catalog into a destination.
2. **Market detail (`/markets/[slug]`)** — the conversion screen (where bets happen) and the home of the
   chart + odds, both of which are visually broken on dark today. *Hero moment:* an oversized animated
   probability readout with YES/NO semantic color + a premium dark area chart (gradient fill, glow line,
   24h-change badge); a confident sticky bet panel with a satisfying confirm → "bet placed" animation, and
   a celebratory resolved/won state.
3. **Auth (`/login` + `/register`)** — the new-user funnel and the place brand trust is won or lost; today
   a vanilla centered card. *Hero moment:* a split-screen — left a dark brand panel with the X-logo, star
   flare, and a one-line value prop; right the form on a refined dark surface with show/hide + strength meter.
4. **Portfolio (`/portfolio`)** — the retention/engagement screen, currently a context-free data dump with
   no market names. *Hero moment:* a dashboard header with total open P&L / staked / win-rate stat cards and
   a per-position card that names the market, links to it, and color-cues the result — making "how am I doing"
   instantly legible and motivating.
5. **Wallet (`/wallet`)** — the most-glanced number (balance). *Hero moment:* a big-number balance hero in
   brand-framed dark glass, with a balance sparkline and iconified, dated transaction rows.

---

## 9. Constraints the redesign must NOT break (verified in code)

- **White-label runtime branding:** keep `--brand-primary` / `--brand-primary-foreground` /
  `--brand-secondary` injected per-navigation by `layout.tsx` from `GET /branding/current`
  (`fetchBrandingPublic`, `cache:"no-store"`); keep `DEFAULT_BRANDING` fallback; keep the `@theme inline`
  mapping in `globals.css`. Operators re-skin with NO rebuild — do not hardcode the new blue/silver as
  literals where brand tokens belong.
- **Logo serving:** keep `<img src="{NEXT_PUBLIC_API_URL}/branding/logo">` in `brand-logo.tsx` (no
  `next/image`, no inlining the SVG bytes) and the wordmark/dot fallback.
- **Money/odds as strings (SP-1):** never `parseFloat` for storage math; round only for display. Preserve in
  `OrderEntryForm`, `PnL`, `OddsDisplay`, chart, activity.
- **Framing LOCK:** event/multi-outcome bars are INDEPENDENT per-outcome YES bars — NEVER a single bar that
  sums to 100% (`EventCard`, `OutcomeRow`, `event-detail-view`).
- **A-LOSS-NEUTRAL:** a losing P&L renders neutral (zinc), never red (`portfolio/page.tsx`,
  `market-resolution-panel.tsx`).
- **Security/anonymization:** `RecentActivityFeed` must stay identity-free; `justification` stays ESCAPED
  React text (never `dangerouslySetInnerHTML`); session cookie value never crosses to the client (only the
  `isAuthenticated` boolean does).
- **Bet flow gate:** the `BetConfirmDialog` is the irreversible-action gate — submit opens the dialog; only
  Confirm fires `placeBetAction`. Keep that two-step contract.
- **Single live-socket cap** on the event page (one `MarketDetailLiveOdds` mounted at a time).
- **Accessibility:** keep `role="status"/"alert"`, `aria-busy`, `aria-current`, `aria-pressed`, the
  `aria-live` LiveIndicator, ≥44px touch targets (chart window toggle `h-11`), and the readable-foreground
  derivation so a bad operator palette can never make text illegible.
- **Disabled "Add funds"** stub must remain inert (v2 Stripe flag).
- **Discriminated fetch results** (unauthenticated/error/ok) must keep showing distinct states, never degrade
  a failure to a misleading empty/zero.

---

## 10. Reusable assets (restyle, do not duplicate)

- `ui/card.tsx`, `ui/button.tsx`, `ui/skeleton.tsx`, `ui/select.tsx`, `ui/dialog.tsx`, `ui/form.tsx`,
  `ui/badge.tsx`, `ui/separator.tsx`, `ui/sonner.tsx` — the shadcn primitive layer; restyle centrally to
  propagate everywhere.
- `OddsDisplay`, `SourceBadge`, `MarketStatusBadge`, `EventStatusBadge`, `LiveIndicator`, `PnL` (in two
  files — consider consolidating) — the shared semantic-display vocabulary.
- `MarketCard`, `EventCard`, `OutcomeRow`, `RecentActivityFeed`, `MarketResolutionPanel`,
  `SignedOutNotice`, `RetryError`, `BetPlacedSuccess`, `MarketGrid` (entrance animation) — pure/near-pure
  presentational, safe to restyle.
- `MarketListSkeleton`, `MarketDetailSkeleton`, route `loading.tsx` files — keep shapes to avoid layout shift.
- `lib/api.ts`, `lib/catalog.ts`, `lib/branding-public.ts` — the data contracts; redesign is presentational,
  these should not change.
- Logic-coupled (restyle the markup, keep the behavior): `OrderEntryForm`, `EventDetailView`,
  `MarketDetailLiveOdds`, `PriceHistorySection`, `PriceHistoryChart`, `CatalogControls`, `PlayerNav`, the
  five auth forms, `verify-email/page.tsx`.
