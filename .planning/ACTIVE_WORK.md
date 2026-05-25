# ACTIVE WORK — XPrediction

> Who is doing what, right now. **Claim your work here before you start, and update the status
> when you stop.** This prevents two operators (or two Claude sessions) doing the same thing.
> Coordination layer on top of GSD — formal phase status lives in `STATE.md` / `ROADMAP.md`.

_Last updated: 2026-05-26_

## In progress / claimed

| Phase / task | Owner | Branch | Status | Updated | Notes |
|---|---|---|---|---|---|
| Phase 1 — Foundation & scaffold | Pol + Claude | `gsd/phase-1-foundation` | ✅ Done · **PR #4 open, `blocked` by branch protection** | 2026-05-26 | Backend + frontend + infra + UI-realism pass + deploy docs — all pushed (HEAD `829b191`). Vercel **connected** (project `xpredict`, Root Dir `frontend/`); prod ● Error only until `main` gets `frontend/` via merge. PR #4 `mergeable:true`. Next: Pol approves/merges PR #4 or relaxes protection — no hacks. See `HANDOFF.md`. |
| Phase 2 — Auth & Identity | Collaborator (parallel) | _owner: fill in_ | 🟡 In progress | 2026-05-25 | Built in parallel. Other sessions: **do NOT touch.** Owner: please fill branch + details. |

## Free / unclaimed

- Phases 3–11 (see `ROADMAP.md`) — unclaimed. **Claim a row here before starting.**

## How to use this file

1. **Before working:** read this table. If your intended work overlaps an "In progress" row →
   **STOP and coordinate** (see the protocol in `CLAUDE.md`).
2. **Claim:** add or update a row with your name, branch, and status **before** writing code.
3. **On stop:** update your row's Status + Updated, and update `HANDOFF.md`.
