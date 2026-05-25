# HANDOFF — XPrediction

> Living operational state for multi-operator work (Pol + collaborators + Claude sessions).
> This is the **coordination layer on top of GSD** — formal phase truth stays in
> `STATE.md` / `ROADMAP.md`; this file captures what is ACTUALLY happening right now.
> **Read this (plus `ACTIVE_WORK.md` and `CURRENT_PHASE.md`) before any work. Update it when you stop.**

_Last updated: 2026-05-25 — by: Pol + Claude (Phase 1 close-out + coordination layer + official naming locked = XPrediction)_

## Snapshot

- **Phase 1 — Project Scaffold, Infra & Cross-Cutting Foundations:** ✅ **DONE (local).**
  Branch `gsd/phase-1-foundation`, 6 commits off `main` `c74bf0f`, **not pushed / not merged.**
  Backend (FastAPI scaffold, config, db, `/health`, Celery, Alembic) + frontend (the
  `xprediction-demo` UI integrated as the real visual base) + infra (`docker-compose`) + tooling.
  All green. Full detail: `docs/PHASE-1-FOUNDATION.md`.
- **Phase 2 — Auth & Identity:** 🟡 **IN PROGRESS by a collaborator, in parallel** (separate
  branch). **Do NOT start or touch Phase 2 from other sessions.** See `ACTIVE_WORK.md`.
- **Phases 3–11:** not started. See `ROADMAP.md`.

> ⚠️ **GSD vs reality:** `STATE.md` still shows "Phase 1 — Ready to plan (0%)" because Phase 1
> was built **out-of-band** (directly, not through the GSD `discuss→plan→execute→verify→ship`
> flow; no `PLAN.md` / `VERIFICATION.md` / PR yet). The code IS done; the formal GSD record is
> not. Whoever formalizes Phase 1 should reconcile `STATE.md` then (note it here).

## Next steps (proposed — do NOT auto-start; claim in ACTIVE_WORK.md first)

1. **Phase 1 → formalize + merge:** in a repo-rooted session, generate `PLAN.md` +
   `VERIFICATION.md` for Phase 1, push `gsd/phase-1-foundation`, open the PR via the GitHub MCP
   (`create_pull_request`). Only Pol merges.
2. **Phase 1 → live proof:** with Docker Desktop on, `docker compose up` and confirm
   backend ↔ Postgres (`/health/ready` → `ok`).
3. **Phase 2:** owned by the parallel collaborator — other sessions stay hands-off.

## What NOT to touch (right now)

- ❌ **Phase 2+ domain/business logic:** auth, users, sessions, protected routes, markets,
  wallets, settlement, ledger — owned elsewhere or not started.
- ❌ **GSD internals:** `STATE.md`, `ROADMAP.md`, `config.json`, `phases/` — owned by the GSD flow.
- ❌ **`main` directly** (PR-only; Pol merges). The separate `xprediction-demo` repo.
- ✅ Work only inside your own claimed branch/phase, after checking `ACTIVE_WORK.md`.
