# XPredict — Onboarding & Workflow Guide

White-label prediction market platform. PM: Pol Bonet. Dev: Cuco.

## Devs: per-machine setup (do this once after cloning)

1. Copy `.env.example` to `.env.local`:
   ```powershell
   Copy-Item .env.example .env.local
   ```

2. Fill in all values in `.env.local`:
   - `LINEAR_API_KEY` — your personal Linear API key (Settings → API)
   - `LINEAR_TEAM_ID` — ask Pol, or find in Linear Settings → Team
   - `LINEAR_IN_PROGRESS_STATE_ID` and `LINEAR_IN_REVIEW_STATE_ID`:
     ```powershell
     powershell -File .claude/hooks/linear-get-states.ps1
     ```

3. Verify hooks are active: open Claude Code in the project — it loads `.claude/settings.json` automatically on clone.

## Starting a phase

Pick your assigned phase from `.planning/ROADMAP.md`, then run:

```
/gsd:autonomous
```

Claude will guide you through the full flow (discuss → plan → execute → verify → code-review → ship).

## PR workflow

When you finish a phase and are about to open the PR:

1. Make sure `PLAN.md` and `VERIFICATION.md` exist for the phase (the `check-phase-ready` hook will block the PR creation otherwise).
2. **Ask Claude in your session** to generate the PR body, e.g.:
   > "compara `.planning/phases/0X/PLAN.md` con lo que he implementado y dame el body del PR — qué tasks se completaron, qué quedó fuera, observaciones"
3. Save the output to a file (e.g., `.planning/phases/0X/PR-BODY.md`) or paste it directly into the PR description.
4. Open the PR with `gh pr create --body-file <file>` (or the GitHub UI).

Linear moves the issue to "In Review" automatically when the PR is opened. Slack `#general` gets the notification via the native GitHub↔Slack integration. There is no automatic AI summary in the loop — the dev owns the PR body.

## PM: one-time project setup (already done for XPredict)

This is documented for reference / future white-label spinoffs.

1. Copy all files from the collaborative-gsd-template to the repo root.
2. Replace `[NAME]`, `[name]`, `[names]` placeholders in `CLAUDE.md`.
3. Set up GitHub ↔ Linear integration (native — no code needed):
   Settings → Integrations → GitHub in Linear.
4. Set up GitHub ↔ Slack integration for PR + merge notifications to `#general`.
5. Commit and push.
6. Create `.planning/ROADMAP.md` with phases using `/gsd:new-project` (done — see `.planning/ROADMAP.md`).
