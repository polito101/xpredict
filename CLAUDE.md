# Project: XPredict

## Roles
- **PM / Tech Lead:** Pol Bonet — creates roadmap, approves PRs
- **Devs:** Cuco — own full GSD flow per assigned phase

## Recommended mode
Use `/gsd:autonomous` by default — handles the full flow solo.
Switch to individual commands only if you need step-by-step control.

## Mandatory workflow
Every phase must complete this flow before a PR can be opened:

1. `/gsd:discuss-phase`
2. `/gsd:plan-phase`     → generates .planning/phases/XX/PLAN.md
3. `/gsd:execute-phase`
4. `/gsd:verify-work`    → generates .planning/phases/XX/VERIFICATION.md
5. `/gsd:code-review`
6. `/gsd:ship`           → triggers AI review + Slack notify + Linear update

The ship step is automatically blocked if PLAN.md or VERIFICATION.md are missing.

## Additional modes (use within your phase)
- `/gsd:spike`           → deep research before planning
- `/gsd:ultraplan-phase` → exhaustive plan for complex phases
- `/gsd:quick`           → quick subtasks within a phase

## Execution approach
Use subagents whenever possible — dispatch independent tasks in parallel
rather than executing them sequentially in the main session.
Reserve inline execution only for tasks that are strictly sequential
or require shared state from the previous step.

## PRs
- 1 PR per phase
- Before opening the PR, the dev asks Claude (in their session) to compare PLAN.md vs what was implemented and produce the PR body. Typical prompt: *"compara PLAN.md de la fase X con lo implementado y dame el body del PR (qué tasks se completaron, qué quedó fuera, observaciones)"*
- The dev passes that to `gh pr create --body-file <file>` (or pastes into the PR description)
- PM is the only one who approves/merges
- A PR without a corresponding PLAN.md will be blocked automatically (check-phase-ready hook)

## Linear
- 1 issue per phase — created automatically when you write PLAN.md
- Moves to "In Review" automatically when you open the PR
- PM closes the issue after merging

Convention: `[FASE-XX] Phase name`

## Slack
- Channel `#general` — PR + merge notifications via GitHub↔Slack native integration (no AI in the loop)

## Environment
Copy `.env.example` to `.env.local` and fill in all values before starting.
Never commit `.env.local`.
