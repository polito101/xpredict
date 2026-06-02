---
phase: 11-hardening-operator-demo-gate
plan: 06
subsystem: testing
tags: [audit, hardening, verification, pitfalls, demo-gate, ci, observability, regulatory]

# Dependency graph
requires:
  - phase: 11-01
    provides: prod-migration-dry-run CI gate (SC#3) — demo-trap evidence
  - phase: 11-02
    provides: security-scan CI gate (SC#4) + .zap/rules.tsv — secrets/security evidence
  - phase: 11-03
    provides: Sentry alert runbook (SC#5) — observability/monitoring evidence
  - phase: 11-04
    provides: regulatory scaffold (docs/regulatory.md + ToS + operator-agreement) — regulatory evidence
provides:
  - "docs/LOOKS-DONE-CHECKLIST.md — the executed SC#2 'Looks Done But Isnt' audit (32 rows, one per PITFALLS item)"
  - "A single demo-gate go/no-go artifact citing every Phase 11 workstream as closing evidence"
affects: [gsd-verify-work, gsd-ship, operator-demo, phase-11-closure]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Verify-only documentation audit: every checklist item is VERIFIED/CLOSED (evidence cited) or DEFERRED (reason + owner) — no blank rows, no re-implementation"
    - "Constraint-3 verify-only: wallet/ledger/concurrency rows cite existing tests/migrations + Pol's separate DEF-03-01 track, never re-fixed"

key-files:
  created:
    - docs/LOOKS-DONE-CHECKLIST.md
  modified: []

key-decisions:
  - "Self-bet ban (item 19) recorded as VERIFIED-by-architecture (structurally N/A in v1: no user-created markets; admins use a separate admin CRM surface, players a separate /bets surface) rather than citing a non-existent firewall — avoids a falsely-green row (T-11-06-01)"
  - "Wallet ledger migration cited as the real file 0004_phase3_wallet_ledger.py (the plan example said '0003' — that is the logical/STATE name; the on-disk file is 0004)"
  - "Backup-restore/PITR (items 26/27), Sentry round-trip (24/28), and Spanish-counsel ToS review (31) are the genuinely-external deferrals carried to the Task-2 human checkpoint"

patterns-established:
  - "Phase-11 synthesis artifact: one audit table is the SC#2 demo-gate, cross-referencing 11-01/02/03/04 deliverables"

requirements-completed: []  # PLT-07 is NOT yet complete — Task 2 (Pol sign-off) is the gating human-verify; mark complete only after approval

# Metrics
duration: ~14min
completed: 2026-06-02
---

# Phase 11 Plan 06: "Looks Done But Isn't" Executed Audit Summary

**`docs/LOOKS-DONE-CHECKLIST.md` — the SC#2 demo-gate: all 32 PITFALLS "Looks Done But Isn't" items recorded as VERIFIED / CLOSED BY PHASE 11 / VERIFY-ONLY (Pol track) / DEFERRED, each with concrete evidence; wallet/ledger/concurrency are verify-only against existing tests + Pol's DEF-03-01 track (never re-implemented).**

> **STATUS: PARTIAL — Task 1 DONE, Task 2 PENDING (blocking human-verify).** Per the operator's batched-checkpoint choice (approach A), the autonomous work is complete and committed; the plan is **NOT** marked complete. Task 2 (`checkpoint:human-verify`, gate=blocking) requires Pol's sign-off on the audit + its 4 external deferrals before phase closure.

## Performance

- **Duration:** ~14 min (autonomous portion)
- **Started:** 2026-06-02 (this session)
- **Completed (Task 1):** 2026-06-02
- **Tasks:** 1 of 2 complete (Task 2 = pending blocking human-verify)
- **Files modified:** 1 (`docs/LOOKS-DONE-CHECKLIST.md`)

## Accomplishments

- **Executed the full "Looks Done But Isn't" checklist** (`.planning/research/PITFALLS.md` lines 447–478, exactly 32 items) as a documented audit table — one row per item, columns `# | Item | Class | Result | Evidence`.
- **17 VERIFIED** (base invariants with cited evidence), **6 CLOSED BY PHASE 11** (dry-run / security-scan / Sentry runbook / regulatory scaffold), **6 VERIFY-ONLY (Pol track)** wallet/ledger/concurrency rows, **4 DEFERRED** (reason + owner). (Counts overlap because rows 13 and 31 carry two tokens.)
- **Cited every Wave-1/Phase-11 deliverable** as closing evidence: `prod-migration-dry-run.yml` (11-01), `security-scan.yml` + `.zap/rules.tsv` (11-02), `docs/runbooks/sentry-alerts.md` (11-03), `docs/regulatory.md` + `docs/terms-of-service.md` + `docs/operator-agreement.md` (11-04).
- **Honored constraint 3 verbatim:** the 5 wallet/ledger/concurrency rows are VERIFY-ONLY, cite existing tests/migrations (`test_concurrent_transfers.py`, `test_atomicity.py`, `reconcile.py`, migration `0004`), and explicitly name Pol's `DEF-03-01` isolation debt as out-of-scope — none re-implemented.
- **No source/test touched** — pure docs-only diff.

## Task Commits

1. **Task 1: Author `docs/LOOKS-DONE-CHECKLIST.md` (executed audit, one row per item)** — `df0038d` (docs)
2. **Task 2: Sign off the audit (deferrals + manual-verify items)** — PENDING (blocking `checkpoint:human-verify`; awaiting Pol)

**Plan metadata (this partial SUMMARY + STATE):** committed separately (docs).

## Files Created/Modified

- `docs/LOOKS-DONE-CHECKLIST.md` — the executed SC#2 audit: header (gate purpose + date), Result/Class legend, the 32-row audit table, a dispositions summary, the genuinely-external deferrals list, and a self-verification block.

## Verify evidence (Task 1 `<verify>` + acceptance criteria)

- `test -f docs/LOOKS-DONE-CHECKLIST.md` → present.
- `grep -Ec 'VERIFIED|VERIFY-ONLY|DEFERRED|CLOSED BY PHASE 11'` → **47** (acceptance: ≥ 28). ✓
- Line count → **110** (acceptance: ≥ 50). ✓
- Audit data rows (`^\| [0-9]+ \|`) → **32** (one per PITFALLS item; acceptance: ≥ 28). ✓
- Key-link patterns: `prod-migration-dry-run` → 2, `security-scan` → 6, `sentry-alerts.md` → 8 (all ≥ 1). ✓
- Wallet/ledger/concurrency rows: every match of `re-implemented`/`re-fixed` is a **negative** assertion ("NEVER re-implemented", "NOT re-fixed here", "none re-implemented") — no row claims a fix. ✓
- `git diff --stat HEAD~1 HEAD` (commit `df0038d`) → `docs/LOOKS-DONE-CHECKLIST.md` only, **110 insertions, 0 deletions** — docs-only, no source/test edit. ✓

## Decisions Made

- **Item 19 (self-bet ban) recorded as VERIFIED-by-architecture, not via a cited firewall.** A grep of `backend/app` found no explicit creator≠bettor constraint. In v1 markets are house-curated only (no user-created-market path); admins create/resolve via the `current_active_admin`-gated admin CRM, players bet only via the `current_active_player` `/bets` surface — the principal/route boundary makes "bet on a market you created" structurally unreachable. Recording a non-existent "Phase 5 self-bet firewall" would have produced exactly the falsely-green row the threat model (T-11-06-01) forbids. Added a v2 note (owner: Pol) for when user-created markets are introduced.
- **Cited the wallet ledger migration as `0004_phase3_wallet_ledger.py`** (the actual on-disk file) while noting the plan example's "migration 0003" is the logical/STATE name.
- Everything else followed the plan's evidence map.

## Deviations from Plan

None — plan executed exactly as written for Task 1 (a verify-only doc audit; no code/test changes, no deviation rules triggered). The two decisions above are evidence-accuracy refinements, not scope changes.

## Issues Encountered

- The plan's example evidence for item 19 referenced a "Phase 5 self-bet firewall" that does not exist as code. Resolved by recording the row accurately (VERIFIED-by-architecture) rather than fabricating evidence — see Decisions.

## User Setup Required

None for Task 1. **Task 2 is a human gate** (see below) — Pol's sign-off, not config.

## CHECKPOINT — Task 2 (blocking human-verify) — PENDING

**Resume signal (verbatim from the plan):** `Type "approved — audit accepted, deferrals acknowledged", or list any item that must be closed before the operator demo.`

Pol must, per `docs/LOOKS-DONE-CHECKLIST.md`:
1. Confirm every item is VERIFIED/CLOSED (with evidence) or DEFERRED with an acceptable reason + owner.
2. Confirm the wallet/ledger/concurrency rows are VERIFY-ONLY against existing tests + the separate backend-test-isolation track (constraint 3 — not re-implemented).
3. Acknowledge the genuinely-external deferrals for the demo gate: backup-restore/PITR (items 26/27, infra), the Sentry alert round-trip (items 24/28, tracked in `docs/runbooks/sentry-alerts.md` §5), and the Spanish-counsel ToS review (item 31, plan 11-04).
4. Approve the audit as the SC#2 gate, or flag any deferral that must be closed before the demo.

## Next Phase Readiness

- **SC#2 autonomous work is complete and committed** (`df0038d`). The audit is the Phase 11 synthesis artifact and is ready for Pol's review.
- **Blocking:** PLT-07 / SC#2 is **not** closed until Pol signs off (Task 2). Mark requirements complete only after approval.
- Phase 11 still has other open human-verify gates (11-03 Sentry round-trip, 11-04 counsel deferral, 11-05 visual QA) — this audit cross-references them, so a single coordinated Pol review session can clear several at once.

## Self-Check: PASSED

- `docs/LOOKS-DONE-CHECKLIST.md` → FOUND.
- Commit `df0038d` → present on `gsd/phase-11-hardening-operator-demo-gate`.
- Docs-only diff confirmed (no source/test edits).

---
*Phase: 11-hardening-operator-demo-gate*
*Plan: 06 — PARTIAL (Task 1 done, Task 2 pending blocking human-verify)*
*Completed (Task 1): 2026-06-02*
