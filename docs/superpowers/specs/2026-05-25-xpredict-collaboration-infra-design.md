# XPredict — Shared Collaboration Infrastructure (AI-native team)

**Date:** 2026-05-25
**Status:** Approved design → ready to implement
**Scope:** Repo configuration, hooks, MCP, and onboarding docs ONLY. No application code. No migration of `xprediction-demo`.

---

## Context

`xpredict` (`github.com/polito101/xpredict`, branch `main`) is a GSD planning scaffold: `.planning/` (PROJECT, REQUIREMENTS, ROADMAP — 11 phases, STATE, config.json, research/), `.claude/` (settings.json + 4 PowerShell Linear hooks), `CLAUDE.md`, `README-SETUP.md`, `.env.example`, `.gitignore`. No app code, no `package.json` yet — that is created in product Phase 1.

This repo is the **central shared GitHub repo** for collaborative work from Claude Code by the owner, other devs, and agents. Before building product on top, the collaboration infrastructure must be stable, clean, and turnkey.

The pre-implementation audit surfaced gaps the design below closes:
- Docs use colon command notation (`/gsd:autonomous`); the installed GSD (get-shit-done-redux) exposes **hyphenated** skills (`/gsd-autonomous`).
- Hooks fire on the MCP tool `mcp__github__create_pull_request`, but no project-pinned GitHub MCP exists; the connected server is plugin-namespaced (`plugin:github:github`), so the matchers would not fire as written.
- `README-SETUP.md` tells devs to open PRs with `gh pr create`, which (a) is not installed and (b) bypasses the MCP-tool hooks.
- `git.branching_strategy` is `"none"` while the workflow is "1 PR per phase" — work would land on `main` with no branch to PR from.
- Linear hooks crash (`$ErrorActionPreference = "Stop"`) for anyone without a Linear API key.

## Goals

Anyone with repo access can, with no tribal knowledge:
1. Clone the repo.
2. Open Claude Code.
3. Connect the required MCP (GitHub) via a versioned prompt + OAuth — no token files.
4. Run GSD workflows with the correct (hyphenated) commands.
5. Work on an isolated per-phase branch.
6. Open a PR through the standard path that triggers the phase-ready gate and Linear automation.

## Non-goals (explicitly deferred)

- Migrating / integrating `xprediction-demo` (the separate Next.js UI demo).
- Moving any frontend or product code.
- Any large refactor.
- Standing up backend/frontend scaffolds (that is product Phase 1).

---

## Confirmed decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | GitHub MCP standard | **Official remote MCP over OAuth, pinned in versioned `.mcp.json`** (key `github`, `https://api.githubcopilot.com/mcp/`). No PAT files. |
| D2 | PR mechanism | **Only** via the GitHub MCP `create_pull_request` tool (so hooks fire). `gh pr create` is not the supported path. |
| D3 | Branching | **Per-phase** (`branching_strategy: "phase"`, template `gsd/phase-{phase}-{slug}`). 1 PR per phase. |
| D4 | Linear | **Optional + tolerant.** Non-secret IDs versioned; only the personal API key is per-dev; hooks skip cleanly when absent. |
| D5 | `mode: "yolo"` | **Keep**, with documented guardrails (see below). Existing gates already enforce control. |
| D6 | Onboarding docs | Rewritten to match reality. |
| D7 | `.gitignore` | Add common preventive ignores. |

---

## Design by area

### 1. Branching per phase
- Set `.planning/config.json` → `git.branching_strategy: "none" → "phase"` (prefer the official `/gsd-config` mechanism; fall back to a minimal direct edit only if needed). Keep `phase_branch_template: "gsd/phase-{phase}-{slug}"`. Keep `auto_advance: false`.
- Effect: each phase executes on its own branch; one PR per phase; `main` is never written to directly.

### 2. GitHub MCP pinned in `.mcp.json`
- New repo-root `.mcp.json`:
  ```json
  {
    "mcpServers": {
      "github": {
        "type": "http",
        "url": "https://api.githubcopilot.com/mcp/"
      }
    }
  }
  ```
- On clone + open, Claude Code prompts to enable the project MCP; the dev approves and authenticates via OAuth.
- Server key `github` ⇒ tools namespaced `mcp__github__*` ⇒ the existing hook matchers (`mcp__github__create_pull_request`) match with **no matcher change**.
- **Implementation check:** confirm the remote server's PR-creation tool is exactly `create_pull_request` before relying on it; if the name differs, align the hook matchers in `.claude/settings.json` to the real name.

### 3. PR workflow + hooks
- Single PR path: the GitHub MCP `create_pull_request` tool. This triggers:
  - **PreToolUse `check-phase-ready.ps1`** — blocks the PR when the active phase lacks `PLAN.md` or `VERIFICATION.md`. Kept as-is (already correct).
  - **PostToolUse `linear-to-review.ps1`** — moves the Linear issue to "In Review". Kept + hardened (§4).
- **PostToolUse `Write` → `linear-create-issue.ps1`** — creates the Linear issue when `PLAN.md` is first written. Kept + hardened (§4).
- Docs drop the `gh pr create` instruction (kept only as an explicitly-labeled fallback that bypasses the hooks).

### 4. Linear: optional + tolerant
- New versioned file `.claude/linear.shared.env` holding only the **non-secret** IDs:
  ```
  LINEAR_TEAM_ID=8c876d02-8e58-429a-8c32-c8aa422e6784
  LINEAR_IN_PROGRESS_STATE_ID=2b9dc3bb-7b09-4a1e-8225-c4aa86588b87
  LINEAR_IN_REVIEW_STATE_ID=cf519e9b-3eb6-4dd0-ac4b-d7758115e5b4
  ```
- `.gitignore` keeps ignoring `*.env` / `.env.local` but adds a negation `!.claude/linear.shared.env` so the shared file is tracked.
- Personal `.env.local` then needs **only** `LINEAR_API_KEY` (optional).
- All three hooks: load `.claude/linear.shared.env` first, then `.env.local` (personal overrides). If `LINEAR_API_KEY` is still unset → **skip cleanly** (`Write-Host "Linear not configured — skipping"; exit 0`). Remove the top-level `$ErrorActionPreference = "Stop"` crash path; wrap the API call so a missing key or a network failure never blocks a dev/agent or spams errors. `check-phase-ready.ps1` stays strict (it is the PR quality gate, not Linear).

### 5. `mode: "yolo"` guardrails (documented in CLAUDE.md)
Keep `mode: "yolo"` for high in-phase autonomy, documented explicitly so it can never drift into chaos on the shared repo:
- It operates **inside the current phase branch** only.
- It **never** implies direct work on `main`.
- The gates remain **mandatory**: `plan_check`, `verifier`, and `code_review` stay ON; a PR is required per phase; `auto_advance` stays `false` (explicit phase transitions).
- Net: phase branches + mandatory PR + verifier/code_review ON + `auto_advance: false` give enough control to run high autonomy without destabilizing the shared repo.

### 6. Onboarding documentation (rewrite to match reality)
- **`README-SETUP.md`** rewritten:
  - Prereqs: Node + Git + Claude Code (present). Python 3.12 + `uv`/`poetry` + Docker are needed only **when executing product Phase 1**, not for planning — stated explicitly.
  - Setup: clone → open Claude Code → approve the prompted `github` MCP → OAuth login.
  - GSD commands are **hyphenated**: `/gsd-autonomous`, `/gsd-discuss-phase`, `/gsd-plan-phase`, `/gsd-execute-phase`, `/gsd-verify-work`, `/gsd-code-review`, `/gsd-ship`, `/gsd-spike`.
  - `.env.local`: only `LINEAR_API_KEY` (optional); shared IDs are already committed.
  - Branching: per-phase branches are created automatically; one PR per phase.
  - PR flow: open the PR via the GitHub MCP so the phase-ready gate + Linear automation fire; `PLAN.md` and `VERIFICATION.md` must exist first.
  - Clarify: **`xpredict` is the real project; `xprediction-demo` is a separate presentational UI demo, not integrated yet.**
- **`CLAUDE.md`** aligned: hyphenated commands, correct PR path, and the §5 `mode: "yolo"` guardrails.

### 7. `.gitignore` preventive ignores
Add common entries so the first product scaffold cannot stage junk: `node_modules/`, `.next/`, `dist/`, `build/`, `__pycache__/`, `.venv/`, `*.log`, `.DS_Store`. Preserve existing secret ignores and the `!.claude/linear.shared.env` negation.

---

## Verification (must pass before declaring done)

1. `.mcp.json` parses; opening Claude Code in the repo prompts for the `github` MCP; after OAuth, `claude mcp list` shows it connected; the PR-creation tool name is confirmed (`create_pull_request`) and matches the hook matchers.
2. `check-phase-ready.ps1` blocks a simulated `create_pull_request` when the active phase has no `PLAN.md`/`VERIFICATION.md`, and passes when both exist.
3. The Linear hooks, run with **no** `LINEAR_API_KEY`, exit 0 with a clean skip message (no thrown error); run **with** the shared IDs + a key, they target the correct team/states.
4. `branching_strategy` reads `"phase"`; the phase branch template is intact.
5. `README-SETUP.md` and `CLAUDE.md` contain zero `/gsd:` colon commands and zero `gh pr create` as the primary path; the xpredict-vs-demo distinction is stated.
6. `git status` shows only the intended infra files changed/added; nothing else touched; no app code created.

## Git policy for this work

All of the above creates/edits files but is **not committed or pushed** without the owner's explicit OK. The owner controls git on the shared repo. When authorized, changes land as one focused infra commit (or a small logical set), on a branch if the owner prefers.

---

*Design approved 2026-05-25. Implements the AI-native collaboration baseline for the shared `xpredict` repo prior to any product build.*
