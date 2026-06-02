# Sentry Alert Rules — Operator Runbook (SC#5 / PLT-08)

**Status:** alert-rule definitions ready for UI configuration · round-trip awaiting human verify against `xpredict-staging`
**Owner of the round-trip:** Pol (PM/Tech Lead)
**Closes:** the PLT-08 deferral — Sentry was code-completed in Phase 1 with "alert rules explicitly
deferred to Phase 11" (`01-04-SUMMARY.md`; REQUIREMENTS.md). This runbook is that closure.

---

## 1. Purpose & model

The four critical error-emit sites **already exist in the codebase** (verified — see the per-rule
"In-code emit site" rows below). This runbook does **not** add or change any of them. In this stack
Sentry alert rules are **org-side configuration** (defined in the Sentry UI / Alerts API), **not a
repo artifact** — so the deliverable is this version-controlled runbook plus a human round-trip, not
IaC and not a CI assertion (alert delivery cannot be asserted inside CI because Sentry is an external
SaaS that needs a live DSN).

**Single project per environment.** Sentry init (`backend/app/core/sentry.py` → `init_sentry`) uses
one project per env: `xpredict-dev` / `xpredict-staging` / `xpredict-prod`. This runbook is verified
against **`xpredict-staging`**. `init_sentry` is a **no-op when `SENTRY_DSN` is unset**, so the
staging stack must boot with the real DSN for any event to leave the process.

**The `service` tag is the primary filter key.** Every event is tagged
`service = api | worker | beat | frontend` (`sentry_sdk.set_tag("service", service)` in `init_sentry`).
The four FastAPI integrations live under `service:api`; all Celery tasks under `service:worker`
(and `service:beat` for beat-process events); the Next.js route handlers under `service:frontend`.
Each alert rule below filters on the `service:` tag plus a message/transaction match.

**No PII in events or synthetic triggers.** `init_sentry` sets `send_default_pii=False`, so request
bodies, headers, and user identifiers are **not** attached. The synthetic triggers below use
non-PII placeholder data and run **against staging only** (mitigates threat T-11-03-01). The
reconciliation-drift trigger deliberately writes a divergent row in the **staging DB only** and is
reverted after the test (threat T-11-03-02).

---

## 2. Notification channel

Pol picks **one** channel when defining the rules (either satisfies "configured notification channel"):

- **Slack `#general`** — the existing GitHub↔Slack channel already wired for PR/merge notifications
  (recommended: it is already operational), **or**
- **email** — to the operator alias.

Set the chosen channel as the **Trigger action** on all four rules. Record which was used in the
sign-off table (§5).

---

## 3. Alert rule definitions (define these four in Sentry → Alerts → Create Alert)

> Threshold guidance (current Sentry): **Static** = fixed count over a window; **Percent change** =
> compares the current window to the prior period (use it for the Polymarket "error-rate spike").
> Valid aggregates include `count()`, `percentage`, `failure_rate`, `p95`.

### Rule 1 — Settlement failure

| Field | Value |
|-------|-------|
| Dataset | Errors (events) |
| Filter | `service:worker OR service:api` AND the event is an unhandled exception on the settlement path (transaction/message matches `settle` / `resolve_market` / `SettlementService`) |
| Aggregate | `count()` |
| Threshold | **Static** — `> 0 in 5m` (any settlement exception is alert-worthy) |
| Trigger action | chosen channel (Slack `#general` or email) |
| In-code emit site | **API:** unhandled 500 captured by `FastApiIntegration()` (registered in `backend/app/main.py` lifespan, `init_sentry(service="api", integrations=[FastApiIntegration(), SqlalchemyIntegration()])`). **Worker:** the `task_failure` signal handler `_on_task_failure` → `sentry_sdk.capture_exception(...)` in `backend/app/celery_app.py` (fires when the settlement task raises). |

### Rule 2 — Polymarket sync error-rate spike

| Field | Value |
|-------|-------|
| Dataset | Errors (events) |
| Filter | `service:worker` AND message/transaction matches the Polymarket tasks (`poll_polymarket_top25` / `snapshot_odds` / `detect_polymarket_resolutions`, log keys `poll_failed` / `snapshot_failed` / `detect_failed`) |
| Aggregate | `count()` (or `failure_rate`) |
| Threshold | **Percent change** — e.g. `> 100% vs. prior 1h` (an error-**rate spike**, not a single error; tune the percentage to staging's baseline) |
| Trigger action | chosen channel |
| In-code emit site | `sentry_sdk.capture_exception(exc)` in `backend/app/integrations/polymarket/tasks.py` — `_run_poll_sync` (`poll_failed`), `_run_snapshot_odds` (`snapshot_failed`), `_run_detect_resolutions` (`detect_settle_failed` / `detect_failed`). |

### Rule 3 — Ledger reconciliation drift

| Field | Value |
|-------|-------|
| Dataset | Errors (events) |
| Filter | `service:worker` AND message matches `wallet ledger drift` (the `capture_message` text) |
| Aggregate | `count()` |
| Threshold | **Static** — `> 0 in 5m` (any drift is alert-worthy; the double-entry invariant must hold) |
| Trigger action | chosen channel |
| In-code emit site | `sentry_sdk.capture_message("wallet ledger drift on …", level="error")` in `backend/app/wallet/reconcile.py` (`_reconcile_with_session`), emitted per drifting account alongside the `wallet_ledger_drift` CRITICAL log. Task name: **`app.wallet.reconcile.reconcile_wallets`** (scheduled nightly 03:00 UTC as `reconcile-wallets-nightly`; the seeded `house_promo` account is excluded so it never cries wolf). |

### Rule 4 — Auth-abuse / failed-login burst

| Field | Value |
|-------|-------|
| Dataset | Errors (events) — OR a transactions/metric alert on the `429` response code if events are sparse |
| Filter | `service:api` AND the `POST /auth/login` transaction returning HTTP `429` (rate-limit burst) |
| Aggregate | `count()` |
| Threshold | **Static** — `> 0 in 5m` (a sustained 429 burst on login indicates credential-stuffing / brute force) |
| Trigger action | chosen channel |
| In-code emit site | The generic-429 path: `@limiter.limit("5/minute", …)` on `login_proxy` plus the per-email `check_email_limit(...)` (both `5/minute`) in `backend/app/auth/router.py` + `backend/app/auth/rate_limit.py`; the global `_rate_limit_exceeded_handler` in `backend/app/main.py` returns the generic 429 (never reveals whether the email exists — T-02-08/T-02-10). The **6th** login attempt within a 1-minute window trips the limit. |

---

## 4. Synthetic triggers (one concrete command per scenario)

All commands reach the **existing** emit sites — **no new code**. Run them with the staging stack up
and the real `SENTRY_DSN` set. (Note: the FastAPI dev-only `/_sentry-test` route returns **403** in
staging/prod, so the synthetic triggers below use the *real* emit paths, not that dev route.)

### 4.1 Settlement failure (Rule 1)

- **API surface (round-trip smoke):** in a dev/staging shell with `is_dev` true, `GET /_sentry-test`
  raises and the FastAPI integration captures it (`service:api`). In staging (where `/_sentry-test`
  is 403), drive the real path instead by forcing a settlement exception on a staging market
  (e.g. resolve a market whose outcome mapping is intentionally invalid) so `SettlementService`
  raises and is captured.
- **Worker surface:** trigger the worker-side capture via the synthetic worker task, which exercises
  the same `task_failure → capture_exception` plumbing the settlement task uses:
  ```
  docker compose exec backend celery -A app.celery_app call app.core.sentry.sentry_test_task
  ```
  Expect a `service:worker` event ("sentry test from worker"). For a true settlement-task failure,
  call the real settlement task against a deliberately-broken staging market.

### 4.2 Polymarket sync error-rate spike (Rule 2)

Induce repeated poll errors so the percent-change threshold trips:

1. In the **staging** env only, point the Gamma client at an unreachable host:
   set `GAMMA_API_BASE_URL` to a non-routable URL (e.g. `https://gamma.invalid/`).
2. Let the scheduled `poll_polymarket_top25` run a few cycles (every 30s), or force it:
   ```
   docker compose exec backend celery -A app.celery_app call app.integrations.polymarket.tasks.poll_polymarket_top25
   ```
   Each failure logs `poll_failed` and calls `capture_exception` (`service:worker`).
3. **Revert** `GAMMA_API_BASE_URL` to the real value after the burst is observed.

### 4.3 Ledger reconciliation drift (Rule 3)

1. In the **staging DB only**, inject a synthetic drift row — mutate one `accounts.balance` so it
   diverges from its ledger (`SUM(credit) - SUM(debit)` over `entries`). Pick a user wallet, not the
   excluded `house_promo` singleton. Example:
   ```sql
   -- staging only: bump one user wallet's cached balance off its ledger
   UPDATE accounts SET balance = balance + 1.0000 WHERE id = '<some-user-account-id>';
   ```
2. Run the reconciliation task:
   ```
   docker compose exec backend celery -A app.celery_app call app.wallet.reconcile.reconcile_wallets
   ```
   Expect a CRITICAL `wallet_ledger_drift` log line **and** a Sentry `wallet ledger drift on …`
   message (`level="error"`, `service:worker`).
3. **Revert** the injected drift (restore the original balance) so staging data is clean again
   (threat T-11-03-02 mitigation):
   ```sql
   UPDATE accounts SET balance = balance - 1.0000 WHERE id = '<some-user-account-id>';
   ```
   Re-run the task once more to confirm a clean `reconcile_clean` line.

### 4.4 Auth-abuse / failed-login burst (Rule 4)

Fire **more than 5** failed `POST /auth/login` attempts within the 1-minute rate-limit window from a
single IP so the **6th** attempt returns `429`:
```
# repeat >5 times within 60s against staging
curl.exe -i -X POST https://<staging-host>/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data "username=notarealuser@example.com&password=wrong"
```
The first five return `401`; the sixth returns the generic `429`
(`{"detail":"Too many requests. Please try again later."}`). Confirm Rule 4 fires on the 429 burst.
Use a throwaway non-PII email (no real account is needed — the limiter trips regardless of whether
the email exists, by design).

---

## 5. Sign-off table — manual-verify gate (Pol completes against the real `xpredict-staging` DSN)

This is the SC#5 verification gate. Nothing here can be asserted in CI (Sentry is external SaaS —
the Phase 1 PLT-08 round-trip was handled the same way; see `01-04-SUMMARY.md` §"Manual-verify items
deferred"). Fill one row per rule, then commit the completed table.

**Notification channel used:** ____________________ (Slack `#general` / email)

| Rule | Synthetic trigger run? | Event visible in Sentry? | Alert fired to channel? | Verified by | Date |
|------|------------------------|--------------------------|-------------------------|-------------|------|
| 1 — Settlement failure | ☐ | ☐ | ☐ | | |
| 2 — Polymarket sync error-rate spike | ☐ | ☐ | ☐ | | |
| 3 — Ledger reconciliation drift | ☐ | ☐ | ☐ | | |
| 4 — Auth-abuse / failed-login burst | ☐ | ☐ | ☐ | | |

**Resume signal:** the phase gate is cleared once all four rows are ☑ across all three columns
(or any gap is reported with the failing rule named). Reply `approved` when the table is complete.

---

## 6. Notes & caveats

- **No IaC, no `sentry-cli` dependency.** UI definition + this runbook is the chosen path (lower risk,
  no Sentry auth token in CI — RESEARCH Open Question 1 / A2). If alert config should later be
  version-controlled, that is a follow-up that adds `sentry-cli`/Alerts-API IaC.
- **No emit-site code was modified.** This plan is verify-only on the existing capture sites
  (constraint 1). `git diff --stat` for plan 11-03 shows only `docs/runbooks/sentry-alerts.md`.
- **Staging-only synthetic triggers.** The drift injection and the `GAMMA_API_BASE_URL` redirect run
  against staging and are reverted; production data is never touched.
- **Beat vs worker tag:** beat-process events carry `service:beat`; the synthetic worker task and the
  scheduled tasks run under `service:worker`. Rules filter on `service:worker` (broaden to include
  `service:beat` only if a beat-side capture is expected).
