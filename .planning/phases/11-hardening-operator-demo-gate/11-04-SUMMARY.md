---
phase: 11-hardening-operator-demo-gate
plan: 04
subsystem: regulatory-scaffold
tags: [regulatory, tos, operator-agreement, legal-scaffold, footer, sc6, plt-07, docs, frontend, human-verify]
status: in-progress  # Tasks 1+2 DONE; Task 3 (checkpoint:human-verify, gate=blocking-human) PENDING — Spanish-counsel deferral acknowledgment

# Dependency graph
requires:
  - phase: 03-wallet-double-entry-ledger
    plan: 02
    provides: "WAL-09 DB-level firewall: tokens non-transferable (no transfer destination), non-redeemable — the structural fact the regulatory/ToS skeletons assert as the only concrete legal claim"
provides:
  - "docs/regulatory.md — SC#6 regulatory-posture SKELETON: section headers + bracketed COUNSEL REVIEW / DEFERRED notes; the three-element test as headers (references PITFALLS, not re-authored); 'what keeps us safe' structural facts; geo-fencing + open counsel-review checklist (all deferred)"
  - "docs/terms-of-service.md — ToS PLACEHOLDER: NOT-LEGALLY-REVIEWED banner + section headers as [PLACEHOLDER] stubs; only concrete assertion = tokens have no monetary value / non-transferable / non-redeemable (matches WAL-09)"
  - "docs/operator-agreement.md — operator-agreement TEMPLATE STUB: the seven operator commitments as headers + signature-block placeholder, each a [TEMPLATE — counsel to finalize] stub"
  - "Player + admin UI footers linking to the ToS / token-policy docs (GitHub blob URLs) + the 'Play-money tokens have no monetary value.' trust note"
affects: [11-hardening-operator-demo-gate]

# Tech tracking
tech-stack:
  added:
    - "(none — three markdown skeletons + two markup-only layout edits; no package install, no new component, no route, no data fetch)"
  patterns:
    - "Legal/ToS content is SCAFFOLD-ONLY (CONSTRAINT 2): structure + bracketed COUNSEL/PLACEHOLDER/TEMPLATE/DEFERRED notes; no authored finished legal prose. The actual Spanish-counsel review is a deferred EXTERNAL dependency, represented via a checkpoint:human-verify gate, never faked with authored text."
    - "The one concrete legal assertion permitted is the structural token-value characterization (no monetary value, non-transferable, non-redeemable) because it mirrors the WAL-09 DB firewall — an engineering fact, not a legal conclusion."
    - "Footer link target = GitHub blob URL of the repo doc (https://github.com/polito101/xpredict/blob/main/docs/{terms-of-service,regulatory}.md) since v1 has no in-app /terms route — chosen for determinism (per plan)."
    - "Footer is markup-only: a <footer> element + next/link links reusing the existing responsive container (max-w-6xl + px-4 sm:px-6 player / px-6 admin) and the text-xs text-zinc-500 palette — no refactor of the branding <style> injection or any layout logic (CONSTRAINT 1)."

key-files:
  created:
    - "docs/regulatory.md (70 lines — section skeleton + counsel notes)"
    - "docs/terms-of-service.md (ToS placeholder)"
    - "docs/operator-agreement.md (operator-agreement template stub)"
    - ".planning/phases/11-hardening-operator-demo-gate/deferred-items.md (DEF-FE-BUILD-01 — pre-existing pnpm/Turbopack build failure, out of scope)"
  modified:
    - "frontend/src/app/layout.tsx (added next/link import + <footer> after {children})"
    - "frontend/src/app/admin/layout.tsx (added <footer> after </main>, reusing already-imported Link)"
    - ".planning/STATE.md (Current Position — 11-04 in-progress / awaiting human-verify; NOT advanced to complete)"

key-decisions:
  - "Footer hrefs use the GitHub blob URL of the committed repo docs (no in-app /terms route in v1) — deterministic, no static-serving assumption."
  - "regulatory.md headers + operator-agreement commitment list derive FROM .planning/research/PITFALLS.md §'The Regulatory Line' but reference it (pointer), they do NOT re-transcribe or re-author the legal analysis (CONSTRAINT 2)."
  - "The only concrete legal assertion across all three docs is the structural token-value statement (no monetary value / non-transferable / non-redeemable) — load-bearing because it matches WAL-09; everything else is a bracketed COUNSEL/PLACEHOLDER/TEMPLATE/DEFERRED note."
  - "Task 2 verify gate satisfied via `pnpm typecheck` (exit 0 — both layouts type-clean), NOT `pnpm build`: `pnpm build` fails identically on pristine HEAD with 10 pre-existing @radix-ui/@sentry/nextjs Turbopack module-resolution errors (Windows pnpm-symlink issue) entirely unrelated to the next/link footer edits. The plan's own acceptance criteria anticipate an out-of-scope build-graph problem (cites DEF-FE-01) and pin the gate to 'both layouts are type-clean.' Logged as DEF-FE-BUILD-01 in deferred-items.md."

requirements-completed: []  # PLT-07 is NOT closed by this plan: the SC#6 phase-gate stays open until the Task-3 human-verify counsel-deferral acknowledgment.

# Metrics
metrics:
  duration: ~18min
  completed: 2026-06-02
  tasks_done: 2
  tasks_pending: 1
  commits: 2
---

# Phase 11 Plan 04: Regulatory / ToS Scaffold (SC#6) Summary

**One-liner:** Scaffolded the SC#6 regulatory posture as structure-only skeletons — `docs/regulatory.md` (section headers + bracketed counsel-review notes), a `docs/terms-of-service.md` placeholder (NOT-LEGALLY-REVIEWED banner, only the WAL-09-matching no-monetary-value/non-transferable/non-redeemable assertion concrete), and a `docs/operator-agreement.md` template stub (the seven operator commitments as headers) — plus markup-only ToS/token-policy footer links in the player + admin layouts; the Spanish-counsel review is represented as a deferred external dependency, never authored.

## Status: IN-PROGRESS (autonomous work done; blocking human gate pending)

- **Task 1 (auto) — DONE.** Three doc skeletons created under `docs/`. Commit `89c6472`.
- **Task 2 (auto) — DONE.** Footer links added to both layouts. Commit `76c8806`.
- **Task 3 (checkpoint:human-verify, gate=blocking-human) — PENDING.** Counsel-review deferral acknowledgment. NOT executed — this is a blocking human gate; the plan is intentionally NOT marked complete.

## What Was Built

### Task 1 — Three regulatory/ToS/operator-agreement skeletons (commit `89c6472`)

- **`docs/regulatory.md`** (70 lines): a SECTION SKELETON. SCAFFOLD-ONLY banner; "Regulatory posture (v1: play-money)"; "The three-element test (Spain Ley 13/2011)" as headers noting v1 removes elements 1 (prize) + 3 (consideration), referencing PITFALLS rather than re-authoring; "What keeps us safe" (structural facts: system-granted tokens, non-transferable at DB level per WAL-09, non-redeemable, no monetary-prize leaderboard); "What breaks us" (pointer to the PITFALLS table, not a re-transcription); "Geo-fencing" (bracketed COUNSEL note); "Open counsel-review items" (a checklist of ToS / token policy / geo-block / operator agreement, each a `[DEFERRED: external counsel]` note). The phrase "Counsel review" appears 8×. Every substantive legal claim is a bracketed `[COUNSEL REVIEW REQUIRED: …]` / `[DEFERRED: external counsel]` note.
- **`docs/terms-of-service.md`**: a ToS PLACEHOLDER. Top blockquote banner "PLACEHOLDER — NOT LEGALLY REVIEWED. Counsel review is a gating dependency (see docs/regulatory.md)." Then the section headers a real ToS needs (Acceptance; Eligibility & geo-restrictions; Play-money tokens; Prohibited conduct; Account suspension; Disclaimers; Governing law — Spain), each a one-line `[PLACEHOLDER]` stub. The single concrete assertion: tokens have NO monetary value and are non-transferable / non-redeemable (structural, matches WAL-09).
- **`docs/operator-agreement.md`**: an operator-agreement TEMPLATE STUB. Banner "TEMPLATE STUB — binding operator policy; finalize with counsel before any operator signs." The SEVEN operator commitments from the PITFALLS "Operator-facing checklist" as `## 1.`–`## 7.` headers (will not enable token purchase; will not enable token redemption; will not award cash/prizes on bet outcomes; will geo-fence per the recommended list; will display ToS asserting tokens have no monetary value; will not advertise tokens as having monetary value; will obtain DGOJ license before any real-money plan), each a `[TEMPLATE — counsel to finalize]` stub, plus a signature-block placeholder.

**Task 1 verify:** `test -f` all three ✓; `grep -lE 'COUNSEL|PLACEHOLDER|TEMPLATE|DEFERRED'` matches all three ✓; regulatory.md = 70 lines (≥30) with "Counsel review" ×8 ✓; ToS "PLACEHOLDER" ×10 + "no monetary value" ×2 + "non-transferable" ×3 ✓; operator-agreement "TEMPLATE" ×14 + exactly 7 numbered commitment headers ✓.

### Task 2 — Footer links to ToS / token policy (commit `76c8806`)

- **`frontend/src/app/layout.tsx`** (player): imported `Link` from `next/link`; inserted a `<footer>` AFTER `{children}` and before `<Toaster />` (so the `min-h-full flex flex-col` body pushes it to the bottom). Two links — "Terms of Service" → `…/docs/terms-of-service.md`, "Token policy" → `…/docs/regulatory.md` (GitHub blob URLs) — plus the note "Play-money tokens have no monetary value." Responsive container `max-w-6xl px-4 sm:px-6`, `text-xs text-zinc-500`.
- **`frontend/src/app/admin/layout.tsx`** (admin): inserted the same `<footer>` AFTER `</main>`, inside the outer flex-col `<div>`, reusing the already-imported `Link` and the `max-w-6xl px-6` admin convention (with dark-mode variants matching the admin palette).

**Task 2 verify:** `pnpm typecheck` exit 0 (both layouts type-clean) ✓; player has `<footer>` + a `terms-of-service` href + the "no monetary value" note ✓; admin has `<footer>` + a `terms-of-service` href ✓; both match the `key_links` `terms` pattern ✓; responsive container convention present ✓; `git status` shows only the two layout edits + the three Task-1 docs ✓.

## Deviations from Plan

**1. [Out of scope — logged, NOT fixed] `pnpm build` fails on pristine HEAD (DEF-FE-BUILD-01)**
- **Found during:** Task 2 verification.
- **Issue:** `pnpm build` (Next.js 16.2.6 Turbopack) exits 1 with 10 `Module not found` errors for `@radix-ui/react-{dialog,dropdown-menu,label,select,separator,tabs,tooltip}` and `@sentry/nextjs` (×3). These packages ARE installed (verified present in `node_modules`) and ARE declared in `package.json`; `pnpm typecheck` (tsc) exits 0. The identical 10 errors reproduce on the CLEAN committed HEAD with both layouts reverted to their pre-11-04 state — proving the failure is a pre-existing Windows pnpm-symlink / Turbopack module-resolution issue (same class CLAUDE.md flags for PMS), NOT caused by the two `next/link` footer edits (next/link is absent from the error set).
- **Action:** Per the executor SCOPE BOUNDARY rule (pre-existing failures in unrelated files are logged, not fixed) and Phase 11 CONSTRAINT 1/3 (no refactor / no architecture / no lockfile change), NOT fixed. Logged to `.planning/phases/11-hardening-operator-demo-gate/deferred-items.md` as DEF-FE-BUILD-01. The plan's Task 2 acceptance criteria explicitly anticipate an out-of-scope build-graph problem (cites DEF-FE-01) and pin the real gate to "both layouts are type-clean," which `pnpm typecheck` (exit 0) confirms.
- **Files modified:** none (investigation only — backed up + restored the two layouts via the sanctioned single-file `git checkout --`, then re-applied).

No other deviations — Tasks 1 and 2 executed as written. No Rule 1/2/3 auto-fixes were needed; no architectural (Rule 4) decisions arose.

## Known Stubs (intentional — CONSTRAINT 2)

The three legal docs are deliberate scaffolds, NOT unintended stubs. This is the whole point of CONSTRAINT 2: legal content = structure + bracketed notes only.

| File | Stub | Reason / resolution |
|------|------|---------------------|
| docs/regulatory.md | All legal claims are `[COUNSEL REVIEW REQUIRED]` / `[DEFERRED: external counsel]` notes | Intentional. Resolved by the deferred external dependency: Spanish-counsel review (Task 3 acknowledges this, does not close it). |
| docs/terms-of-service.md | All sections are `[PLACEHOLDER]` (except the structural no-monetary-value assertion) | Intentional ToS placeholder pending counsel. |
| docs/operator-agreement.md | All seven commitments + signature block are `[TEMPLATE — counsel to finalize]` | Intentional template stub; binding text finalized with counsel. |

These stubs do NOT block the plan goal — SC#6 (closure-scoped per CONSTRAINT 2) is explicitly "scaffold + base + notes only." The plan documents the counsel review as the future resolver (an external dependency, not a future XPredict plan).

## Pending: Task 3 — Counsel-review deferral (blocking human gate)

Task 3 is a `checkpoint:human-verify` with `gate="blocking-human"`. Per the batched-checkpoint mode, the autonomous work (Tasks 1+2) shipped now; this blocking human gate is returned for explicit acknowledgment and the plan is NOT marked complete. Pol must confirm the three docs are SKELETONS only (no authored legal prose) and acknowledge Spanish-counsel review of the ToS + token policy as a gating external dependency this phase does not close (per STATE.md Blockers: "Spanish legal counsel must review ToS and token policy before any demo … this is a gating dependency on Phase 11 completion").

**Resume signal (verbatim from the plan):** `approved — scaffold accepted, counsel review acknowledged as deferred external dependency` (or describe required scaffold changes).

## Commits

- `89c6472` — docs(11-04): add regulatory/ToS/operator-agreement skeletons (SC#6)
- `76c8806` — feat(11-04): footer links to ToS / token policy in player + admin layouts (SC#6)

(The partial SUMMARY + STATE + deferred-items.md will be captured in a follow-up docs commit.)

## Self-Check: PASSED

- All created/modified files exist: docs/regulatory.md, docs/terms-of-service.md, docs/operator-agreement.md, frontend/src/app/layout.tsx, frontend/src/app/admin/layout.tsx, 11-04-SUMMARY.md, deferred-items.md.
- Both commits present in git log: `89c6472`, `76c8806`.
