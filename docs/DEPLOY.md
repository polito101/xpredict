# Deployment — XPrediction

> Product = **XPrediction**. `xpredict` is the technical repo name. This documents how
> XPrediction is deployed, including a **temporary** Vercel arrangement.

## Frontend (Vercel)

### Decision (2026-05-25) — TEMPORARY co-location in Chiribito's Vercel team

To move fast on previews/deploys while Phase 2 and the multi-operator system stabilize,
XPrediction will **temporarily** live inside the **existing Vercel team used by Chiribito**
(`chiribito293-7173s-projects`) — as its **own separate project**, NOT mixed into Chiribito's
app and NOT reusing the throwaway `xprediction-demo` project.

**This is operational, not branding/architecture. It is explicitly temporary and must be
separated before any real launch.**

**Hard rules while co-located (do NOT break Chiribito):**
- Separate Vercel **project** (e.g. `xprediction`); never edit Chiribito's project or domains.
- **No shared env vars / secrets / assets** with Chiribito — XPrediction keeps its own.
- **No branding mixing** — XPrediction branding only (already in `frontend/`).
- Do not `vercel link` the Chiribito repo to XPrediction or vice-versa.
- Log in with the **Chiribito Vercel identity** before any Vercel action (team isolation rule).
- `.vercel/` (local project link) stays gitignored — never commit it.

### Wiring plan (NOT yet executed — owner runs it)

The repo is a **monorepo**; Vercel deploys only the **frontend**:
1. In the Chiribito Vercel team, **create a new project** (e.g. `xprediction`) linked to GitHub
   repo `polito101/xpredict`.
2. **Root Directory = `frontend/`** (Next.js auto-detected). Build `next build`, default output.
3. Env var `NEXT_PUBLIC_API_URL`: the backend isn't deployed yet and the UI runs on mock data, so
   this can stay a placeholder for now.
4. **Preview deploys** on every branch/PR (automatic once the repo is connected);
   **production** only from `main` (gets the frontend after Phase 1 merges).
5. Verify the first preview renders the dark-premium home and does NOT touch Chiribito.

### Exit plan — what must be separated later

When this stops being temporary:
- Move XPrediction to its **own Vercel team/org**.
- XPrediction's **own domain** + **own env/secrets**.
- Remove the project from Chiribito's team; re-confirm zero coupling (domains, env, analytics, assets).

## Backend

Not deployed yet. Local via `docker compose up`. Staging target (per `.planning/research/STACK.md`):
Railway for v1 — out of scope until a later phase.
