# Phase 11 — Deferred / Manual Operator-Demo Gates

Phase 11 (Hardening & Operator-Demo Gate) shipped all autonomous deliverables and closed its
two review gates. Two verification gates require external runtime not yet available; they are
**deferred as documented manual-verify items** — they gate the **LIVE operator demo, NOT the
code merge**. Both have a ready runbook to close them.

## Status of the 4 Phase-11 human gates (operator decision 2026-06-02)

| Gate | Plan | Decision | Recorded in |
|------|------|----------|-------------|
| Regulatory scaffold ack | 11-04 (SC#6) | ✅ ACKNOWLEDGED | scaffolds accepted; counsel ToS review = gating external dep (below) |
| "Looks Done But Isn't" sign-off | 11-06 (SC#2) | ✅ SIGNED OFF | `docs/LOOKS-DONE-CHECKLIST.md` §sign-off |
| Sentry alert round-trip | 11-03 (SC#5) | ⏸️ DEFERRED (manual) | this file + `docs/runbooks/sentry-alerts.md` §5 |
| Responsive visual QA | 11-05 (SC#1/PLT-07) | ⏸️ DEFERRED (manual) | this file + `11-05-SUMMARY.md` |

---

## ⏸️ DEFERRED-1 — Sentry alert round-trip (SC#5, plan 11-03)
- **Why deferred:** rules + synthetic triggers need a deployed **staging** stack with a real `SENTRY_DSN` (Sentry is external SaaS — cannot be asserted in CI; same precedent as Phase 1 PLT-08).
- **Shipped:** `docs/runbooks/sentry-alerts.md` (4 rules + triggers + sign-off table); the 4 emit sites already exist in code. Only the live round-trip remains.
- **Owner:** Pol (operator).
- **How to close:** follow the runbook — define the 4 rules in Sentry UI, run the 4 synthetic triggers against `xpredict-staging`, confirm each alert fires to the channel, fill §5, commit.

## ⏸️ DEFERRED-2 — Responsive visual QA 360–768px (SC#1 / PLT-07, plan 11-05)
- **Why deferred:** needs the running app at mobile widths; the local `pnpm build` is environmentally broken (DEF-FE-BUILD-01 — Windows/Turbopack deep-path; reproduces on pristine HEAD; real CI builds fine). A stable preview/dev runtime is needed for the visual pass.
- **Shipped:** CSS/layout-only fixes (wallet/portfolio/market-detail/market-card) + `pnpm typecheck` clean. Only the human visual confirmation remains.
- **Owner:** Pol / operator.
- **How to close:** run the frontend (dev server or CI preview); check home / market-detail / bet flow / portfolio / wallet / auth at 360 / 390 / 414 / 768px — no horizontal scroll, thumb-reachable — per `11-05-SUMMARY.md`; record pass or list surface+width+issue.

---

## Other external deferrals (from `docs/LOOKS-DONE-CHECKLIST.md`, acknowledged at sign-off)
- **Spanish-counsel ToS + token-policy review** (plan 11-04) — gating external dependency before any real operator demo.
- **Backup-restore test + PITR** (infra; owner Pol).
- **Postgres metrics** (infra).

## DEF-FE-BUILD-01 (environmental — NOT a Phase-11 defect, NOT fixed here)
Local `pnpm build` fails in the deep session-worktree path (Windows pnpm-symlink + Turbopack module-not-found for `@radix-ui/*`/`@sentry/nextjs`); reproduces on pristine HEAD; real CI (shallow checkout) builds fine (proven on PR #16). Out of Phase-11 scope; do not fix here.
