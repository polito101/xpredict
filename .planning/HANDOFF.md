# HANDOFF — live operational state

> **Updated:** 2026-06-06 (planning reconciliation) · **Latest milestone:** v1.4 Premium Experience (shipped) · **No phase in flight, no open PRs.**
> Read this first. STATE.md + ROADMAP.md are the formal GSD truth; this is the live "what's happening NOW + what NOT to touch."
> **Verify live state from git (`git log`, `origin/main`, `gh pr ...`), not these docs alone — they drift.**

---

## TL;DR

**Everything started is shipped to `main`.** As of `origin/main` @ `2b2fca8`:

- ✅ v1.0 MVP (Phases 1-12) · ✅ v1.1 Demo Polish (Fases A-E) · ✅ v1.2 Credible Catalog (Phases 13-18, tag `v1.2`) · ✅ v1.3 Live-Bets demo (Fases LB-A/B/C, off-grid, `171aee5`) · ✅ v1.4 Premium Experience (Phase 19, PR #33, `2b2fca8`).
- **0 open PRs, 0 phase branches in flight.** Single alembic head `0011_livebets_bridge` (the old two-`0011`-heads divergence from the v1.3 merge is FIXED on main).
- `.planning/phases/` is **empty** — all phase dirs archived under `milestones/v{X.Y}-phases/`.

This session **reconciled the planning record** (it had drifted: STATE/HANDOFF still described "v1.2, awaiting v1.3" even though v1.3 + Phase 19 were already on main). v1.3 + Phase 19 are now folded in, with Phase 19 classified as its own milestone **v1.4 Premium Experience**.

**Next:** define the next milestone — `/gsd-new-milestone`. **Before any live operator demo:** close the Spanish legal review gate (the one hard blocker).

---

## What was reconciled (this branch: `chore/planning-reconcile-v1.3-v1.4`)

- **Archived** (no work was in flight): `LB-A-backend-bridge`, `LB-B-frontend-surface`, `LB-C-demo-harness` → `milestones/v1.3-phases/`; `phase-19-premium-experience` → `milestones/v1.4-phases/`.
- **Created:** `milestones/v1.3-MILESTONE-AUDIT.md`, `milestones/v1.4-MILESTONE-CONTEXT.md`, `milestones/v1.4-MILESTONE-AUDIT.md`.
- **Rewrote:** `STATE.md` (now v1.4 shipped / no active milestone), `ROADMAP.md` (+ v1.4), `MILESTONES.md` (+ v1.3 and v1.4 summaries — v1.3 had been missing), this `HANDOFF.md`.
- **Tags:** `v1.3` → `171aee5` (Merge gsd/livebets-demo), `v1.4` → `2b2fca8` (Merge PR #33).
- **Branch cleanup candidate:** `origin/gsd/phase-19-premium-experience` (merged; safe to delete on the remote).

## Latest milestone — v1.4 Premium Experience (Phase 19)

- **What shipped:** frontend-only "Obsidian & Spark" dark-first redesign; platform-first public landing (XPrediction as a white-label, API-first prediction-market platform); the live app moved behind auth; premium-restyled admin at `/admin/*`. Visible brand = **"XPrediction"** (technical names stay `XPredict/xpredict`). 238/238 frontend tests, `next build --webpack` green, CI `frontend` + security checks green.
- **Backend:** unchanged (one exception: a pure `ruff format` of already-merged v1.3 livebets files to unblock CI).
- **Integration handoff (carried as deferred):** point frontend env at the definitive backend (`BACKEND_URL`/`NEXT_PUBLIC_API_URL`/`NEXT_PUBLIC_WS_URL` + CORS/WS origin), set `tenant_config.brand_name = "XPrediction"`, drop the official logo PNG at `frontend/public/brand/xprediction-logo.png` (falls back to a faithful vector mark until then), and seed/verify demo data. Full per-screen backend-dependency matrix: `milestones/v1.4-phases/phase-19-premium-experience/HANDOFF.md`.

## Local runtime (for manual QA)

The `xpredict-run` docker stack is the QA handle — run it from a STABLE checkout, never a `.claude/worktrees/*` agent worktree (auto-cleans → breaks the backend). Recipe: regenerate `.env.local` from `.env.example` (`SECRET_KEY == ADMIN_JWT_PUBLIC_SECRET`, both 32+ chars), `docker compose ... up -d --build`, `alembic upgrade head`, `create_admin.py` (pass `FIRST_ADMIN_*` via `-e`), `seed_demo.py`. Surfaces on Phase 19 / main: `/` (marketing landing, public), `/markets` `/portfolio` `/wallet` `/live` (auth-gated → `/login`), `/admin/*`. **Emails in local go to Mailpit (`:8025`), never a real inbox** — that includes verification + password-reset.

## What NOT to touch

- **Don't push to `main` or self-merge** — PR-only; **only Pol merges**.
- Don't re-introduce a second alembic head — `0011_livebets_bridge` chains after `0011_phase13_market_groups`; keep it linear.
- Per-outcome framing: NEVER a stacked/normalized/sum-to-100 outcome bar (the gating visual invariant).
- Money discipline: never hand-write a ledger row / mutate `accounts.balance` / chain two self-committing services on one session (the 23505 landmine).
- White-label runtime branding pipeline: visible brand is runtime-driven (`/branding/current`) with real-operator override — don't hardcode a brand that breaks white-label.
- Don't revert `market_groups` in `_RESET_TABLES` (the DEMO-04 seed idempotency fix).

## Standing deferred items

| Category | Item | Status |
|----------|------|--------|
| legal (gating) | Spanish counsel review of ToS + token policy | Open — **not deferrable** before any live operator demo |
| human-UAT | Phase 12 `12-HUMAN-UAT.md` | 3 scenarios open |
| human-UAT | Phase 14 `14-HUMAN-UAT.md` | 2 scenarios open (live-runtime, deploy-only) |
| verification | Phases 03 / 04 / 05 | 3 VERIFICATION.md missing (backends shipped) |
| backend (Phase 17 follow-up) | Dedicated admin event-list endpoint + editable `resolution_criteria` | Deferred |
| frontend integration (v1.4) | env → definitive backend · brand_name · official logo PNG · seed | Open — handoff to Pol |

## Recommended next session

- **Decide + start the next milestone** (`/gsd-new-milestone`). Candidates: multi-tenancy runtime, real money (Stripe/KYC), full Polymarket catalog, live-bets productionization.
- Optionally close the cheap doc-debt: write the 3 missing Phase 03/04/05 `VERIFICATION.md` (backends already shipped + tested).
- **Gate:** the Spanish legal review must precede any operator-facing live demo.
