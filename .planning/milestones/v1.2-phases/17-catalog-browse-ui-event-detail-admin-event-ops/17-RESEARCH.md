# Phase 17 — Implementation Research

**Researched:** 2026-06-06
**Confidence:** HIGH — the backend contract is merged + fully mapped; the frontend reuse donors are read and quoted.

## Don't Hand-Roll — reuse map

| Need | Reuse (verbatim) | Note |
|------|------------------|------|
| Bet on one outcome (EVT-03) | `OrderEntryForm` (`components/order-entry-form.tsx`) | already binary-leg-scoped: props `{marketId, outcomes:[{id,label,current_odds}], marketStatus, isAuthenticated, minStake?, maxStake?}`. A child IS a real binary market — pass the child's full YES+NO outcomes. |
| Get the child's full YES+NO outcomes + bounds + status | `fetchMarket(child_slug)` (`lib/api.ts`) → `MarketDetail` | `EventOutcomeRead` only carries the YES leg; the order form needs the real NO outcome id too. Each child is fetchable at `/api/v1/markets/{child_slug}`. |
| Per-outcome price history (EVT-05) | `PriceHistorySection` (`{slug, initialPoints, initialWindow?}`) → `PriceHistoryChart` | key by `child_slug`; endpoint `/markets/{child_slug}/price-history`. |
| Live odds (criterion 3 cap) | `MarketDetailLiveOdds` (`{marketId, yesOutcomeId, noOutcomeId, initialOdds}`) → `useMarketSocket` | ONE socket per `marketId`; mount only for the selected child → caps to 1. |
| Probability bar | `OddsDisplay` (`{yes,no}`) | each outcome's own YES vs its own NO — truthful per-binary, never a cross-outcome sum. |
| Binary card (catalog `type:"market"`) | `MarketCard` (`{market: MarketItem}`) via `catalogMarketToMarketItem(item)` adapter | the adapter maps `title→question`, `outcomes[].yes_price→YES current_odds`, `deadline ?? ""` (formatDeadline → "No deadline" on ""), `source_url:null`. MarketCard renders title/OddsDisplay/Vol/deadline/source — no status badge, so the public-status vocab mismatch is harmless. |
| Grid + entrance | `MarketGrid` (`"use client"`, framer stagger) | server-rendered card children inside the client grid is fine. |
| Admin Server Actions | clone `lib/admin-markets-api.ts` (`bearerHeader()` reads `admin_jwt` cookie → `Authorization: Bearer`; `adminApiFetch<T>` throws `"API error: <status>"`) | bare `/admin/events` prefix (NOT `/api/v1`). |
| Admin form | clone `market-form.tsx` (RHF+zodResolver+`Form*`+`Loader2`+sonner+422→`form.setError`) | add `useFieldArray` outcomes (min 2). |
| Two-step dialog | clone `resolve-market-dialog.tsx` (stays-open-during-submit, `role="alert"`, `isSessionExpiredError`) | adapt to the SERVER two-step (`confirm:false` preview → `confirm:true` execute). |
| Action host island | clone `market-detail-actions.tsx` (status-gated buttons + form + dialogs + `router.refresh()`) | gate off the derived event status. |

## Key technical findings

1. **URL-driven filters (Next App Router idiom).** Keep `app/page.tsx` a Server Component reading `searchParams`; the client `CatalogControls` island mutates the URL via `useRouter().replace(\`${pathname}?${params}\`)` (debounce the search ~300ms with a `setTimeout`/`useRef`, cleared on unmount). The Server Component re-fetches on every URL change (`cache:"no-store"`). Shareable, SSR-fresh, no client data store. Status/sort selects fire immediately; search is debounced.
2. **Child-detail-on-select keeps large events cheap.** SSR fetches ONLY the default child's detail; selecting another outcome client-fetches that child. Rows render from `EventDetail.outcomes` (one event fetch). A 60-outcome event = 1 event fetch + 1 child fetch (selected) + 1 socket. Never N child fetches or N sockets.
3. **The WS cap is structural, not a counter.** Mount `MarketDetailLiveOdds` only inside the selected panel → exactly one `useMarketSocket(selectedChildMarketId)`; switching selection unmounts the old socket (the hook's cleanup closes it) and opens one for the new child. No connection storm by construction.
4. **Server two-step confirm.** The event settle endpoints are stateless: body `{justification, confirm}`. `confirm:false` (or omit) → non-mutating preview (`EventActionResponse{preview:true, winners?, losers?, settled_children_to_reverse?, projected_status}`); `confirm:true` → execute (`{children_settled, children_failed, projected_status}`). The dialog fetches the preview on open and shows projected impact before the destructive confirm. Resolve also validates `winning_outcome_id` is a child YES leg (422 in preview too).
5. **Edit-lock is reactive (no bet_count for events).** Attempt `PATCH /admin/events/{group_id}`; a `423 {code:"EVENT_LOCKED", reason}` → disable the outcomes editor + locked helper. The `adminApiFetch` throw message carries the status (`API error: 423`); surface it as a typed `EventLockedError` (or branch on `423`) so the form can render the lock instead of a generic toast.
6. **Money/odds are JSON strings.** Parse only to render a percent; never store as float. Reuse `formatVolume`/`formatDeadline`/`formatMoney`.
7. **Prefix split (encode per call):** `/api/v1/catalog|events|categories|markets`; bare `/admin/events…`; `/api/v1/admin/markets`. URL-contract test locks the bare event prefix.
8. **Admin auth = Bearer via `admin_jwt` cookie** (forwarded server-side), distinct from the player `xpredict_session` cookie. New `/admin/events/*` pages are auto-gated by the existing `proxy.ts` `/admin/:path*` matcher.

## Package legitimacy

Zero new dependencies. `react-hook-form` `useFieldArray` and the `lucide-react` icons (`Plus`/`X`/`Trash2`/`Search`) ship with already-installed packages. No `npx shadcn add`, no third-party registry.

## Validation recipe (Windows worktree caveat)

- Use the standalone/pinned **pnpm 9.15.0** (never unpinned `corepack pnpm` → destructive 11.x).
- Local: `pnpm typecheck` (`tsc --noEmit`) + `pnpm lint` (`eslint src`) + `pnpm test` (`vitest run`) all work on the worktree. Default Turbopack `next build` flakes (pnpm symlink + Sentry) → `pnpm exec next build --webpack` locally; trust the **Linux CI `frontend` job** as authoritative. See [[xprediction-frontend-local-validation]].
- Executors stream-idle-timeout on this worktree → the orchestrator writes code inline. See [[gsd-execute-phase-sequential-in-worktree]].

## Pitfalls

- **P1 — sum-to-100.** Never stack/normalize outcome bars (the framing LOCK). Each row = its own YES vs own NO.
- **P2 — order form needs the real NO id.** Don't synthesize NO from `1 - yes_price`; fetch the child detail to get the real NO outcome id (else NO bets break).
- **P3 — socket storm.** Don't mount a socket per row; only the selected child.
- **P4 — wrong prefix.** `/admin/events` is bare; `/catalog` is `/api/v1`. URL-test it.
- **P5 — `MarketList` orphan.** After upgrading `/`, remove `market-list.tsx` + its test (only consumer) to avoid dead code; verify no other import.
- **P6 — `formatDeadline(null)`.** Pass `deadline ?? ""` to the adapter (`new Date("")` → "No deadline"; `new Date(null)` → 1970 → "Ended" — wrong).
- **P7 — `"use server"` files export only async fns.** Event types live in `admin-events-types.ts`, not in `admin-events-api.ts`.
</content>
