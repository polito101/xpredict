# Collaborative GSD Workflow — Setup Guide

## PM: one-time project setup (do this once per project)

1. Copy all files from this template to the project repo root.
2. Replace `[NAME]`, `[name]`, `[names]` placeholders in `CLAUDE.md`.
3. Set up GitHub ↔ Linear integration (native — no code needed):
   Settings → Integrations → GitHub in Linear.
4. Set up GitHub ↔ Slack integration for merge notifications to `#general`.
5. Commit everything: `git add . && git commit -m "chore: add collaborative GSD workflow"`
6. Create `ROADMAP.md` with your waves and phases using `/gsd:new-project` or manually.

## Devs: per-machine setup (do this once after cloning)

1. Copy `.env.example` to `.env.local`:
   ```powershell
   Copy-Item .env.example .env.local
   ```

2. Fill in all values in `.env.local`:
   - `ANTHROPIC_API_KEY` — your Anthropic API key
   - `SLACK_WEBHOOK_URL` — ask PM for the webhook URL
   - `LINEAR_API_KEY` — your personal Linear API key (Settings → API)
   - `LINEAR_TEAM_ID` — ask PM, or find in Linear Settings → Team
   - `LINEAR_IN_PROGRESS_STATE_ID` and `LINEAR_IN_REVIEW_STATE_ID`:
     ```powershell
     powershell -File .claude/hooks/linear-get-states.ps1
     ```

3. Verify hooks are active: open Claude Code in the project — it loads `.claude/settings.json` automatically on clone.

## Starting a phase

Pick your assigned phase from `ROADMAP.md`, then run:

```
/gsd:autonomous
```

Claude will guide you through the full flow. Your PR will be blocked until
PLAN.md and VERIFICATION.md exist. Linear and Slack are updated automatically.
