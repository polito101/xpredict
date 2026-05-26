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

You MUST update it at two moments, no exceptions:

| Moment | What to update |
|--------|----------------|
| **Before touching any code** (phase start) | Set status to `🔄 In progress`, fill in Owner and Branch |
| **When opening the PR** | Set status to `👀 In review`, fill in PR number |

Pol updates the row to `✅ Done` after merging. That's it — no Linear, no tickets.

### BLOCK rule — read this before starting any phase

**Read `PHASES.md` first.** If the target phase is NOT `⬜ Not started`, stop immediately and report:

> ⛔ Phase X is already `{status}` (owner: {owner}, branch: {branch}).
> Cannot start. Coordinate with {owner} or ask Pol to reassign.

Only proceed if the status is `⬜ Not started`. No exceptions.

## Mandatory workflow

Every phase completes this flow before a PR can be opened:

1. Update `PHASES.md` → `🔄 In progress`
2. `/gsd-plan-phase`     → generates `.planning/phases/XX/PLAN.md`
3. `/gsd-execute-phase`
4. `/gsd-verify-work`    → generates `.planning/phases/XX/VERIFICATION.md`
5. `/gsd-code-review`
6. Update `PHASES.md` → `👀 In review` + PR number
7. `/gsd-ship`           → opens the PR via GitHub MCP

PR creation is blocked automatically if `PLAN.md` or `VERIFICATION.md` are missing.

> **Light mode:** for straightforward phases use `/gsd-autonomous` — it covers steps 2–5 and 7 in one command. You still do steps 1 and 6 manually.

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
- **1 PR per phase.** Open PRs **via the GitHub MCP** (`create_pull_request`), not `gh`.
- Before opening, compare `PLAN.md` vs. what was implemented and produce the PR body.
- Only the PM approves/merges. A PR without a matching `PLAN.md` is blocked automatically.

## Slack
- `#general` — PR + merge notifications via native GitHub↔Slack integration.

## Environment
- GitHub MCP is pinned in `.mcp.json`, authenticated via a PAT from the `GITHUB_PERSONAL_ACCESS_TOKEN` env var (GitHub OAuth isn't usable — no MCP dynamic client registration). Set that env var per-dev (`setx`, or `~/.claude/settings.local.json` "env"); the repo stays secret-free.
- `.env.local` (optional, gitignored) only needs secrets. Never commit it.
- Python 3.12 + uv + Docker are required for backend phases.
