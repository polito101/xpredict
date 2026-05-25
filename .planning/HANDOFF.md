# HANDOFF — XPrediction

> Living operational state for multi-operator work (Pol + collaborators + Claude sessions).
> This is the **coordination layer on top of GSD** — formal phase truth stays in
> `STATE.md` / `ROADMAP.md`; this file captures what is ACTUALLY happening right now.
> **Read this (plus `ACTIVE_WORK.md` and `CURRENT_PHASE.md`) before any work. Update it when you stop.**

_Last updated: 2026-05-26 — by: Pol + Claude (state reconciliation: Vercel project `xpredict` CONNECTED; PR #4 open but `blocked` by branch protection; prod deploy ● Error only because `main` lacks `frontend/` until merge)_

## Snapshot

- **Phase 1 — Project Scaffold, Infra & Cross-Cutting Foundations:** ✅ **DONE — in review.**
  Branch `gsd/phase-1-foundation`, **pushed to `origin`** (HEAD `829b191`). **PR #4 OPEN**
  (`gsd/phase-1-foundation` → `main`): `mergeable: true` (no conflicts) but **`mergeable_state: blocked`**
  by branch protection (review/checks required). Branch is **14 ahead / 3 behind** `main`
  (`main` is now `49ccd3b` after merges #1–#3) — no conflicts, no rebase needed.
  Backend (FastAPI scaffold, config, db, `/health`, Celery, Alembic) + frontend (the
  `xprediction-demo` UI integrated as the real visual base) + infra (`docker-compose`) + tooling.
  All green (`next build` + lint). Full detail: `docs/PHASE-1-FOUNDATION.md`.
  - **2026-05-25 — frontend UI-realism pass (commit `97fd984`, pushed to origin):** pre-launch
    product-integrity sweep on the landing. Removed invented metrics ($48M volume, 124k traders,
    per-market volume/traders, leaderboard accuracy/resolved/streak), neutralized named gov data
    feeds (Caltrans PeMS / NOAA / CAISO → generic signal types), and reframed simulated "live" data
    as honest "Preview / Sample / Concept". Visual design + layout unchanged; `next build` green
    (types + lint); verified desktop + mobile. 9 files in `frontend/src/`, all driven from
    `src/lib/mock-data.ts`. Lands inside the Phase 1 PR when opened.
- **Phase 2 — Auth & Identity:** 🟡 **IN PROGRESS by a collaborator, in parallel** (separate
  branch). **Do NOT start or touch Phase 2 from other sessions.** See `ACTIVE_WORK.md`.
- **Phases 3–11:** not started. See `ROADMAP.md`.
- **Frontend deploy (Vercel):** ✅ **CONNECTED** (by Pol, 2026-05-26). Project = **`xpredict`**
  (technical name; brand stays **XPrediction**) in Chiribito's Vercel team
  `chiribito293-7173s-projects`, **Root Directory = `frontend/`**, separate project/config/env —
  **Chiribito untouched**. Preview deploys build fine off branches/PRs. **Production deploys are
  currently ● Error — expected and harmless:** Production builds from `main`, and `main` does not
  contain `frontend/` yet (only `.planning/.claude/docs/.mcp.json`), so the Root Directory is absent
  there. **Production turns green automatically the moment PR #4 merges `frontend/` into `main` — no
  Vercel change needed.** Prod URL (once green): `https://xpredict-chiribito293-7173s-projects.vercel.app`.
  Details: `docs/DEPLOY.md`.

> ⚠️ **GSD vs reality:** `STATE.md` still shows "Phase 1 — Ready to plan (0%)" because Phase 1
> was built **out-of-band** (directly, not through the GSD `discuss→plan→execute→verify→ship`
> flow; no `PLAN.md` / `VERIFICATION.md` / PR yet). The code IS done; the formal GSD record is
> not. Whoever formalizes Phase 1 should reconcile `STATE.md` then (note it here).

## Next steps (proposed — do NOT auto-start; claim in ACTIVE_WORK.md first)

1. **Unblock + merge PR #4 (Pol only):** PR #4 (`gsd/phase-1-foundation` → `main`) is
   `mergeable: true` but `blocked` by branch protection. To land it, **approve the required review**
   (and let any required checks pass) **or temporarily relax the protection rule**, then merge via
   PR. **Do NOT force-merge; do NOT disable protections as a hack.** Only Pol merges.
   - On merge, `main` gains `frontend/` (+ backend/infra) → Vercel **Production** turns green
     automatically (Root Directory already = `frontend/`). No further Vercel action required.
2. **Reconcile `STATE.md` at merge:** it still shows "Phase 1 — Ready to plan" (built out-of-band,
   no `PLAN.md`/`VERIFICATION.md`). Update it when formalizing Phase 1's GSD record.
3. **Phase 1 → live proof (optional, later):** with Docker Desktop on, `docker compose up` and
   confirm backend ↔ Postgres (`/health/ready` → `ok`).
4. **Phase 2:** owned by the parallel collaborator — other sessions stay hands-off.

## What NOT to touch (right now)

- ❌ **Phase 2+ domain/business logic:** auth, users, sessions, protected routes, markets,
  wallets, settlement, ledger — owned elsewhere or not started.
- ❌ **GSD internals:** `STATE.md`, `ROADMAP.md`, `config.json`, `phases/` — owned by the GSD flow.
- ❌ **`main` directly** (PR-only; Pol merges). The separate `xprediction-demo` repo.
- ✅ Work only inside your own claimed branch/phase, after checking `ACTIVE_WORK.md`.
