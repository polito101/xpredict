# Phase 17 — Validation Plan (what proves each criterion)

Goal-backward: each success criterion + requirement maps to a concrete, observable proof (automated test where possible; documented manual/UI-review where the runtime is needed). "Verified by" is the artifact that makes the claim true.

## Success criteria → proof

### SC1 — Browse: search (debounced) + category tabs/chips (empty never render) + status/sort + visible empty state
| Proof | Verified by |
|-------|-------------|
| `fetchCatalog({q,category,status,sort})` builds the exact `/api/v1/catalog?…` query | `lib/__tests__/catalog.test.ts` |
| `CatalogControls` debounces search → URL, sets `?category/status/sort` via router | `components/catalog/catalog-controls.test.tsx` |
| Empty categories never render (API returns only non-empty; "All" + returned chips only) | `catalog-controls.test.tsx` (renders only provided categories) |
| Zero-result combo shows the explicit empty block (not an error) | page conditional + UI-review (runtime) |

### SC2 — Multi-outcome event card (top 2–4 + %, "+N more"), distinct; event detail = independent per-outcome rows, own YES, never sum-to-100
| Proof | Verified by |
|-------|-------------|
| `EventCard` shows top 2–4 outcomes each with own YES%, "+N more" when >4, "Event · N outcomes" badge, links `/events/{slug}` | `components/catalog/event-card.test.tsx` |
| Event detail renders one independent `OutcomeRow` per outcome, each its own YES% — **no single bar summing to 100%** | `components/event/event-detail-view.test.tsx` (asserts N rows + N independent percents; asserts NO stacked/normalized bar) |
| Card is visually distinct from the binary `MarketCard` | UI-review (Dim 2 framing LOCK) |

### SC3 — Bet on a single outcome (reuse OrderEntryForm) + per-outcome history + WS cap to on-screen
| Proof | Verified by |
|-------|-------------|
| Selecting an outcome mounts `OrderEntryForm` targeting that child (`market_id`, real YES+NO via `fetchMarket(child_slug)`) | `event-detail-view.test.tsx` (select → order form present with child id) |
| Per-outcome history via `PriceHistorySection` keyed `child_slug` | `event-detail-view.test.tsx` / code (keyed remount) |
| Exactly one live socket (selected child only) — no storm | code (single `MarketDetailLiveOdds` mount) + RESEARCH P3 + UI-review |

### SC4 — Admin create/edit/resolve forms (per-outcome labels + two-step + justification) + brand white-label on every new surface
| Proof | Verified by |
|-------|-------------|
| `EventForm` create: dynamic outcomes (min 2), submit body matches `CreateEventRequest`; edit: whole-list replace; 423 locks outcomes | `components/admin/event-form.test.tsx` |
| Resolve/Void/Reverse dialogs: server two-step (`confirm:false` preview → `confirm:true` execute) + mandatory justification | `components/admin/resolve-event-dialog.test.tsx` |
| `admin-events-api` hits bare `/admin/events…` with Bearer + `confirm` | `lib/__tests__/admin-events-api.test.ts` |
| Every new surface uses `--brand-*` (no hardcoded hue) | grep audit (no stray indigo/emerald hex in new files) + UI-review (palette swap re-skins) |

## Requirements → proof

| Req | Proof |
|-----|-------|
| EVT-02 (independent rows, never 100%) | `event-detail-view.test.tsx` + framing LOCK (UI-SPEC §) |
| EVT-03 (bet on one outcome, reuse path) | `event-detail-view.test.tsx` (OrderEntryForm wired to child) |
| EVT-04 (distinct event card, top 2–4, +N more) | `event-card.test.tsx` |
| EVT-05 (per-outcome history, reuse chart) | `event-detail-view.test.tsx` / code (PriceHistorySection per child_slug) |
| BRW-06 (white-label all new surfaces) | grep (no hardcoded brand hue) + UI-review |
| (BRW-01..05 UI) | `catalog.test.ts` + `catalog-controls.test.tsx` + empty-state |
| EVA-01/02 UI | `event-form.test.tsx` |
| EVA-03/04/05 UI | `resolve-event-dialog.test.tsx` + `admin-events-api.test.ts` |

## Gate commands (local; CI authoritative)
```
cd frontend
pnpm typecheck      # tsc --noEmit
pnpm lint           # eslint src
pnpm test           # vitest run
pnpm exec next build --webpack   # local build (Turbopack flakes on the worktree)
```
GREEN on the Linux CI `frontend` job is the authoritative gate (see [[xprediction-frontend-local-validation]]).

## Manual / UI-review (runtime — non-blocking advisory)
- The per-outcome framing LOCK renders truthfully on a real multi-outcome event (no stacked bar).
- A `/admin/branding` palette change re-skins the catalog/event/admin surfaces on next navigation (BRW-06).
- A large (many-outcome) event opens exactly one socket as the player switches outcomes (no storm).
</content>
