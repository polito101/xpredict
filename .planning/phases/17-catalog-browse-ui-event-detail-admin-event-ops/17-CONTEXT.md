# Phase 17: Catalog Browse UI, Event Detail & Admin Event Ops - Context

**Gathered:** 2026-06-05
**Status:** Ready for planning
**Mode:** Smart Discuss (autonomous) — grey areas auto-resolved to the recommended answer and documented below (operator directive: no questions, decide reasonably, respect existing architecture). Identical structure to a `gsd-discuss-phase` CONTEXT.md.

<domain>
## Phase Boundary

Phase 17 delivers the **frontend** for the v1.2 catalog: the player-facing curated **browse** (search + category chips + status/sort, explicit empty states), a **multi-outcome event card** (distinct from the binary market card), an **event detail page** that renders each outcome as an **independent per-outcome row** (its own YES price/odds — never a single bar summing to 100%) with **bet-on-one-outcome** (reusing the binary `OrderEntryForm`) and **per-outcome price history** (reusing the existing chart per child), and the **admin house-event operations** UI (create / edit / resolve / void / reverse). Every new surface respects the operator's `--brand-*` white-label tokens.

It builds **entirely against the finished, merged Phase-16 HTTP contract** (`GET /api/v1/catalog`, `GET /api/v1/events/{slug}`, `GET /api/v1/categories`, `POST/PATCH /admin/events`, `POST /admin/events/{group_id}/resolve|void|reverse`) — **no backend code changes**. Covers **EVT-02, EVT-03, EVT-04, EVT-05, BRW-06** (the UI for browse BRW-01..05 whose API shipped in Phase 16). It does **NOT** add any backend endpoint, the seed/demo multi-outcome harness (Phase 18), or — beyond the storm-proof on-screen cap that criterion 3 mandates — the P2 stretch (P2-01 combined chart, P2-02 live odds on all rows, P2-03 featured shelf + count chips), which land only after the P1 core is stable.

It **reuses UNCHANGED**: `OrderEntryForm` + `BetConfirmDialog` + `placeBetAction` (bet on a child binary market), `PriceHistorySection` + `PriceHistoryChart` (per-child history by `child_slug`), `useMarketSocket` + `MarketDetailLiveOdds` (live odds, one socket per market), `OddsDisplay` / `SourceBadge` / `LiveIndicator`, the `--brand-*` CSS-variable cascade (`globals.css` `@theme inline` → `bg-brand-primary` utilities, no provider), the admin Server-Action Bearer-forward pattern (`admin_jwt` cookie → `Authorization: Bearer`), and the shadcn primitives + RHF/zod + sonner + `Loader2` form/dialog conventions. **Zero new dependencies.**

</domain>

<decisions>
## Implementation Decisions

### Catalog browse — IA, routing, filter UX (BRW-01..06 UI, EVT-04)
- **Mount the catalog browse at the homepage `/`** (upgrade `app/page.tsx`). The homepage is already "the market catalog" (`<h1>Markets</h1>` + `MarketList` → `GET /markets`); Phase 17 swaps its data source to the curated `GET /catalog` (a strict superset returning both standalone markets and events) and adds the browse controls. The legacy `GET /markets` API stays for back-compat; binary detail stays at `/markets/[slug]`; events get the new `/events/[slug]`. (No separate marketing landing exists on `origin/main`.)
- **Filter state lives in the URL `searchParams`** (`?q=&category=&status=&sort=`). `app/page.tsx` stays a Server Component that reads `searchParams`, server-fetches `fetchCatalog(params)` + `fetchCategories()` (both `cache:"no-store"`, SSR-fresh), and renders a `"use client"` controls island that updates the URL via `router.replace` (debounced search ~300ms). Shareable, SSR-first, matches the app's existing server-fetch pattern. No client-only filter state, no infinite scroll, no pagination (BRW-05 — bounded `LIMIT 100`).
- **Category control = a horizontal scrollable chip row**: "All" + one chip per category from `GET /categories` (which returns only non-empty categories — CAT-06 — so empty categories simply never render). Active chip uses the brand token.
- **Status + sort = two shadcn `Select`s** in a filter bar (`flex flex-wrap items-end gap-4`, mirroring the admin markets filter bar): Status = All / Open / Closing soon / Resolved → `?status=open|closing_soon|resolved`; Sort = Volume / Closing soonest / Newest → `?sort=volume|closing_soonest|newest` (default volume). Search = a debounced `Input`.
- **Every zero-result combination shows an explicit empty state** (BRW-05) — a centered "No markets found / No markets match your current filters…" block (reuse the shipped table-empty copy), never an error.

### Event card & per-outcome framing — THE DESIGN LOCK (EVT-04, EVT-02)
- **`EventCard` is visually distinct from the binary `MarketCard`** (EVT-04): event title + an **"Event · {N} outcomes"** badge + the **top 2–4 outcomes** as labeled rows (`label` + its YES %), with **"+{N} more"** when there are more than 4; a multi-row "stacked" silhouette versus the binary card's single YES/NO bar. Links to `/events/{slug}`. The catalog renders the binary `MarketCard` for `type:"market"` items (via a tiny pure adapter) and `EventCard` for `type:"event"` items.
- **Per-outcome price framing (NON-NEGOTIABLE):** on the event detail, **each outcome is an independent row showing its OWN YES probability** (0–100%, on its own bar) — **NEVER a single distribution summing to 100%**, never a stacked/normalized bar across outcomes. This is the "never lie about probability" rule (live Polymarket data sums to ~0.45 across 60 outcomes — a stacked bar would visibly lie). Display-only; **no cross-outcome normalization**. Each row reuses the `OddsDisplay` single-bar primitive (YES vs its own complement), not a shared 100% bar.
- **Outcome ordering** = YES price descending (most-likely first); resolved/closed children are de-emphasized with a status chip but still rendered (the event status is derived). Ties broken by label.

### Bet-on-one-outcome & per-outcome history (EVT-03, EVT-05)
- **Selecting an outcome row mounts the bet + chart for that child.** Clicking a row selects it; the right rail (sticky `lg:col-span-1`, mirroring the market detail layout) mounts the **reused `OrderEntryForm`** targeting that child's `{marketId: market_id, outcomes:[YES,NO], marketStatus, minStake, maxStake}` and the **reused `PriceHistorySection`** keyed by the child's `child_slug` (the price-history endpoint is `/markets/{slug}/price-history`; each child is a real market with its own slug). Betting on an event outcome === betting on its constituent binary market (EVT-03 — zero new bet path).
- **Default selection** = the first (highest-YES, OPEN) outcome, so the page is immediately actionable; the player switches outcomes by clicking another row.

### Live-odds subscription cap (success criterion 3 — storm-proof)
- **Subscribe live odds ONLY for the currently-selected outcome** — one `useMarketSocket(selected child market_id)` mounted in the selected panel (reusing `MarketDetailLiveOdds`). Non-selected rows show the SSR `yes_price` (refreshed on navigation). This caps WebSocket subscriptions to **exactly one** on-screen child regardless of event size (no connection storm on a 60-outcome event). P2-02 (live odds on *all* visible rows behind a max-K cap) is the documented stretch beyond this P1 cap.
- **The catalog grid has no live sockets** (SSR prices only) — avoids a socket-per-card storm on the browse; live odds are a detail-page concern (P2-03 stretch otherwise).

### Admin event ops — IA & data flow (EVA-01..05 UI)
- **Admin events list = the PUBLIC catalog filtered.** No admin list/get-event endpoint exists in the Phase-16 contract; house events appear in `GET /api/v1/catalog`. The `/admin/events` list page server-fetches `fetchCatalog()` and filters to `type==="event" && source==="HOUSE"`, rendering rows that link to a manage page by slug. (No backend change.)
- **Admin event manage page loads via the PUBLIC `GET /api/v1/events/{slug}`** → `EventDetail`, whose `id` **is** the `group_id` and whose `outcomes[].yes_outcome_id` feeds the resolve `Select`. Mutations target `/admin/events/{group_id}` (bare prefix, Bearer).
- **Server-driven two-step confirm.** The event resolve/void/reverse dialogs use the backend's stateless two-step: open → call with `confirm:false` → render the non-mutating **preview** (`winners`/`losers` for resolve/void, `settled_children_to_reverse` for reverse, `projected_status`); operator confirms → call again with `confirm:true` → execute. Mandatory non-empty `justification` on all three. This is richer than the binary market dialogs (which are client-only two-step) — design the dialog to show projected impact before the destructive confirm.
- **Edit-lock (HTTP 423) handled reactively.** Events expose no `bet_count`; the event edit form attempts the `PATCH` and, on `423 {code:"EVENT_LOCKED"}`, disables the outcomes editor + shows the locked helper. The backend is authoritative for the lock.
- **Event create form** mirrors `market-form.tsx` (RHF + zod + shadcn `Form` + `Loader2` + sonner + 422→inline) but with a **dynamic outcomes array** (`useFieldArray`, **min 2** `{label, initial_odds∈(0,1)}`) instead of a single YES/NO odds field; `outcomes` is a whole-list replace on edit. Title/category/deadline/resolution_criteria match the create contract. **Add an `/admin/events` link to `admin-nav.tsx`.**

### Brand / white-label (BRW-06)
- **Every new surface is brand-compliant by construction**: brand accents use `bg-brand-primary` / `text-brand-primary` / `border-brand-primary` / `ring-brand-primary` (or `var(--brand-primary,…)` for SVG strokes / inline bars) — never a hardcoded indigo/emerald hex. Surfaces inherit theming automatically via the root-layout CSS-variable cascade (no per-page provider). The active category chip, focus rings, and any selected-outcome accent route through the brand token.

### Claude's Discretion
- Exact new component/file names, the debounce interval (~300ms), the "+N more" threshold (4), and chip/badge colors for event-derived status (follow the shipped chip convention from the Phase-12 status palette).
- Whether the selected-outcome bet+chart renders in a sticky right rail vs an inline expansion under the selected row — pick the most "looks-real", least-layout-churn option (default: right rail, mirroring `markets/[slug]`).
- Whether to retire the now-orphaned `MarketList` component (only used by `/`) or keep it for a future `/markets` index — default: retire it + its test, replace with the catalog browse, to avoid dead code (reusing `MarketCard` for the catalog's `type:"market"` items).
- Copy strings — reuse the Phase-12 copywriting conventions verbatim where an analog exists (empty/error/toast/justification copy).
- Test layout: co-located `*.test.tsx`/`*.test.ts` + URL-contract tests for the new `lib/catalog.ts` and `lib/admin-events-api.ts` (clone the `admin-markets-api.test.ts` prefix-lock test).

</decisions>

<code_context>
## Existing Code Insights
*(from two read-only frontend + backend scouts on the phase branch)*

### Reusable Assets
- **Catalog/event frontend is pure greenfield** — grep for `catalog|MarketGroup|group_item_title|outcome|EventDetail` across `frontend/src` found nothing (only an unrelated admin bet `outcome_label`). No `lib/catalog*`, no `Event`/`CatalogItem` TS types, no `/events` route, no `EventCard`, no admin events page/nav. The binary-market frontend is the reuse donor.
- **Browse analog**: `app/page.tsx` (Server Component + `<Suspense>` → `components/market-list.tsx` async SC → `lib/api.ts fetchMarkets()` → `MarketGrid` of `MarketCard`). The new browse is a strict superset (adds q/category/status/sort + event cards) reading `/catalog`.
- **Event-detail analog**: `app/markets/[slug]/page.tsx` — SSR `Promise.allSettled([fetchMarket, fetchPriceHistory, fetchActivity])`, `cookies()→xpredict_session` for `isAuthenticated`, `grid grid-cols-1 lg:grid-cols-3 gap-8`, LEFT `lg:col-span-2` (live odds + criteria + chart + activity), RIGHT `lg:col-span-1 lg:sticky lg:top-8` (`OrderEntryForm` Card, or resolution panel when RESOLVED). Header H1 `text-3xl font-semibold tracking-tight` + `SourceBadge` + status badge.
- **`OrderEntryForm`** (`components/order-entry-form.tsx`, `"use client"`): props `{marketId, outcomes: {id,label,current_odds}[], marketStatus, isAuthenticated, minStake?, maxStake?}`; submits `placeBetAction` (server action, `lib/bet-actions.ts`) via `useActionState`; client zod (`makeBetSchema`) → `BetConfirmDialog` → POST. Already binary-leg-scoped — works verbatim on a child market.
- **`PriceHistorySection`** (`components/price-history-section.tsx`, `"use client"`) owns `window`+`points` state, re-fetches `fetchPriceHistory(slug, window)`; wraps `PriceHistoryChart` (Recharts, `react-is` pinned for React 19). Per-child by passing `child_slug`.
- **`useMarketSocket(marketId, initialOdds)`** (`hooks/use-market-socket.ts`) → `{odds, state}`; one socket per `marketId`, re-subscribes only on `marketId` change, full teardown on unmount. `MarketDetailLiveOdds` (`components/market-detail-live-odds.tsx`) composes it with `OddsDisplay` + `LiveIndicator` (`{marketId, yesOutcomeId, noOutcomeId, initialOdds}`).
- **`OddsDisplay`** (`{yes,no}` whole percents, single 2-segment bar, `bg-brand-primary` YES), **`SourceBadge`** (`{source, sourceUrl?}`), **`LiveIndicator`**, **`MarketCard`** (`{market: MarketItem}`, stretched-link to `/markets/{slug}`, `OddsDisplay` + footer Vol/deadline + `SourceBadge`), **`MarketGrid`** (`"use client"`, framer-motion stagger, `grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4`).
- **Admin form analog**: `components/admin/market-form.tsx` (RHF + `zodResolver` + shadcn `Form/FormField/FormItem/FormControl/FormMessage/FormDescription` + `Loader2` + sonner + `422→form.setError`); `{mode, marketId?, initialValues?, betCount?}`. The event form adds `useFieldArray` outcomes (min 2).
- **Admin dialog analogs**: `components/admin/resolve-market-dialog.tsx` (outcome `Select` + mandatory justification `Textarea` + destructive confirm, stays-open-during-submit, `role="alert"`), `reverse-settlement-dialog.tsx` (justification only). Shared `components/admin/settlement-dialog-utils.ts isSessionExpiredError`. Action host island `components/admin/market-detail-actions.tsx` (status-gates buttons, `router.refresh()` after mutation).
- **Admin data layer**: `lib/admin-markets-api.ts` (`"use server"`, `bearerHeader()` reads `admin_jwt` cookie → `Authorization: Bearer`, `adminApiFetch<T>` throws `"API error: <status>"`). Two-prefix landmine documented + URL-tested. `lib/admin-markets-types.ts` holds shared types.
- **Public data layer**: `lib/api.ts` (`apiBase()` server→`BACKEND_URL||NEXT_PUBLIC_API_URL`, browser→`NEXT_PUBLIC_API_URL`; all reads `cache:"no-store"`; typed throws like `MarketNotFound`). Mirror as `lib/catalog.ts` (`fetchCatalog`/`fetchEvent`/`fetchCategories` + `EventNotFound`).

### Established Patterns
- **Brand white-label = CSS-variable cascade only.** `globals.css` `:root` defines `--brand-primary/-foreground/-secondary`; `@theme inline` maps them to `bg-/text-/border-/ring-brand-primary` utilities; `app/layout.tsx` injects a server-validated `<style>:root{…}</style>` per navigation from `GET /branding/current`. NO React provider — new surfaces are themed automatically; just use the brand utilities/`var()`.
- **SSR-first reads, `cache:"no-store"`**, Docker-hostname-vs-localhost split in `apiBase()`. Server Components read `searchParams`/`params` (Next 16 async: `await params`). Client islands own interactivity.
- **Admin auth**: `proxy.ts` (renamed from `middleware.ts`) optimistic Edge gate on `/admin/:path*` (cookie presence → `/admin/login`); authoritative gate is the backend `current_active_admin` (Bearer JWT). New `/admin/events/*` pages auto-gated by the existing matcher.
- **Tests**: Vitest (`*.test.tsx`→jsdom, `*.test.ts`→node), `@→./src` alias; mock `next/link` to a plain `<a>`, mock server actions via `vi.mock`, mock `globalThis.fetch`/`next/headers` for API tests; assert on roles/text/`data-testid`. Co-located + `__tests__/` both used.
- **Money/odds are JSON strings on the wire** — parse client-side, never assume numbers.

### Integration Points
- `app/page.tsx` (homepage → catalog browse), new `app/events/[slug]/page.tsx` (+`error.tsx`), new `app/admin/events/{page,new,[slug]}.tsx`.
- `components/player-nav.tsx` (verify the "Markets" link still points to `/`), `components/admin/admin-nav.tsx` (add `/admin/events`).
- New `lib/catalog.ts` (public reads), `lib/admin-events-api.ts` + `lib/admin-events-types.ts` (admin writes; bare `/admin/events` prefix).
- Reused: `OrderEntryForm`, `PriceHistorySection`, `useMarketSocket`/`MarketDetailLiveOdds`, `OddsDisplay`, `SourceBadge`, shadcn `Select`/`Input`/`Card`/`Dialog`/`Form`/`Tabs`/`Badge`.

</code_context>

<specifics>
## Specific Ideas

- **Never sum-to-100.** The single most important rule of the phase: per-outcome independent YES bars, display-only, no normalization. A stacked/100%-distribution bar is an explicit anti-feature (live data sums to <1 across many outcomes — it would visibly lie).
- **Never proxy search to Gamma.** The browse search hits only the local `/catalog` (`pg_trgm` over local rows) — never a third-party search.
- **No heavy pagination / infinite scroll.** Catalog is curated/bounded (`LIMIT 100`).
- **Money/odds on the wire = strings.** Reuse the existing `formatVolume`/`formatDeadline`/`formatMoney` string helpers; never `parseFloat` for storage/display math beyond rendering a percent.
- **Prefix split for URLs**: public reads `/api/v1/catalog|events|categories|markets`; admin events bare `/admin/events`; admin markets `/api/v1/admin/markets`. Encode per-call (URL-contract test).
- **Admin auth = Bearer (via `admin_jwt` cookie forwarded server-side)** — not the player `xpredict_session` cookie.
- **Windows worktree caveat**: default Turbopack `next build` flakes on the worktree (pnpm symlink + Sentry); validate locally with `pnpm typecheck`/`lint`/`vitest` + `next build --webpack`, and trust Linux CI for the authoritative `frontend` job. See [[xprediction-frontend-local-validation]]. Use the standalone/pinned **pnpm 9.15.0**, never `corepack pnpm` unpinned (resolves to destructive 11.x).
- **Executors stream-idle-timeout on this Windows worktree** → the orchestrator writes the implementation **inline**; spawned agents only for read-only analysis. See [[gsd-execute-phase-sequential-in-worktree]].

</specifics>

<deferred>
## Deferred Ideas

- **P2-01** combined event chart (overlaid top-outcome histories), **P2-02** live odds on *all* on-screen event rows behind a max-K cap, **P2-03** featured "Top events" home shelf + per-category count chips — Phase 17 **stretch**, only after the P1 core is stable; non-blocking. (The P1 cap subscribes only the selected outcome.)
- **Seed/demo multi-outcome harness** across event states (DEMO-01..04) — **Phase 18**.
- **True refund-on-cancel** — out of scope (void = all-children-NO, per Phase 15).
- **Admin list/get-event backend endpoints** — not needed; the public catalog + `/events/{slug}` cover the admin read path. A dedicated admin event-list endpoint (with bet counts / drafts) would be a future backend addition.
- **Per-child deadlines on the event detail** — `EventOutcomeRead` exposes only the event-level `deadline`; per-row deadlines would need a backend field (deferred).

</deferred>
</content>
</invoke>
