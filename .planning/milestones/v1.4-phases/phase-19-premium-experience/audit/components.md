# Phase 19 Audit — Reusable Component Inventory (non-admin)

Scope: `frontend/src/components/` top level + `catalog/` + `event/` + `ui/`.
Excludes `admin/` (separate surface). READ-ONLY audit — no source modified.

All paths are relative to repo root `frontend/`. Line refs valid as of this audit.

---

## 0. Theming backbone (read this first — it constrains every restyle)

The whole UI is wired to a **white-label runtime brand system** that MUST be preserved:

- `src/app/globals.css` (Tailwind v4, `@theme inline`):
  - `:root` defines `--brand-primary: #4f46e5` (indigo fallback), `--brand-primary-foreground: #fafafa`, `--brand-secondary: #0ea5e9` (sky fallback).
  - `@theme inline` maps them to Tailwind utilities: `--color-brand-primary`, `--color-brand-primary-foreground`, `--color-brand-secondary` → enables `bg-brand-primary`, `text-brand-primary`, `border-brand-primary`, `ring-brand-primary`.
  - Dark mode today is **CSS-media only**: `@media (prefers-color-scheme: dark)` flips `--background`/`--foreground` (and only those). **There is no `.dark` class toggle and no `next-themes`.** This is a key limitation for a "dark-first" redesign — see §Limitations.
  - `body` font is `var(--font-sans)` (Inter, loaded in layout).
- `src/app/layout.tsx` (async Server Component): awaits `fetchBrandingPublic()` on **every navigation** (`cache:"no-store"`) and injects an inline `<style>:root{--brand-primary:…;--brand-primary-foreground:…;--brand-secondary:…}</style>` from server-validated hexes (line 75). A `pickReadableForeground()` derives the foreground. Fallback to `DEFAULT_BRANDING` on fetch failure.
- `src/lib/branding-public.ts`: **`GET /branding/current`** → `BrandingPublic { brand_name: string; primary_hex: string; secondary_hex: string; logo_url: string | null }`. No bytes. `DEFAULT_BRANDING = { brand_name:"XPredict", primary_hex:"#4f46e5", secondary_hex:"#0ea5e9", logo_url:null }`.
- Logo is served as a raw `<img src={NEXT_PUBLIC_API_URL + logoUrl}>` (backend asset on a different origin; `next/image` deliberately NOT used). Path is `/branding/logo`.

**Restyle invariant:** never hardcode the accent. Any "premium accent" (royal blue / silver) must flow through `--brand-primary` / `--brand-secondary` (or new tokens layered alongside) so an operator palette still re-skins. `--brand-secondary` is currently DEFINED but barely used — it's a free lever for the redesign.

Only 5 files touch `--brand-primary` today: `ui/button.tsx`, `price-history-chart.tsx`, `brand-logo.tsx`, `admin/volume-chart.tsx`, `app/layout.tsx`. Bar fills use the Tailwind `bg-brand-primary` utility (market-card, odds-display, event-card, outcome-row, catalog chip).

---

## 1. Per-outcome framing LOCK (Phase 17 invariant) — where it lives

**Invariant:** in multi-outcome events, each outcome shows its OWN independent YES probability on its OWN bar. Bars NEVER sum to 100% across outcomes. A binary market's single bar is YES vs its own NO complement only.

Appears in (any restyle of these bars MUST keep each bar independent — do not introduce a single stacked/segmented 100% bar):
- `catalog/event-card.tsx` (lines 64–98): one `<li>` per outcome, each its own `bg-brand-primary` fill `style={{ width: \`${pct}%\` }}` over a `bg-zinc-200` track. Comment at line 65: "Each outcome's OWN YES probability on its OWN bar — never summed."
- `event/outcome-row.tsx` (lines 50–60): identical idiom, comment "This outcome's OWN YES bar — independent, never a cross-outcome sum."
- `event/event-detail-view.tsx` (lines 104–119): renders the LEFT column as a list of independent `OutcomeRow`s; comment "never sum-to-100."
- `odds-display.tsx` (binary): a two-segment bar (`yes%` brand + `no%` zinc) that DOES sum to 100 — this is the *binary* YES/NO split and is correct/allowed; it is NOT the multi-outcome case the lock forbids.

---

## 2. Top-level components (`src/components/*.tsx`)

### market-card.tsx — `MarketCard`
- Purpose: binary market tile in the catalog grid. Question (stretched `Link` to `/markets/{slug}`), YES/NO odds bar, volume + deadline, source chip.
- Props: `{ market: MarketItem }`. `MarketItem` (lib/api.ts): `id, question, slug, category, source, status, deadline, bet_count, created_at, volume, volume_24hr, source_url, outcomes: MarketOutcome[]`. `MarketOutcome { id, label, initial_odds, current_odds }` (odds are STRINGS, SP-1).
- Type: **Pure-presentational Server Component** (no `"use client"`). Derives `primaryPercent` from the YES outcome (case-insensitive). **Restyle-safe.**
- Current visual: `Card` (white/zinc-950 dark, `rounded-lg border-zinc-200 shadow-sm`), `hover:-translate-y-0.5 hover:shadow-md`, `focus-within:ring-2 ring-brand-primary`. Title `text-base font-semibold line-clamp-3`. Footer `text-sm text-zinc-500`. Composes `OddsDisplay` + `SourceBadge`. **Visual backbone — the single most-repeated unit on the home page.**

### market-grid.tsx — `MarketGrid`
- Purpose: responsive grid wrapper (`grid-cols-1 sm:2 lg:3`, `gap-4`) + framer-motion staggered entrance.
- Props: `{ children: React.ReactNode }`.
- Type: **Client Component**, layout + animation only; logic-light. **Restyle-safe** (changing grid/gap is safe). Note the deliberate constraint: entrance animates `y`+`scale` ONLY, never `opacity` (cards stay visible if JS is slow) and respects `useReducedMotion`. Keep that contract if reworking motion.
- Current visual: 3-col grid, 0.05s stagger, 0.3s easeOut item entrance.

### odds-display.tsx — `OddsDisplay`
- Purpose: canonical binary YES/NO renderer — labels + percentages + a single proportional 2-segment bar.
- Props: `{ yes: number; no: number }` (already-rounded percents).
- Type: **Pure-presentational Server Component.** **Restyle-safe.** Reused verbatim by `market-card` AND `market-detail-live-odds`.
- Current visual: YES brand-weight, NO muted zinc-500; bar `h-1.5 rounded-full`, YES = `bg-brand-primary`, NO = `bg-zinc-200 dark:bg-zinc-700`. `role="img"` w/ aria-label. **Visual backbone — the "odds" gesture of the whole product.** A premium redesign should make this bar feel alive (gradient/glow on YES, etc.) while keeping the prop contract and the brand token.

### order-entry-form.tsx — `OrderEntryForm`
- Purpose: the bet ticket (MKT-03). Outcome `Select` (YES/NO) + stake `Input` + expected-payout preview + submit → opens `BetConfirmDialog` → fires `placeBetAction` server action.
- Props: `{ marketId: string; outcomes: OrderEntryOutcome[]; marketStatus: string; isAuthenticated: boolean; minStake?: string|null; maxStake?: string|null }`. `OrderEntryOutcome { id; label:"YES"|"NO"; current_odds:string }`.
- Type: **Heavily logic-coupled Client Component** — react-hook-form + zod + `useActionState`, server action, dialog orchestration, per-market stake bounds. **Restyle the markup/classes only; do NOT touch the form/action wiring.** Unauthenticated state renders a "Log in to place a bet" CTA (not a dead form); closed state disables with copy.
- Current visual: vertical `space-y-4`; `h-11` inputs/select; inline `role="alert"` errors (red), no toast; full-width `Button size="lg"`. Right-rail panel — second visual backbone (this is where conversion happens; worth elevating into a premium "ticket").

### bet-confirm-dialog.tsx — `BetConfirmDialog`
- Purpose: irreversible-action confirm modal — Stake / Current odds / Expected payout rows + "Odds may move…" note + Confirm/Cancel.
- Props: `{ open; onOpenChange; stake:string; yesPct:number; noPct:number; payout:string; onConfirm:()=>void; pending?:boolean }`. Fully parent-controlled.
- Type: **Presentational Client Component** (wraps shadcn `Dialog`; parent owns all state/action). **Restyle-safe.**
- Current visual: shadcn dialog (white/zinc-950, `max-w-lg`, `bg-black/80` overlay). `<dl>` two-col grid. Outline Cancel + default Confirm buttons.

### bet-placed-success.tsx — `BetPlacedSuccess`
- Purpose: post-confirm success line — spring-animated check + message.
- Props: `{ message: string }`.
- Type: **Presentational Client Component** (framer-motion). **Restyle-safe.** Note: emerald is SEMANTIC success, intentionally NOT the brand color — keep that distinction.
- Current visual: `bg-emerald-50 / dark:bg-emerald-950/30`, emerald check badge, `role="status"`.

### price-history-chart.tsx — `PriceHistoryChart`
- Purpose: Recharts YES-probability line chart + 24h/7d/30d window toggle. YES line ONLY (NO is the complement, not plotted).
- Props: `{ points: PricePoint[]; window: PriceWindow; onWindowChange:(w)=>void }`. `PricePoint { ts:string; probability:string }`; `PriceWindow = "24h"|"7d"|"30d"`. Controlled component (parent owns window).
- Type: **Logic-coupled Client Component** (Recharts; React-19 `react-is` pin gotcha; `<2 points` empty state; fixed `h-64` to stop ResponsiveContainer collapse). **Restyleable but carefully** — colors/axes/tooltip are inline literals (`CartesianGrid stroke="#e4e4e7"`, axis ticks `#71717a`, line `stroke="var(--brand-primary, #059669)"`). These hardcoded greys are LIGHT-MODE-ONLY and will look wrong on near-black; this is a concrete dark-first fix point. Keep the `h-64` and `<2` empty-state contract.
- Current visual: light grid, brand-token line, ghost/secondary window buttons (`h-11`).

### price-history-section.tsx — `PriceHistorySection`
- Purpose: thin client bridge owning the chart's window state + client re-fetch (`fetchPriceHistory(slug, window)`); SSR seeds initial 7d points.
- Props: `{ slug:string; initialPoints:PricePoint[]; initialWindow?:PriceWindow }`.
- Type: **Logic-only Client wrapper** (no own markup beyond `PriceHistoryChart`). **No restyle surface** — style the chart, not this.

### market-detail-live-odds.tsx — `MarketDetailLiveOdds`
- Purpose: live-odds block on the detail page — subscribes `useMarketSocket`, renders `OddsDisplay` + `LiveIndicator`, updates in place.
- Props: `{ marketId:string; yesOutcomeId:string; noOutcomeId:string; initialOdds: Record<string,string> }`.
- Type: **Logic-coupled Client Component** (websocket hook; explicit-NO-vs-complement handling WR-06). **Restyle the wrapper layout only**; reuses `OddsDisplay` for the bar. The "Live odds" header + indicator cluster is a premium opportunity (real-time pulse).
- Current visual: `text-xs uppercase tracking-wide text-zinc-500` header + `LiveIndicator`, then `OddsDisplay`.

### live-indicator.tsx — `LiveIndicator`
- Purpose: connection-state dot + label (live/stale/reconnecting).
- Props: `{ state: ConnState; className?:string }` (`ConnState` from use-market-socket).
- Type: **Pure-presentational Client Component** (state owned by hook). **Restyle-safe** (it's a config map at lines 25–44).
- Current visual: emerald pulsing dot "Live", amber solid "Stale", amber pulsing "Reconnecting…". `aria-live="polite"`. Uses semantic emerald/amber (not brand). A small but high-signal "premium" element (the pulsing live dot is brand-able energy).

### recent-activity-feed.tsx — `RecentActivityFeed`
- Purpose: anonymized last-20 bets — "Someone backed {YES|NO} · {amount} PLAY_USD · {relative-time}".
- Props: `{ items: ActivityItem[] }`. `ActivityItem { outcome:"YES"|"NO"; amount:string; created_at:string }` (NO identity field — anonymity is structural).
- Type: **Pure-presentational Server Component** (own `relativeTime` helper). **Restyle-safe.** Empty state "No bets yet".
- Current visual: plain `<ul>` text rows, `text-sm text-zinc-600`, YES emerald / NO rose tokens, `·` separators. Currently very flat — a clear candidate for premium treatment (ticker/feed energy) but keep anonymity + the YES/NO semantic colors.

### source-badge.tsx — `SourceBadge`
- Purpose: market provenance chip — "Polymarket" (links to source_url, new tab) / "House" / fallback.
- Props: `{ source:string; sourceUrl?:string|null }`.
- Type: **Client Component** (only for `stopPropagation` so the chip doesn't trigger the card's stretched link). Presentational otherwise. **Restyle-safe.**
- Current visual: zinc secondary chip for Polymarket, near-black/inverted chip for House. Wraps shadcn `Badge`.

### retry-error.tsx — `RetryError`
- Purpose: non-silent fetch-failure state w/ `router.refresh()` retry.
- Props: `{ title:string; message?:string }`.
- Type: **Client Component** (router). Presentational shell. **Restyle-safe.**
- Current visual: `border-zinc-200 bg-zinc-50` panel, outline "Try again". `role="alert"`.

### signed-out-notice.tsx — `SignedOutNotice`
- Purpose: signed-out gate for private surfaces (wallet/portfolio) instead of a misleading empty state.
- Props: `{ resource:string }`.
- Type: **Pure-presentational Server Component.** **Restyle-safe.**
- Current visual: same `border-zinc-200 bg-zinc-50` panel idiom as RetryError + a "Log in" button. `role="status"`.

### market-list-skeleton.tsx — `MarketListSkeleton`
- Purpose: 6-card loading grid matching `MarketCard` dims.
- Props: none.
- Type: **Pure-presentational Server Component.** **Restyle-safe** — but MUST stay dimensionally in sync with the new MarketCard to avoid layout shift.
- Current visual: 6 `Card`s of `Skeleton` blocks, same grid as MarketGrid.

### market-detail-skeleton.tsx — `MarketDetailSkeleton`
- Purpose: two-column detail-page skeleton (title, criteria card, `h-64` chart box, activity, sticky order panel) — no layout shift.
- Props: none.
- Type: **Pure-presentational Server Component.** **Restyle-safe** — keep the `h-64` chart box + the `PAGE_SHELL` mirror.
- Current visual: `Skeleton` blocks in the resolved detail-page grid (`max-w-6xl`, `lg:grid-cols-3`).

### brand-logo.tsx — `BrandLogo`  ⚠ branding-coupled
- Purpose: header logo/wordmark from the same `/branding/current` payload.
- Props: `{ brandName:string; logoUrl:string|null; className?:string }`.
- Type: **Server Component**, branding-coupled. **Restyleable but with care:** the `<img src=/branding/logo>` path is a security/runtime contract (T-10-02 — never inline SVG markup) and the wordmark keeps zinc ink with brand only as an accent dot (A-PALETTE #4: a bad operator palette must never make the wordmark unreadable). Preserve both. This is where the official angular "X" logo asset will surface in production.
- Current visual: `<img className="h-7 w-auto">` when `logoUrl`, else `bg-brand-primary` accent dot + `text-base` wordmark; links to `/`.

### player-nav.tsx — `PlayerNav`
- Purpose: primary nav (Markets / Wallet / Portfolio) + auth actions (Log out OR Log in/Sign up).
- Props: `{ isAuthenticated: boolean }` (resolved server-side from cookie presence).
- Type: **Client Component** (`usePathname` for active link; `logoutAction` form). Logic-light. **Restyle-safe** for classes/active state.
- Current visual: text links, active = `text-brand-primary`, inactive `text-zinc-600 hover:text-zinc-900`; `Button size="sm"` Sign up. Lives in the white `header` (layout.tsx). The header/nav is a top-priority premium surface (first thing seen).

### market-resolution-panel.tsx — `MarketResolutionPanel`
- Purpose: RESOLVED block in the detail-page right column (replaces the order panel) — winning outcome chip, source attribution, settled date, justification, and the logged-in player's Won/Lost + payout + realized P&L.
- Props: `{ winningOutcomeLabel:string|null; resolutionSource:string|null; justification:string|null; resolvedAt:string|null; sourceUrl?:string|null; source:string; myResult: ResolutionResult|null; isAuthenticated:boolean; operatorName?:string|null }`. `ResolutionResult { bet_id, market_id, outcome_id, stake, odds_at_placement, won, payout, realized_pnl }`.
- Type: **Pure-presentational Server Component** (composes Card + Separator + SourceBadge). **Restyle-safe**, but keep two contracts: justification rendered as ESCAPED React text (NEVER `dangerouslySetInnerHTML`, T-12-12) and **A-LOSS-NEUTRAL** — a loss renders neutral zinc, NOT red (only gains are emerald-with-`+`). `won` chip is emerald, else neutral.
- Current visual: sticky `Card`, status chip, zinc copy, emerald/neutral P&L.

---

## 3. Catalog subdirectory (`src/components/catalog/*`)

### catalog/event-card.tsx — `EventCard`  🔒 framing LOCK
- Purpose: catalog tile for a multi-outcome EVENT — "Event · N outcomes" badge + top 2–4 outcomes each with own independent YES bar + "+N more"; links `/events/{slug}`.
- Props: `{ event: CatalogItem }`. `CatalogItem { type:"market"|"event"; id; slug; title; category; source; status; deadline:string|null; volume; created_at; outcomes: CatalogOutcome[] }`; `CatalogOutcome { label; yes_outcome_id:string|null; yes_price:string }`.
- Type: **Pure-presentational Server Component.** **Restyle-safe** — BUT preserve the per-outcome independent bars (NEVER a single 100% stacked bar). Sorts outcomes desc by `yes_price`, shows top 4.
- Current visual: same `Card` hover/ring idiom as MarketCard; outcome rows `text-sm`, `tabular-nums` percent, `bg-brand-primary` fills on `bg-zinc-200` tracks; secondary "Event · N outcomes" badge. **Visual backbone** — the multi-outcome counterpart to MarketCard; the two cards living side-by-side in one grid is the home page's signature.

### catalog/catalog-controls.tsx — `CatalogControls`
- Purpose: browse filter island (BRW-01..04) — debounced search, category chip row, status `Select`, sort `Select`. Drives URL searchParams (`router.replace`); SSR re-fetches.
- Props: `{ categories:string[]; q?; category?; status?; sort? }`.
- Type: **Logic-coupled Client Component** (router/searchParams, 300ms debounce, render-time state sync). **Restyle the markup/classes only**; the URL-param logic is load-bearing for shareable/SSR-fresh filters. The active category chip uses `bg-brand-primary text-brand-primary-foreground` (white-label-aware — keep).
- Current visual: search `Input` w/ lucide `Search` icon, two `w-44` Selects, horizontal-scroll chip row; inactive chips `bg-zinc-100`. Functional but generic — high-value premium target (this is the primary interaction surface above the grid).

---

## 4. Event subdirectory (`src/components/event/*`)

### event/event-detail-view.tsx — `EventDetailView`  🔒 framing LOCK
- Purpose: multi-outcome event detail island (EVT-02/03/05). LEFT = every outcome as an independent `OutcomeRow`; RIGHT (sticky) = selected child's `MarketDetailLiveOdds` + `OrderEntryForm` + `PriceHistorySection`. Selecting an outcome client-fetches that child market.
- Props: `{ event: EventDetail; defaultChild: MarketDetail; defaultHistory: PricePoint[]; isAuthenticated: boolean }`. `EventDetail { id, slug, title, category, source, status, deadline, created_at, outcomes: EventOutcomeRead[] }`; `EventOutcomeRead { label, yes_outcome_id, yes_price, market_id, child_slug, child_status }`.
- Type: **Heavily logic-coupled Client Component** — selection state, out-of-order-fetch guard, **single-websocket cap** (exactly ONE live socket via the `key={child.id}` panel remount — comment lines 134–139; critical, do not break). **Restyle markup/classes only; do not touch selection/socket logic.** Composes the reused right-rail pieces.
- Current visual: `lg:grid-cols-3`, LEFT col-span-2 list of `OutcomeRow`, RIGHT sticky `Card` with `opacity-60` while loading. **Visual backbone** of the event experience.

### event/outcome-row.tsx — `OutcomeRow`  🔒 framing LOCK
- Purpose: one INDEPENDENT outcome row of an event — own YES% + own bar, selectable button, status chip for non-OPEN children.
- Props: `{ label:string; yesPct:number; status:string; selected:boolean; onSelect:()=>void }`.
- Type: **Presentational Client Component** (button + selection styling; parent owns state). **Restyle-safe** — BUT the bar is the per-outcome independent bar (never a cross-outcome sum). Reuses `admin/market-status-badge` for non-OPEN status (cross-import to admin — note for any admin-vs-player divergence).
- Current visual: `rounded-lg border p-3`, selected = `border-brand-primary ring-2 ring-brand-primary`, own YES bar `bg-brand-primary` on `bg-zinc-200`. Worth elevating into a premium selectable "outcome pill/row."

### event/event-status-badge.tsx — `EventStatusBadge`
- Purpose: derived event-status chip (open / partially_resolved / resolved / void).
- Props: `{ status:string; className?:string }`.
- Type: **Pure-presentational Server Component** (config map lines 9–28). **Restyle-safe.** Follows the locked chip convention (`px-2.5 py-0.5 text-xs font-semibold`, `aria-label="Status: …"`).
- Current visual: emerald (open), amber (partially_resolved), near-black (resolved), zinc (void).

---

## 5. UI primitives (`src/components/ui/*`) — shadcn "new-york", the restyle root

These are copied shadcn primitives. Restyling THESE re-skins the entire app at once (highest leverage, but also highest blast radius — change carefully).

| File | Export(s) | Brand-aware? | Current treatment / notes |
|---|---|---|---|
| `ui/button.tsx` | `Button`, `buttonVariants` | **YES** | `cva` variants. `default` = `bg-brand-primary text-brand-primary-foreground`; focus ring = `ring-brand-primary`; `active:scale-[0.97]`. secondary/ghost/outline = neutral zinc; destructive = red-500. Sizes default/sm/lg/icon. The ONE brand-aware primitive. **Restyle-safe; the CTA backbone.** |
| `ui/card.tsx` | `Card`,`CardHeader`,`CardTitle`,`CardDescription`,`CardContent`,`CardFooter` | no | `bg-white text-zinc-950 dark:bg-zinc-950 dark:text-zinc-50`, `rounded-lg border-zinc-200 shadow-sm`. The surface everything sits on — **the single highest-leverage dark-first restyle target.** |
| `ui/badge.tsx` | `Badge`,`badgeVariants` | no | rounded-full chip; default near-black, secondary zinc, destructive red, outline. |
| `ui/dialog.tsx` | `Dialog…` (Radix) | no | white/zinc-950 panel, `bg-black/80` overlay, animate-in/out, close X. |
| `ui/input.tsx` | `Input` | no | `h-10 border-zinc-200 bg-white`, focus ring **`ring-zinc-950`** (NOT brand — inconsistency vs Button; candidate to unify on brand). |
| `ui/select.tsx` | `Select…` (Radix) | no | zinc trigger/content, focus `ring-zinc-950`. |
| `ui/skeleton.tsx` | `Skeleton` | no | `animate-pulse bg-zinc-100 dark:bg-zinc-800`. |
| `ui/tabs.tsx` | `Tabs…` (Radix) | no | zinc list, active `bg-white`. (Used mostly admin/user-detail.) |
| `ui/sonner.tsx` | `Toaster` | no | `theme="system"` (CSS-only dark, no next-themes); white/zinc toasts. Note: player BET flow deliberately uses inline alerts, NOT toasts. |
| `ui/tooltip.tsx` | `Tooltip…` (Radix) | no | zinc tooltip. |
| `ui/form.tsx` | `Form`,`FormField`,`FormItem`,`FormLabel`,`FormControl`,`FormMessage` (RHF wiring) | no | logic wiring for react-hook-form; restyle via Label/Input, not here. |
| `ui/label.tsx`, `ui/textarea.tsx`, `ui/dropdown-menu.tsx`, `ui/separator.tsx`, `ui/table.tsx` | primitives | no | neutral zinc; table/dropdown mostly admin. `separator`/`label`/`textarea` shared. |

---

## 6. Visual backbone ranking (most worth elevating first)

1. **`ui/card.tsx`** — every tile, panel, dialog sits on it. White surface → dark surface is the single biggest "premium dark-first" move. Restyle once, the whole app changes.
2. **`market-card.tsx` + `catalog/event-card.tsx`** — the home grid's two repeating units (side by side). The product's first impression; the angular-X/blue-silver identity should live here.
3. **`odds-display.tsx`** — the recurring odds bar; the core "feel" of a prediction market. Make YES feel energetic (gradient/glow on the brand fill) while keeping the binary 2-segment contract.
4. **`ui/button.tsx`** — the only brand-aware primitive; every CTA. Premium hover/press/glow here propagates everywhere.
5. **Header/nav (`layout.tsx` header + `player-nav.tsx` + `brand-logo.tsx`)** — first thing seen; where the logo lands. White `header bg-white` → dark glass/near-black.
6. **`event/event-detail-view.tsx` + `event/outcome-row.tsx`** — the multi-outcome experience and the selectable outcome rows (respect the framing LOCK).
7. **`order-entry-form.tsx` + `bet-confirm-dialog.tsx`** — the conversion ticket (style only; logic frozen).
8. **`price-history-chart.tsx`** — has hardcoded light-mode greys (`#e4e4e7`, `#71717a`) that are an outright dark-first bug; concrete fix point.
9. **`recent-activity-feed.tsx` + `live-indicator.tsx`** — low-effort, high-energy "this is live" moments currently very flat.

---

## 7. Constraints the redesign must NOT break (component-specific)

- **Per-outcome framing LOCK** (event-card, outcome-row, event-detail-view): independent YES bars, never sum-to-100.
- **White-label brand tokens**: accent must flow through `--brand-primary`/`--brand-secondary` (+ `--brand-primary-foreground`); never hardcode. Active states already use `bg-brand-primary` — keep that.
- **`BrandLogo`**: logo only via `<img src=/branding/logo>` (never inline SVG markup); wordmark keeps legible ink with brand-as-accent (A-PALETTE #4).
- **Semantic colors stay semantic**: success = emerald (`BetPlacedSuccess`, won chip), error = red/rose, live = emerald, stale/reconnecting = amber. **A-LOSS-NEUTRAL**: losses render neutral zinc, NEVER red (`MarketResolutionPanel`, portfolio).
- **Logic-coupled components — markup/classes only, do not touch behavior**: `OrderEntryForm` (RHF/zod/server-action), `EventDetailView` (single-socket cap via `key={child.id}`), `CatalogControls` (URL-param/debounce), `PriceHistorySection`/`PriceHistoryChart` (controlled window, `h-64`, `<2` empty state, react-is pin), `MarketDetailLiveOdds` (socket).
- **Motion guardrails**: `MarketGrid` entrance never animates opacity (SSR-visible) + respects `useReducedMotion`. Keep both for any new motion.
- **No layout shift**: skeletons (`market-list-skeleton`, `market-detail-skeleton`) must stay dimensionally in sync with their real counterparts.
- **Security**: `MarketResolutionPanel` justification stays ESCAPED text (no `dangerouslySetInnerHTML`); layout `<style>` only interpolates validated hexes.
- **Anonymity**: `RecentActivityFeed` never adds identity.

---

## 8. Limitations / gaps relevant to a dark-first premium redesign

- **No real dark theme system.** Dark mode is `@media (prefers-color-scheme: dark)` flipping only `--background`/`--foreground`. Component-level `dark:` variants exist but are tied to OS preference — there is **no app-controlled dark toggle / `.dark` class / next-themes**. A "dark-FIRST" redesign likely needs to invert the default (make near-black the base, not a media-query branch), or introduce a theme class. This is the largest structural decision.
- **White surfaces are the default, not dark.** Card/Input/Select/Dialog/header/footer all default to `bg-white`; dark is only the OS-pref branch. Premium dark-first means rebasing these defaults.
- **`--brand-secondary` is defined but essentially unused** in components — a free token for the royal-blue/silver duotone of the new identity.
- **Hardcoded greys break on dark**: `price-history-chart.tsx` (`#e4e4e7`, `#71717a`), and the default chart line fallback `#059669` (emerald, not the brand) — pre-token leftovers.
- **Focus-ring inconsistency**: `Button` rings `brand-primary`; `Input`/`Select`/`Dialog`/`Tabs` ring `zinc-950`/`zinc-300`. Unifying on the brand ring is a cheap consistency + premium win.
- **No elevation/glass/gradient/glow vocabulary** anywhere — only flat `shadow-sm`/`shadow-md`. The metallic-X / lens-flare identity has no existing surface treatment to build on; it's greenfield.
- **Cross-surface import**: `event/outcome-row.tsx` imports `admin/market-status-badge` — a player component depends on an admin one; watch if admin gets a separate visual language.
