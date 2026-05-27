# XPredict — Phase Tracker

> **Single source of truth for phase progress.**
> Update this file **before touching any code** (mark In Progress) and **when opening the PR** (mark Done).
> No Linear. No exceptions.

| # | Phase | Owner | Status | Branch | PR |
|---|-------|-------|--------|--------|----|
| 1 | Scaffold & Foundations | Pol | ✅ Done | `gsd/phase-01-scaffold-foundations` | — |
| 2 | Auth & Identity | Pol | 👀 In review | `gsd/phase-02-auth-identity` | [#5](https://github.com/polito101/xpredict/pull/5) |
| 3 | Wallet & Double-Entry Ledger | Agustin | 🔄 In progress | `gsd/phase-03-wallet-double-entry-ledger` | — |
| 4 | Markets Domain & HouseAdapter | — | ⬜ Not started | — | — |
| 5 | Bets, Settlement & First E2E Demo | — | ⬜ Not started | — | — |
| 6 | Polymarket Sync | — | ⬜ Not started | — | — |
| 7 | Polymarket Auto-Resolution | — | ⬜ Not started | — | — |
| 8 | Admin CRM | — | ⬜ Not started | — | — |
| 9 | User App UX Polish & Real-Time | — | ⬜ Not started | — | — |
| 10 | Admin KPI Dashboard & Branding | — | ⬜ Not started | — | — |
| 11 | Hardening & Operator-Demo Gate | — | ⬜ Not started | — | — |

## Status legend

| Icon | Meaning |
|------|---------|
| ⬜ Not started | Nobody is working on it yet |
| 🔄 In progress | Branch created, work underway |
| 👀 In review | PR open, waiting for Pol to merge |
| ✅ Done | PR merged to `main` |
| 🚫 Blocked | Waiting on a dependency — note the blocker in comments below |

## Notes

<!-- Add per-phase notes here if needed, e.g. blockers, spike results, handoff context -->

### Phase 3 — Wallet & Double-Entry Ledger — HANDOFF for Pol (2026-05-27)

**Status:** Implementation complete (6/6 plans), branch `gsd/phase-03-wallet-double-entry-ledger`, HEAD `d9a42a7`, working tree clean, **not pushed** (push + PR are yours). Architecture is validated — please do not modify the validated ledger model.

**Delivered (9/9 requirements, 7/7 success criteria):**
- `accounts`/`transfers`/`entries` schema, migration `0003` (off `0002`, single head) — append-only immutability via deny-trigger + `REVOKE`, `CHECK (balance >= 0)`, `idempotency_key UNIQUE`, seeded `house_promo`/`house_revenue`.
- `WalletService` as the sole ledger writer (`SELECT … FOR UPDATE`); concurrency gate proven (25/25 concurrent, drift 0).
- Wallet auto-created in the **same transaction** as the user on registration (override of `UserManager.create()`).
- `POST /admin/wallets/{user_id}/recharge` (admin-gated, idempotent) + 3-layer no-user→user firewall (WAL-09).
- Player reads `GET /wallet/me/balance` + `/wallet/me/transactions` (money-as-string), Stripe stub (`NotImplementedError`), Next.js `/wallet` page.
- Nightly `reconcile_wallets` Celery task (CRITICAL log + Sentry on drift).
- Per-plan `*-SUMMARY.md` files in `.planning/phases/03-wallet-double-entry-ledger/`.

**Verification gates (green on the final integrated tree):** backend 35 integration (testcontainers) + 65 non-integration / 2 skipped · `ruff` + money-lint clean · single alembic head `0003` · frontend 29 vitest.

**Remaining GSD steps before the PR (no `VERIFICATION.md`/`SECURITY.md` yet):** `/gsd-verify-work 3` → `/gsd-code-review` → `/gsd-secure-phase 3`, then mark this row `👀 In review` + PR# and `/gsd-ship` (PR via GitHub MCP `create_pull_request`, repo-rooted session).

**Two PRE-EXISTING defects flagged (NOT Phase 3 regressions, intentionally NOT fixed — out of scope, recommend a separate cleanup task):**
- **DEF-03-01** — `backend/tests/core/test_audit_immutability.py` (Phase 1) poisons the session-scoped transaction without savepoint isolation, so running the *entire* backend integration suite in one process cascade-fails the wallet tests. Per-file / per-directory / non-integration runs are all green.
- **DEF-FE-01** — `frontend/src/__tests__/middleware.test.ts` (Phase 2, commit `8a9c186`) imports `../middleware`, which does not exist in the source tree → 1 failing suite (0 tests).
