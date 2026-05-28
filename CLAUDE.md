# Project: XPredict

White-label, production-grade prediction market platform, built phase by phase via GSD.
(Not to be confused with `xprediction-demo` — a separate presentational UI demo, not integrated here.)

## Roles
- **PM / Tech Lead:** Pol Bonet — creates roadmap, approves/merges PRs
- **Devs / agents:** Cuco (+ others) — own the full GSD flow per assigned phase

## Recommended mode
Use `/gsd-autonomous` by default — handles the full flow solo.
Switch to individual commands only if you need step-by-step control.

## Phase tracking — MANDATORY (replaces Linear)

**`PHASES.md` in the repo root is the source of truth for who is doing what.**

The AI owns all updates to `PHASES.md`. The dev never edits it manually.

### Step 1 — Before touching any code (AI does this)

1. Read `PHASES.md`.
2. If the target phase is NOT `⬜ Not started` → **STOP**. Report:
   > ⛔ Phase X is already `{status}` (owner: {owner}, branch: {branch}).
   > Cannot start. Coordinate with {owner} or ask Pol to reassign.
3. If `⬜ Not started` → update the row: set `🔄 In progress`, fill in Owner (the dev who asked) and Branch (`gsd/phase-{N}-{slug}`). Commit the change with message `chore: mark phase {N} in progress in PHASES.md`.

### Step 2 — When opening the PR (AI does this)

Update the row: set `👀 In review`, fill in the PR number. Commit with `chore: mark phase {N} in review in PHASES.md`.

Pol updates the row to `✅ Done` after merging. That's the only manual step.

## Mandatory workflow

Every phase completes this flow before a PR can be opened:

1. ✏️ AI reads `PHASES.md` → blocks if taken, else marks `🔄 In progress` and commits
2. `/gsd-plan-phase`     → generates `.planning/phases/XX/PLAN.md`
3. `/gsd-execute-phase`
4. `/gsd-verify-work`    → generates `.planning/phases/XX/VERIFICATION.md`
5. `/gsd-code-review`
6. ✏️ AI marks `PHASES.md` → `👀 In review` + PR number and commits
7. `/gsd-ship`           → opens the PR (via `gh` or the GitHub MCP)

PR creation is no longer hook-blocked (the `check-phase-ready` gate was removed 2026-05-28). `PLAN.md` and `VERIFICATION.md` are still expected per the workflow above — enforcement is now on the dev/PM, not a hook.

> **Light mode:** for straightforward phases use `/gsd-autonomous` — it covers steps 2–5 and 7 in one command. Steps 1 and 6 are always done by the AI automatically.

> **Skip discuss:** `/gsd-discuss-phase` is optional. Only use it when the phase has ambiguity that planning alone can't resolve.

## Additional modes (within your phase)
- `/gsd-spike`           → deep research before planning (recommended for phases 3 and 6)
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
- **1 PR per phase** — though Pol may approve a **consolidated PR bundling multiple phases**. Open PRs with the **GitHub CLI** (`gh pr create`) or the GitHub MCP (`create_pull_request`). Never push to `main`.
- Before opening, compare `PLAN.md` vs. what was implemented and produce the PR body.
- Only the PM approves/merges. (The automatic `check-phase-ready` PR-gate hook was removed 2026-05-28 — a matching `PLAN.md` is still expected, but no longer hook-enforced.)

## Slack
- `#general` — PR + merge notifications via native GitHub↔Slack integration.

## Environment
- GitHub MCP is pinned in `.mcp.json`, authenticated via a PAT from the `GITHUB_PERSONAL_ACCESS_TOKEN` env var (GitHub OAuth isn't usable — no MCP dynamic client registration). Set that env var per-dev (`setx`, or `~/.claude/settings.local.json` "env"); the repo stays secret-free.
- `.env.local` (optional, gitignored) only needs secrets. Never commit it.
- Python 3.12 + uv + Docker are required for backend phases.
