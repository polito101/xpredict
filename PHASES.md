# XPredict — Phase Tracker

> **Single source of truth for phase progress.**
> Update this file **before touching any code** (mark In Progress) and **when opening the PR** (mark Done).
> No Linear. No exceptions.

| # | Phase | Owner | Status | Branch | PR |
|---|-------|-------|--------|--------|----|
| 1 | Scaffold & Foundations | Pol | ✅ Done | `gsd/phase-01-scaffold-foundations` | — |
| 2 | Auth & Identity | Pol | ✅ Done | `gsd/phase-02-auth-identity` | [#5](https://github.com/polito101/xpredict/pull/5) |
| 3 | Wallet & Double-Entry Ledger | Agustin | ✅ Done | `integration/phase-05-full` | [#8](https://github.com/polito101/xpredict/pull/8) |
| 4 | Markets Domain & HouseAdapter | Pol | ✅ Done | `gsd/phase-04-markets-domain-houseadapter` | [#6](https://github.com/polito101/xpredict/pull/6) |
| 5 | Bets, Settlement & First E2E Demo | Agustin | ✅ Done | `integration/phase-05-full` | [#8](https://github.com/polito101/xpredict/pull/8) |
| 6 | Polymarket Sync | Pol | ✅ Done | `gsd/phase-06-polymarket-sync-catalog-replication` | [#7](https://github.com/polito101/xpredict/pull/7) |
| 7 | Polymarket Auto-Resolution | Agustin | ✅ Done | `gsd/phase-07-polymarket-auto-resolution` | [#10](https://github.com/polito101/xpredict/pull/10) |
| 8 | Admin CRM | Pol | 👀 In review | `gsd/phase-08-admin-crm-user-management-audit-log-viewer` | [#14](https://github.com/polito101/xpredict/pull/14) |
| 9 | User App UX Polish & Real-Time | Agustin | ✅ Done | `gsd/phase-09-user-app-ux-polish-market-detail-real-time` | [#13](https://github.com/polito101/xpredict/pull/13) |
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

### ⚠️ Tracker drift — needs Pol's reconciliation (flagged 2026-05-29, by Agustin)

Git `main` shows **Phases 1–7 are ALL merged** (PRs #5, #6, #7, #8, #10) — backend modules `markets/`, `bets/`, `settlement/`, `integrations/polymarket/` are all present. But the trackers are stale and disagree:

- **This file** still shows phases **2, 4, 7 as `👀 In review`** — they're merged → should be `✅ Done` (left untouched: marking Done is Pol's step).
- **`.planning/ROADMAP.md`** progress table shows **4, 5, 7 as "Not started"**; ROADMAP checkboxes for 4/5/7 are unticked.
- **`.planning/STATE.md`** says `completed_phases: 5`, focus "Phase 6" (stale).
- **GSD `roadmap.analyze`** therefore sees 4 (checkbox unticked), 5 (no `.planning` artifacts committed — code landed via the bundled PR #8 but PLAN/SUMMARY/CONTEXT for phase 5 were not), and 7 (no SUMMARYs) as incomplete.

**Risk:** running `/gsd-autonomous` **without a phase filter** would start discovery at Phase 4 and try to re-do already-merged phases. Phase 9 below is being run with `--only 9` to avoid this.

**Recommended reconciliation (Pol):** tick ROADMAP boxes + mark `✅ Done` for 2/4/5/7, backfill phase-5 `.planning` artifacts (or mark intentionally-absent), and update STATE.md (`completed_phases: 7`).

#### ✅ RESOLVED 2026-05-30 — reconciled into PR #14

State advanced since Agustin's note (Phase 9 merged via PR #13; Phase 8 opened as PR #14). The reconciliation was applied **on the `gsd/phase-08` branch and folded into PR #14**, so it lands on `main` at merge — honouring the "never touch `main` directly" guardrail. Merge truth as of today: phases **1-7 + 9 merged**; **8 = PR #14 (this branch, in review)**; **10-11 not started**.

- **PHASES.md** — phases **2, 4, 7** flipped `👀 In review → ✅ Done` (merged via #5/#6/#10); **9 → ✅ Done** (#13). **8 stays `👀 In review`** (#14, not yet merged — Pol still owns the final merge).
- **`.planning/ROADMAP.md`** — checkboxes ticked for **4, 5, 7, 8, 9**; progress table set to Complete with merge dates.
- **`.planning/STATE.md`** — `completed_phases: 9`, focus **Phase 10**, position + continuity refreshed.
- **Phases 5 & 7 artifacts** — left **as-is** (no synthetic backfill). Their `.planning` is thin (Phase 5 has no committed PLAN/SUMMARY — code shipped via the bundled PR #8; Phase 7 has PLANs but no SUMMARYs), but the GSD SDK forces `disk_status: complete` whenever the ROADMAP checkbox is ticked (`init.cjs`: `if (roadmapComplete && diskStatus !== 'complete') diskStatus = 'complete'`). Ticking the boxes is therefore sufficient: `roadmap.analyze` now reports **phases 1-9 all complete, `next_phase: 10`**, so `/gsd-autonomous` **without a `--only` filter** resumes at **Phase 10** instead of re-discovering 5/7. Verified post-reconciliation.

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

### Phase 4 & 5 — parallel ownership & integration handshake (2026-05-27)

**Ownership split:**
- **Phase 4 (Markets Domain & HouseAdapter) — owner: Pol.** Pol owns the full GSD flow for Phase 4: branch, migrations, alembic chain management, PR, and merge. No one else opens Phase 4 work.
- **Phase 5 (Bets, Settlement & First E2E Demo) — owner: Agustin.** Advancing in PARALLEL with Phase 4 on branch `gsd/phase-05-bets-settlement` (based off the Phase 3 branch, since Phase 3 isn't merged to `main` yet).

**Why Phase 5 can run before Phase 4 merges (dependency split):**
- 🟢 *Parallel-safe now (no Phase 4 dep, no migration):* sign-up bonus (SC#4). The Phase 3 ledger is generic — `accounts.kind`/`transfers.kind` are `Text` (not enums) and `owner_type` already supports `market`, so new transfer kinds and per-market liability accounts are new rows/strings, NOT schema changes.
- 🟡 *Buildable against a thin `MarketReadPort`/`MarketResolvePort` Protocol + stub:* bet-placement ACID logic, `SettlementService` core, API schemas, frontend.
- 🔴 *Blocked until Phase 4 merges (the single integration point):* the Phase 5 migration `0005` (the `bets` table + FKs to `markets`/`outcomes`) — written ONLY after `0004` exists, chained off `0004`, to preserve the single-alembic-head invariant. Then swap the port stubs for Phase 4's real models + wire the admin resolution endpoint + the E2E demo.

**Conflict minimization:** Phase 5 lives in NEW modules (`app/bets/`, `app/settlement/`); it does NOT touch `app/markets/`, `app/integrations/market_source.py`, or `backend/alembic/versions/` during the parallel phase. Shared touches are append-only (`app/wallet/constants.py` string kinds, `app/auth/manager.py` `on_after_verify` bonus hook, `app/core/config.py`).

**Integration handshake (REQUIRED):** When **Phase 4 is merged** (row 4 flips to `✅ Done`; Slack `#general` posts the GitHub merge), that is Agustin's trigger to: (1) rebase `gsd/phase-05-bets-settlement` onto the updated `main` (Phase 1+2+3+4), (2) write migration `0005` off `0004`, (3) swap the market port stubs for Phase 4's real models, (4) finish the E2E demo. **Pol: please ping Agustin on merge so integration starts on your final base.**
