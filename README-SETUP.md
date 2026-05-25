# XPredict — Onboarding & Workflow Guide

White-label prediction market platform. PM: Pol Bonet. Devs/agents: Cuco (+ others).

> **`xpredict` vs `xprediction-demo`:** `xpredict` (this repo) is the real, production-grade project, built phase by phase via GSD. `xprediction-demo` is a **separate** presentational Next.js UI demo (mock data, no backend) and is **not integrated here yet** — any future reuse of its UI will be a deliberate, controlled migration. Don't mix them.

## Prerequisites

Always needed:
- **Node** 20+ and **Git**
- **Claude Code** (this workflow runs inside it)

Needed only once product **Phase 1** starts scaffolding code (NOT required to clone, plan, or read docs):
- **Python 3.12** + **uv** or **poetry** (backend)
- **Docker** + Docker Compose (local Postgres / Redis / stack)

## Per-machine setup (once after cloning)

1. **Clone and open in Claude Code:**
   ```powershell
   git clone https://github.com/polito101/xpredict.git
   cd xpredict
   claude
   ```

2. **Set your GitHub token for the MCP.** The repo ships a versioned `.mcp.json` pinning the official GitHub MCP. It authenticates via a **Personal Access Token** read from the `GITHUB_PERSONAL_ACCESS_TOKEN` environment variable — GitHub's OAuth flow is **not usable here** (its auth server doesn't support MCP dynamic client registration, RFC 7591). One time:
   - Create a PAT at https://github.com/settings/tokens — classic with `repo` scope, or fine-grained with `contents:write` + `pull_requests:write`.
   - Set it as a **user environment variable** (persists for new terminals): `setx GITHUB_PERSONAL_ACCESS_TOKEN "ghp_your_token"` (then open a new terminal) — **or** add it under `"env"` in `~/.claude/settings.local.json`. It does **not** go in the repo's `.env.local`.

   The committed `.mcp.json` only references the variable, so **no token is ever stored in the repo**. When Claude Code prompts to enable the `github` server, approve it; verify with `/mcp` (shows `github` connected and the `create_pull_request` tool). Note: `claude mcp get github` from a plain terminal may report "Failed to connect" because that CLI health-check does not expand env vars — the in-session MCP client does.

3. **(Optional) Linear.** Issue tracking is optional and tolerant — you can work fully without it. To enable it, create `.env.local` with just your personal key:
   ```powershell
   "LINEAR_API_KEY=lin_api_xxx" | Set-Content .env.local -Encoding UTF8
   ```
   The shared, non-secret team/state IDs are already committed in `.claude/linear.shared.env` — you do NOT add those. If `LINEAR_API_KEY` is absent, the Linear hooks skip cleanly (no errors, no noise).

That's it. `.claude/settings.json` (hooks) and `CLAUDE.md` load automatically when you open the repo in Claude Code.

## Commands

GSD commands are **hyphenated** (not `/gsd:...`):

- Full solo flow (recommended): **`/gsd-autonomous`**
- Step-by-step: `/gsd-discuss-phase` → `/gsd-plan-phase` → `/gsd-execute-phase` → `/gsd-verify-work` → `/gsd-code-review` → `/gsd-ship`
- Helpers: `/gsd-spike` (deep research), `/gsd-ultraplan-phase` (complex phases), `/gsd-quick` (small subtasks)

## Working a phase

1. Pick your assigned phase from `.planning/ROADMAP.md`.
2. Run `/gsd-autonomous` (or the step-by-step commands). GSD creates an isolated **per-phase branch** (`gsd/phase-XX-slug`) — you never work directly on `main`.
3. The flow generates `.planning/phases/XX/PLAN.md` and `.planning/phases/XX/VERIFICATION.md`.

When `PLAN.md` is first written, a Linear issue is created automatically (if Linear is configured).

## Opening the PR

Open the PR **through the GitHub MCP** (e.g. ask Claude in-session: *"abre el PR de esta fase con create_pull_request"*), NOT with `gh`. The MCP path is what triggers the automation:

- A pre-check **blocks** PR creation unless the active phase has both `PLAN.md` and `VERIFICATION.md` (`check-phase-ready` hook).
- After the PR opens, the phase's Linear issue moves to **In Review** automatically (if configured).
- Slack `#general` gets the PR/merge notification via the native GitHub↔Slack integration.

For the PR body, ask Claude to compare plan vs. shipped:
> "compara `.planning/phases/0X/PLAN.md` con lo implementado y dame el body del PR — tasks completadas, qué quedó fuera, observaciones"

Rules:
- **1 PR per phase.** Only the PM (Pol) approves/merges.
- A PR without a matching `PLAN.md` is blocked automatically.
- `gh pr create` is **not** the supported path — it bypasses the hooks above (the gate + Linear move won't fire).

## Autonomy & guardrails (`mode: "yolo"`)

GSD runs in high-autonomy `mode: "yolo"`, deliberately bounded so the shared repo stays clean:
- It operates **inside the current phase branch** only — **never** directly on `main`.
- Gates stay **mandatory**: `plan_check`, `verifier`, and `code_review` are ON; a PR is required per phase; `auto_advance` is `false` (phase transitions are explicit).

Phase branches + mandatory PR + verifier/code_review + `auto_advance: false` = high autonomy without chaos.

## PM: one-time project setup (reference / future white-label spinoffs)

1. Copy the collaborative-gsd-template to the repo root; replace `[NAME]` placeholders in `CLAUDE.md`.
2. Linear: set up the native GitHub↔Linear integration; put the team + workflow-state IDs in `.claude/linear.shared.env` (use `.claude/hooks/linear-get-states.ps1` to discover state IDs for a new team).
3. Slack: native GitHub↔Slack integration for `#general`.
4. Create `.planning/ROADMAP.md` via `/gsd-new-project` (done — 11 phases).
