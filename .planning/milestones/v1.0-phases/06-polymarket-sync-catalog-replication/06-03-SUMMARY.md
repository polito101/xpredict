---
phase: 06-polymarket-sync-catalog-replication
plan: 03
subsystem: frontend-market-list
tags: [market-card, odds-display, source-badge, server-component, suspense, responsive-grid]
dependency_graph:
  requires: [phase-04-markets, 06-01]
  provides: [market-list-ui, market-card-component, source-badge-component, odds-display-component, api-fetch-helper]
  affects: [home-page, frontend-components]
tech_stack:
  added: [shadcn-badge, shadcn-skeleton]
  patterns: [stretched-link-card, async-server-component, suspense-skeleton-fallback, intl-date-format]
key_files:
  created:
    - frontend/src/components/ui/badge.tsx
    - frontend/src/components/ui/skeleton.tsx
    - frontend/src/components/source-badge.tsx
    - frontend/src/components/odds-display.tsx
    - frontend/src/lib/api.ts
    - frontend/src/components/market-list-skeleton.tsx
    - frontend/src/components/market-card.tsx
    - frontend/src/components/market-list.tsx
    - frontend/src/__tests__/market-card.test.tsx
  modified:
    - frontend/src/app/page.tsx
decisions:
  - "Used stretched-link pattern (Link inside h3 with after:absolute) instead of wrapping entire Card in Link -- avoids invalid nested <a> tags when SourceBadge renders a Polymarket external link"
  - "Made SourceBadge a client component ('use client') -- onClick stopPropagation requires client-side JS; plan said Server Component but onClick handler is incompatible"
  - "Installed Badge and Skeleton shadcn primitives manually (matching project convention) rather than via shadcn CLI -- project has no components.json (manual install pattern from Phase 1)"
metrics:
  duration: ~10m
  completed: 2026-05-28T09:46:00Z
---

# Phase 06 Plan 03: Market List UI Summary

Home page market catalog with responsive grid of MarketCard components -- stretched-link pattern, OddsDisplay with emerald/rose bar, SourceBadge with Polymarket external link, Suspense skeleton loading, empty/error states, 6 component tests green.

## Task Completion

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Install shadcn components, create MarketCard subcomponents, and API helper | 42b9762 | 6 files: badge.tsx, skeleton.tsx, source-badge.tsx, odds-display.tsx, api.ts, market-list-skeleton.tsx |
| 2 | MarketCard, MarketList, home page replacement, and component tests | 99c9223 | 4 files: market-card.tsx, market-list.tsx, page.tsx, market-card.test.tsx |

## What Was Built

### shadcn Primitives (manual install)
- `Badge` component with default/secondary/destructive/outline variants (CVA-based)
- `Skeleton` component with animate-pulse for loading states

### SourceBadge (source-badge.tsx)
- Client component (onClick stopPropagation for Polymarket external link)
- POLYMARKET: secondary badge wrapped in anchor, target="_blank", rel="noopener noreferrer", aria-label
- HOUSE: default badge (dark chip), no link
- Fallback for unknown sources: outline badge

### OddsDisplay (odds-display.tsx)
- Server Component showing YES/NO percentages with labels
- Proportional odds bar (emerald-500 / rose-500), h-1.5, rounded-full
- role="img" with aria-label="YES {X}%, NO {Y}%" for accessibility
- Semantic colors: emerald-700/400 for YES, rose-700/400 for NO (light/dark)

### API Helper (api.ts)
- TypeScript types: MarketOutcome, MarketItem (matches backend /api/v1/markets response)
- fetchMarkets(): Server Component fetch with cache: "no-store"
- formatVolume(): "$2.1M" / "$450K" / "$89" formatting
- formatDeadline(): Intl.DateTimeFormat with "Ended" for past dates

### MarketListSkeleton (market-list-skeleton.tsx)
- 6 skeleton cards in responsive grid (1/2/3 columns)
- Card with Skeleton placeholders matching MarketCard dimensions
- aria-busy="true" on container, aria-hidden="true" on skeleton elements

### MarketCard (market-card.tsx)
- Server Component with stretched-link pattern (Link inside h3, after:absolute)
- SourceBadge in relative z-10 div (sits above stretched link for independent click)
- OddsDisplay with YES/NO percentages computed from outcomes
- Volume and deadline formatting in footer
- hover:shadow-md transition, focus-within:ring-2 for keyboard accessibility
- line-clamp-3 on question text

### MarketList (market-list.tsx)
- Async Server Component fetching from /api/v1/markets
- Empty state: "No markets yet" with descriptive body, role="status"
- Error state: "Unable to load markets" in text-rose-700, role="status"
- Populated: responsive grid of MarketCard components

### Home Page (page.tsx)
- Replaced Phase 1 scaffold placeholder
- "Markets" heading (text-xl font-semibold)
- Suspense boundary with MarketListSkeleton fallback
- max-w-6xl centered, responsive padding (px-4 mobile, sm:px-6 tablet+)

## Test Results

6 new component tests (all pass):
- renders the market question text
- renders YES and NO odds percentages (63%, 37%)
- renders formatted volume ($2.1M)
- renders Polymarket source badge
- renders House badge without link for HOUSE source
- has an accessible odds bar with role=img and aria-label

Total frontend tests: 33 pass, 1 pre-existing failure (middleware.test.ts -- unrelated broken import)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Refactored Card from Link-wrapper to stretched-link pattern**
- Found during: Task 2
- Issue: Wrapping entire Card in `<Link>` (renders `<a>`) and having SourceBadge's `<a>` inside creates invalid nested `<a>` HTML, producing hydration errors
- Fix: Used stretched-link pattern -- Link inside h3 with `after:absolute after:inset-0`, SourceBadge in `relative z-10` div
- Files modified: frontend/src/components/market-card.tsx
- Commit: 99c9223

**2. [Rule 1 - Bug] Made SourceBadge a client component**
- Found during: Task 1
- Issue: Plan specified Server Component (no "use client") but SourceBadge needs onClick={stopPropagation} on the Polymarket anchor to prevent parent card navigation
- Fix: Added "use client" directive
- Files modified: frontend/src/components/source-badge.tsx
- Commit: 42b9762

**3. [Rule 3 - Blocking] Installed shadcn Badge and Skeleton manually**
- Found during: Task 1
- Issue: `pnpm dlx shadcn@latest add badge` fails because project has no components.json (manual install pattern from Phase 1)
- Fix: Created badge.tsx and skeleton.tsx manually matching official shadcn source code
- Files modified: frontend/src/components/ui/badge.tsx, frontend/src/components/ui/skeleton.tsx
- Commit: 42b9762

## Verification Results

- `pnpm build`: Compiled successfully, 0 type errors, home page now Dynamic (server-rendered)
- `pnpm test -- --run`: 33/33 tests pass (6 new + 27 existing); 1 pre-existing failure in middleware.test.ts (out of scope)
- Home page renders "Markets" heading (not Phase 1 "XPredict" placeholder)
- MarketCard renders question, odds bar, volume, deadline, source badge
- SourceBadge for Polymarket is a link with target="_blank"; for House is not a link
- Grid responsive: grid-cols-1 / sm:grid-cols-2 / lg:grid-cols-3

## Self-Check: PASSED

All 10 created/modified files verified present. Both task commits (42b9762, 99c9223) verified in git log.
