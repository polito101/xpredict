# Deployment — XPrediction

> Product = **XPrediction**. `xpredict` is the technical repo name. This documents how
> XPrediction is deployed, including a **temporary** Vercel arrangement.

## Frontend (Vercel)

### Branch → environment workflow (the continuous model)

| Trigger | Vercel environment | URL |
|---|---|---|
| Push to a **feature/phase branch** (`gsd/*`, `chore/*`, `fix/*`) | **Preview** (per-branch / per-commit) | auto-generated `*.vercel.app` |
| Open / update a **PR** | **Preview** (surfaced on the PR) | auto-generated `*.vercel.app` |
| Merge to **`main`** (PR-only; Pol merges) | **Production** | the project's production domain |

**Hard rule:** feature/phase branches deploy to **Preview only — never Production**. Production is
reached **exclusively** by merging to `main` via PR. Never run `vercel --prod` from a feature branch.
This is Vercel's default once the repo is Git-connected (see Runbook); it is also enforced socially by
the PR-only, Pol-merges-only `main`.

### Decision (2026-05-25) — TEMPORARY co-location in Chiribito's Vercel team

To move fast on previews/deploys while Phase 2 and the multi-operator system stabilize,
XPrediction will **temporarily** live inside the **existing Vercel team used by Chiribito**
(`chiribito293-7173s-projects`) — as its **own separate project**, NOT mixed into Chiribito's
app and NOT reusing the throwaway `xprediction-demo` project.

**This is operational, not branding/architecture. It is explicitly temporary and must be
separated before any real launch.**

**Hard rules while co-located (do NOT break Chiribito):**
- Separate Vercel **project** (named `xpredict`); never edit Chiribito's project or domains.
- **No shared env vars / secrets / assets** with Chiribito — XPrediction keeps its own.
- **No branding mixing** — XPrediction branding only (already in `frontend/`).
- Do not `vercel link` the Chiribito repo to XPrediction or vice-versa.
- Log in with the **Chiribito Vercel identity** before any Vercel action (team isolation rule).
- `.vercel/` (local project link) stays gitignored — never commit it.

### Status (2026-05-26) — ✅ CONNECTED

The Vercel project is **connected** (by Pol): project **`xpredict`** (technical name; brand stays
XPrediction) in team `chiribito293-7173s-projects`, **Root Directory = `frontend/`**, separate
project/config/env — Chiribito untouched.

- **Preview:** branch/PR builds work (they contain `frontend/`).
- **Production:** builds from `main`. Currently **● Error, which is expected** — `main` does not
  contain `frontend/` yet (only `.planning/.claude/docs/.mcp.json`), so the Root Directory is missing
  there. **The moment PR #4 merges `frontend/` into `main`, Production goes green automatically — no
  Vercel change required.** Prod URL: `https://xpredict-chiribito293-7173s-projects.vercel.app`.

### Runbook — how it was connected (reference; do NOT re-run unnecessarily)

The repo is a **monorepo**; Vercel deploys only the **`frontend/`** subdir. The logged-in Vercel
identity must be the Chiribito team (`chiribito293-7173`) — the team that temporarily hosts this.

**Recommended path — Dashboard (this is what gives automatic Preview deploys on every push):**
1. Vercel → Chiribito team → **Add New… → Project** → import GitHub repo `polito101/xpredict`
   (if the repo isn't listed, authorize the Vercel GitHub app for it first).
2. **Project name:** `xpredict` (matches the repo; brand stays XPrediction). **Root Directory:** `frontend`. Framework: Next.js (auto-detected).
   Build `next build`, default output. **Do NOT** point it at the repo root or at `xprediction-demo`.
3. **Env vars:** add only XPrediction's own — none required yet (`NEXT_PUBLIC_API_URL` can stay
   unset/placeholder while the UI runs on mock data). **Never** import Chiribito's env or secrets.
4. Deploy. Vercel then auto-builds per the table above: **every branch/PR → Preview**,
   **`main` → Production** (Production gets the frontend once the Phase 1 PR merges).
5. Verify the first Preview renders the dark-premium home **and that Chiribito's projects are untouched**.

**Alternative — CLI (manual one-off preview; does NOT by itself set up auto-previews):**
From `frontend/`: `vercel link` (scope = Chiribito team, project = `xpredict`, root = current dir),
then `vercel deploy` for a Preview (`vercel deploy --prod` **only** ever from `main`). To get push →
auto-deploy, run `vercel git connect` (links the GitHub repo — same effect as the dashboard import).
`.vercel/` is gitignored — never commit it.

### Exit plan — what must be separated later

When this stops being temporary:
- Move XPrediction to its **own Vercel team/org**.
- XPrediction's **own domain** + **own env/secrets**.
- Remove the project from Chiribito's team; re-confirm zero coupling (domains, env, analytics, assets).

## Backend

Not deployed yet. Local via `docker compose up`. Staging target (per `.planning/research/STACK.md`):
Railway for v1 — out of scope until a later phase.
