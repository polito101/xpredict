# Project: XPredict

White-label, production-grade prediction market platform, built phase by phase via GSD.
(Not to be confused with `xprediction-demo` — a separate presentational UI demo, not integrated here.)

## Roles
- **PM / Tech Lead:** Pol Bonet — creates roadmap, approves/merges PRs
- **Devs / agents:** Cuco (+ others) — own the full GSD flow per assigned phase

## Multi-operator protocol (READ BEFORE ANY WORK)

XPredict is operated by multiple people and Claude sessions (Pol, collaborators, agents).
Treat it as **one coherent shared system, not isolated sessions.** This is a coordination
layer **on top of** GSD — it does not replace it.

**Before doing ANY work:**
1. Read `.planning/STATE.md`, `.planning/ROADMAP.md`, `.planning/CURRENT_PHASE.md`,
   `.planning/ACTIVE_WORK.md`, `.planning/HANDOFF.md`, and this `CLAUDE.md`.
2. Inspect git: `git status`, branches (`git branch -a`), recent commits
   (`git log --oneline -15`), and unmerged work (`git branch --no-merged main`).
3. Detect in-progress tasks, possible overlaps, active phases, and current ownership.
4. **If your intended work risks duplicating or colliding with claimed/in-progress work →
   STOP and report the conflict before implementing.** Do not proceed on a hunch.

**When you finish or pause ANY task:**
- Update `.planning/ACTIVE_WORK.md` (your row: status + date).
- Update `.planning/HANDOFF.md` (exact state, next steps, what NOT to touch).
- Leave the working tree clean with semantic commits.

**Source-of-truth split:** `STATE.md` + `ROADMAP.md` = formal GSD phase truth.
`CURRENT_PHASE.md` / `ACTIVE_WORK.md` / `HANDOFF.md` = live operational coordination.
If they disagree, reconcile explicitly (note it in `HANDOFF.md`) — never silently.

## Recommended mode
Use `/gsd-autonomous` by default — handles the full flow solo.
Switch to individual commands only if you need step-by-step control.

## Mandatory workflow
Every phase completes this flow before a PR can be opened (commands are **hyphenated**):

1. `/gsd-discuss-phase`
2. `/gsd-plan-phase`     → generates `.planning/phases/XX/PLAN.md`
3. `/gsd-execute-phase`
4. `/gsd-verify-work`    → generates `.planning/phases/XX/VERIFICATION.md`
5. `/gsd-code-review`
6. `/gsd-ship`           → opens the PR (via GitHub MCP) + Linear/Slack updates

PR creation is blocked automatically if `PLAN.md` or `VERIFICATION.md` are missing (`check-phase-ready` hook).

## Additional modes (within your phase)
- `/gsd-spike`           → deep research before planning
- `/gsd-ultraplan-phase` → exhaustive plan for complex phases
- `/gsd-quick`           → quick subtasks within a phase

## Autonomy & guardrails (`mode: "yolo"`)
High in-phase autonomy, deliberately bounded:
- Operates **inside the current phase branch** only — **never** directly on `main`.
- Gates remain **mandatory**: `plan_check`, `verifier`, `code_review` ON; a PR is required per phase; `auto_advance: false` (explicit phase transitions).

## Execution approach
Use subagents whenever possible — dispatch independent tasks in parallel rather than sequentially.
Reserve inline execution for strictly-sequential or shared-state steps.

## Branches & PRs
- **Per-phase branches** (`branching_strategy: "phase"`, template `gsd/phase-{phase}-{slug}`). Never commit directly to `main`.
- **1 PR per phase.** Open PRs **via the GitHub MCP** (`create_pull_request`), not `gh` — only the MCP path triggers the phase-ready gate + Linear move.
- Before opening, ask Claude to compare `PLAN.md` vs. what was implemented and produce the PR body.
- Only the PM approves/merges. A PR without a matching `PLAN.md` is blocked automatically.

## Linear (optional + tolerant)
- 1 issue per phase — created automatically when `PLAN.md` is first written (if configured).
- Moves to "In Review" automatically when the PR opens; PM closes it after merge.
- Non-secret team/state IDs live in `.claude/linear.shared.env` (committed). Personal `LINEAR_API_KEY` goes in `.env.local` (optional). With no key, Linear hooks skip cleanly.
- Convention: `[FASE-XX] Phase name`

## Slack
- `#general` — PR + merge notifications via native GitHub↔Slack integration.

## Environment
- GitHub MCP is pinned in `.mcp.json`, authenticated via a PAT from the `GITHUB_PERSONAL_ACCESS_TOKEN` env var (GitHub OAuth isn't usable — no MCP dynamic client registration). Set that env var per-dev (`setx`, or `~/.claude/settings.local.json` "env"); the repo stays secret-free.
- `.env.local` (optional, gitignored) only needs `LINEAR_API_KEY`. Never commit it.
- Python 3.12 + uv/poetry + Docker are needed only when executing product Phase 1.
