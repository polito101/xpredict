---
phase: 11-hardening-operator-demo-gate
plan: 03
subsystem: observability
tags: [sentry, alerting, runbook, observability, manual-verify, sc5, plt-08, docs]
status: in-progress  # Task 1 DONE; Task 2 (checkpoint:human-verify) PENDING — Sentry round-trip vs real staging DSN

# Dependency graph
requires:
  - phase: 01-scaffold-foundations
    plan: 04
    provides: "Sentry wired across api/worker/beat/frontend (init_sentry, service tag, send_default_pii=False); PLT-08 code-complete with alert rules deferred to Phase 11"
provides:
  - "docs/runbooks/sentry-alerts.md — SC#5 runbook: 4 alert-rule definitions (dataset/filter/aggregate/threshold/channel) for UI definition + one synthetic trigger per scenario tied to the existing in-code emit sites + a blank sign-off table for the manual-verify gate"
affects: [11-hardening-operator-demo-gate]

# Tech tracking
tech-stack:
  added:
    - "(none — no runtime/dev dependency added; no sentry-cli, no IaC. UI definition + runbook is the chosen path.)"
  patterns:
    - "Sentry alert rules are org-side config (Sentry UI/Alerts API), NOT a repo artifact in this stack — the version-controlled deliverable is a runbook + a human round-trip, not IaC and not a CI assertion (Sentry is external SaaS, cannot be asserted in CI without a live DSN)"
    - "Each alert rule filters on the service:-tag (api|worker|beat|frontend) set by init_sentry, plus a message/transaction match on the existing emit site"
    - "Settlement failure & reconciliation drift & auth-abuse burst use Static thresholds (> 0 in 5m); the Polymarket error-rate SPIKE uses a Percent-change threshold"
    - "Manual-verify sign-off table is the SC#5 gate (mirrors the Phase 1 PLT-08 Sentry round-trip precedent in 01-04-SUMMARY)"

key-files:
  created:
    - "docs/runbooks/sentry-alerts.md (207 lines)"
  modified:
    - ".planning/STATE.md (Current Position — 11-03 in-progress / awaiting human-verify; NOT advanced to complete)"

key-decisions:
  - "FastAPI synthetic trigger uses the REAL emit paths, not the dev-only /_sentry-test route (which returns 403 in staging/prod). The runbook references GET /api/sentry-test (the Next.js frontend route, which exists and captures service=frontend) for the api/frontend surface and the worker sentry_test_task for the worker surface; settlement/Polymarket/reconciliation/auth use their actual capture sites."
  - "Auth-abuse burst threshold documented accurately as the actual limit: 5/minute per-IP AND 5/minute per-email — the 6th login attempt in a 1-minute window returns the generic 429 (the plan text said '>6'; corrected to '>5 / the 6th attempt' per app/auth/rate_limit.py + router.py)."
  - "No emit-site code modified — verify-only on the existing capture sites (constraint 1). git diff --stat for 11-03 shows ONLY docs/runbooks/sentry-alerts.md."

requirements-completed: []  # PLT-07 is SC#1 (responsive), not this plan. SC#5/PLT-08 closure is NOT complete until the Task-2 human round-trip is signed off.

# Metrics
duration: ~12min (Task 1 only; Task 2 is a blocking human gate, not yet executed)
completed: null  # plan NOT complete — awaiting human-verify
---

# Phase 11 Plan 11-03: Sentry Alert Runbook (SC#5) Summary

**Authored `docs/runbooks/sentry-alerts.md` (207 lines) closing the PLT-08 alert-rule deferral: the four critical Sentry alert rules (settlement failure, Polymarket sync error-rate spike, ledger reconciliation drift, auth-abuse/failed-login burst) are each specified precisely enough to define in the Sentry UI (dataset, `service:`-tag filter, aggregate, threshold type+value, notification channel) and mapped to their existing in-code emit sites; one synthetic trigger per scenario reaches the real emit sites with zero code change; and a blank sign-off table is provided for the manual-verify gate. Task 1 (auto) is DONE and committed. Task 2 (`checkpoint:human-verify`, `gate="blocking-human"`) — Pol defines the rules + runs the synthetic round-trip against the real `xpredict-staging` DSN — is PENDING and is NOT auto-executable (Sentry is external SaaS).**

## Status

- **Task 1 (auto) — DONE.** `docs/runbooks/sentry-alerts.md` created and committed (`3fcdcc5`). All acceptance criteria pass.
- **Task 2 (`checkpoint:human-verify`, blocking-human) — PENDING.** The Sentry alert round-trip requires the real `xpredict-staging` DSN and a human to (1) define the 4 rules in the Sentry UI, (2) run the 4 synthetic triggers, (3) confirm each event + alert lands in the configured channel, (4) fill the sign-off table. This cannot be asserted in CI. **Plan 11-03 is therefore in-progress / awaiting human-verify — NOT complete.**

## Accomplishments (Task 1)

- **`docs/runbooks/sentry-alerts.md`** — closes the PLT-08 deferral (Sentry was code-complete in Phase 1 with "alert rules explicitly deferred to Phase 11", `01-04-SUMMARY.md`). Structure:
  - **§1 Purpose & model** — single project per env (`xpredict-staging` for verify), `init_sentry` is a no-op without a DSN, the `service` tag is the primary filter key, `send_default_pii=False` (no PII in synthetic triggers).
  - **§2 Notification channel** — Slack `#general` (recommended; already the GitHub↔Slack channel) or email; Pol picks one.
  - **§3 Four rule definitions** — each a table with Dataset / Filter (`service:` tag + match) / Aggregate / Threshold (Static `> 0 in 5m` for settlement, reconciliation, auth-abuse; Percent-change for the Polymarket spike) / Trigger action, plus the **real in-code emit site** named for each:
    - Settlement failure → `FastApiIntegration()` 500 capture (`main.py` lifespan) + `task_failure → capture_exception` (`celery_app.py`).
    - Polymarket sync spike → `capture_exception` in `app/integrations/polymarket/tasks.py` (`poll_failed`/`snapshot_failed`/`detect_failed`).
    - Reconciliation drift → `capture_message("wallet ledger drift …", level="error")` in `app/wallet/reconcile.py`; task `app.wallet.reconcile.reconcile_wallets`.
    - Auth-abuse burst → the `5/minute` per-IP + per-email limit on `login_proxy` → generic 429 via `_rate_limit_exceeded_handler` (`main.py`).
  - **§4 Synthetic triggers** — one concrete command per scenario, all reaching existing emit sites (worker `sentry_test_task`, `GAMMA_API_BASE_URL` redirect → `poll_polymarket_top25` failure, drift-row injection → `reconcile_wallets`, >5 failed `POST /auth/login` → 429 burst). Staging-only; drift + Gamma redirect are reverted after the test.
  - **§5 Sign-off table** — one blank row per rule (trigger run? / event in Sentry? / alert fired to channel? / verified by / date) — the SC#5 manual-verify gate.
  - **§6 Notes & caveats** — no IaC / no `sentry-cli`, no emit-site code changed, staging-only triggers, beat-vs-worker tag note.

## Verification (Task 1 — all pass)

- `test -f docs/runbooks/sentry-alerts.md` → present; **207 lines** (>= 60 required).
- Scenario grep (`Settlement|Polymarket|[Rr]econciliation|[Aa]uth`) → **23** matches (>= 4 required — names all four).
- Literal `app.wallet.reconcile.reconcile_wallets` present (key_link 1 resolves); `reconcile_wallets` present.
- `sentry-test` reference present (`GET /api/sentry-test` + `/_sentry-test`) — key_link 2 resolves.
- Each of the 4 rules specifies dataset + `service:`-tag filter + aggregate + threshold type+value + notification action.
- Sign-off table present with one row per rule (blank for Pol).
- `git diff --stat` shows **only** `docs/runbooks/sentry-alerts.md` — **no emit-site source file modified** (constraint 1 satisfied).

## Task Commits

1. **Task 1: Sentry alert runbook (SC#5 — 4 rules + synthetic triggers + sign-off)** — `3fcdcc5` (docs)

## Deviations from Plan

### Auto-fixed (documentation accuracy — Rule 1: corrected an inaccurate plan instruction against the real code)

**1. [Rule 1 — Accuracy] FastAPI synthetic route corrected to the real emit paths**
- **Found during:** Task 1 (reading `backend/app/main.py`).
- **Issue:** the plan `<action>` says reference `GET /api/sentry-test` for the FastAPI/api surface. In the code, `/api/sentry-test` is the **Next.js frontend** route (`frontend/src/app/api/sentry-test/route.ts`, `service=frontend`); the **FastAPI** synthetic route is `/_sentry-test` and it returns **403 in staging/prod** (`if not settings.is_dev: raise HTTPException(403)`), so it cannot be the staging synthetic trigger.
- **Fix:** the runbook references `GET /api/sentry-test` (frontend, exists — satisfies the key_link) and the worker `sentry_test_task`, and routes the settlement/api synthetic trigger through the real capture path (force a settlement exception) rather than the dev-only `/_sentry-test`. Both required key_link patterns (`reconcile_wallets`, `sentry-test`) resolve.
- **Files modified:** `docs/runbooks/sentry-alerts.md` only.
- **Commit:** `3fcdcc5`.

**2. [Rule 1 — Accuracy] Auth-abuse burst threshold corrected to the actual rate limit**
- **Found during:** Task 1 (reading `app/auth/router.py` + `app/auth/rate_limit.py`).
- **Issue:** the plan said "fire >6 failed login attempts". The actual limit is `5/minute` per-IP (decorator) AND `5/minute` per-email (`check_email_limit`) — the **6th** attempt within a 1-minute window trips the 429.
- **Fix:** the runbook documents "more than 5 within the 1-minute window (the 6th attempt → 429)".
- **Files modified:** `docs/runbooks/sentry-alerts.md` only.
- **Commit:** `3fcdcc5`.

> No emit-site code was changed in either case (constraint 1). These are documentation-accuracy corrections so the runbook matches the real code an operator will trigger.

## Awaiting human verification (Task 2 — blocking-human gate)

**Task 2 (`checkpoint:human-verify`, `gate="blocking-human"`) is NOT auto-executable** — it needs the real `xpredict-staging` DSN and a human round-trip (same shape as the Phase 1 PLT-08 manual-verify, `01-04-SUMMARY.md` §"Manual-verify items deferred"). The exact steps are in `docs/runbooks/sentry-alerts.md` §3 (define 4 rules), §4 (run 4 synthetic triggers), §5 (sign-off table). The `## CHECKPOINT REACHED` message returned to the orchestrator restates them verbatim.

**SC#5 / PLT-08 closure is gated on this round-trip** — do NOT mark plan 11-03 or SC#5 complete until the sign-off table in the runbook is filled (all four rules ☑ across trigger-run / event-in-Sentry / alert-fired) and committed.

## Self-Check: PASSED

**Files created (1):**
- `docs/runbooks/sentry-alerts.md` — FOUND (207 lines).

**Commits:**
- `3fcdcc5` — `docs(11-03): add Sentry alert runbook (SC#5 — 4 rules + synthetic triggers + sign-off)` — FOUND in git log.

**Constraint check:**
- `git diff --stat` for the commit shows only `docs/runbooks/sentry-alerts.md` (1 file, +207) — no app/Sentry-init code touched.

---

*Phase: 11-hardening-operator-demo-gate*
*Plan: 03*
*Status: IN-PROGRESS — Task 1 done (`3fcdcc5`); Task 2 (Sentry round-trip) PENDING human-verify against the real staging DSN. Plan NOT complete.*
