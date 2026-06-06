---
phase: 17
status: clean
reviewed: 2026-06-06
reviewers: 2 (independent, read-only)
findings: 1 HIGH, 2 MEDIUM, 4 LOW — all resolved
---

# Phase 17 — Code Review

Two independent read-only reviewers audited the full Phase-17 frontend diff (`df137f9..HEAD`) against the merged Phase-16 backend contract. **Gating verdicts:** the per-outcome **framing LOCK = PASS** (each outcome renders its own independent YES%; tests assert >100% sums to forbid normalization), **Security = PASS** (server-only `admin_jwt`→Bearer, no token leak, no XSS/`dangerouslySetInnerHTML`, no injection, backend `current_active_admin` is the real gate), **Accessibility = PASS**, **Brand/BRW-06 = PASS** (no stray hardcoded brand hue). No CRITICAL findings.

## Findings & dispositions

| ID | Sev | Finding | Disposition |
|----|-----|---------|-------------|
| H1 | HIGH | Edit sent `category: null` to clear, but the backend treats `null` as "no change" (`if body.category is not None`) → clearing silently failed while the success toast lied. | **FIXED** — `event-form.tsx`: edit now sends `category: ""` (the real clear; backend sets `""`, which the catalog excludes) and only when changed. |
| M2 | MED | Edit **always** sent `outcomes`, so a metadata-only edit triggered a full child DELETE+rebuild (new ids/slugs, **orphaned per-child price history**) on every save. | **FIXED** — `event-form.tsx`: the edit body now includes only the fields that actually changed (diff vs `initialValues`); `outcomes` is sent only when modified. |
| M1 | MED | Out-of-order `select()` race — a late earlier fetch could clobber the panel with the wrong child during rapid outcome switching. | **FIXED** — `event-detail-view.tsx`: a `latestSelectionRef` guard drops a stale response. **Regression test added** ("ignores a stale out-of-order fetch"). |
| L1 | LOW | Edit forced a future deadline even on an untouched/past field, blocking a metadata-only edit of a past/null-deadline event. | **FIXED** — `makeEventSchema("edit")` allows an empty deadline (= no change) and future-checks only a non-empty value; paired with the dirty-field send (M2). |
| L2 | LOW | Void preview copy said "positions" (counts outcomes, not bettors). | **FIXED** — `void-event-dialog.tsx`: "outcomes settle NO". |
| L3 | LOW | `EventCard` list key `o.yes_outcome_id ?? o.label` could collide on null-id duplicate labels. | **FIXED** — `event-card.tsx`: index tiebreaker `?? \`${label}-${idx}\``. |
| L4 | LOW | `partially_resolved`→Void was offered client-side (semantically odd; already-settled children can't be re-settled NO). | **FIXED (tightened)** — `event-detail-admin-actions.tsx`: Void gated to `open` only. (The server two-step preview is the authoritative guard regardless.) |

## Accepted / deferred (not changed)
- **Edit-mode `resolution_criteria` not editable/displayed** — the Phase-16 `UpdateEventRequest` has no `resolution_criteria` field and `EventDetail` doesn't carry it, so it can't be edited or surfaced here. Backend-contract limitation, documented; not a frontend bug.
- **`partially_resolved`→Resolve / Reverse offered** — correct for retrying a partial failure / undoing; the server two-step preview (`confirm:false`) errors before any mutation if a state combo is invalid, so a permissive gate is safe.
- **Verified-correct (no action):** `catalogMarketToMarketItem` (YES-only synth is fine — `MarketCard` derives NO as the complement, never reads a NO id), the bare `/admin/events` prefix + Bearer + `confirm` flag, the WS single-socket cap, the reused `OrderEntryForm` getting the child's REAL YES+NO via `fetchMarket`, the two-step preview/execute param parity, Next-16 async `params`/`searchParams`.

## Post-fix verification
- `tsc --noEmit` clean; `eslint` 0 errors (only the pre-existing/house-pattern `set-state-in-effect` warnings); affected + full `vitest` green (regression test for M1 included).
</content>
