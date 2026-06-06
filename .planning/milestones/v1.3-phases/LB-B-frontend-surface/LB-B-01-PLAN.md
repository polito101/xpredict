---
phase: LB-B-frontend-surface
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - frontend/src/lib/api.ts
  - frontend/src/lib/live-actions.ts
  - frontend/src/components/player-nav.tsx
  - frontend/.env.example
autonomous: true
requirements: [SC2, SC4, D-1, D-3]
must_haves:
  truths:
    - "A 'Live' entry appears in player-nav and links to /live"
    - "Typed helpers fetchLiveSession / fetchLiveTables exist and read the player's HttpOnly session cookie server-side"
    - "Server Actions recordLivePlaced(betId) / recordLiveSettled(betId) POST to the LB-A placed/settled routes with the cookie forwarded"
    - "NEXT_PUBLIC_LIVEBETS_WIDGET_SRC is documented in frontend/.env.example"
  artifacts:
    - path: "frontend/src/lib/live-actions.ts"
      provides: "Server Actions: fetchLiveSession, fetchLiveTables, recordLivePlaced, recordLiveSettled (cookie-forwarded)"
      contains: "use server"
    - path: "frontend/src/components/player-nav.tsx"
      provides: "Live nav entry"
      contains: "/live"
    - path: "frontend/.env.example"
      provides: "NEXT_PUBLIC_LIVEBETS_WIDGET_SRC documentation"
      contains: "NEXT_PUBLIC_LIVEBETS_WIDGET_SRC"
  key_links:
    - from: "frontend/src/lib/live-actions.ts"
      to: "backend POST /api/live/session"
      via: "fetch with Cookie: xpredict_session header"
      pattern: "api/live/session"
    - from: "frontend/src/lib/live-actions.ts"
      to: "backend POST /api/live/bets/{id}/placed and /settled"
      via: "fetch with Cookie: xpredict_session header"
      pattern: "api/live/bets"
---

<objective>
Lay the LB-B foundation: the typed, cookie-forwarding backend helpers for the LB-A `/api/live/*`
surface, the "Live" nav entry, and the new public widget-src env var. No `/live` page yet — this plan
delivers ONLY the pieces the page and the client widget will consume in waves 2 and 3, so they receive
their contracts (helper signatures + types) instead of discovering them.

Purpose: Establish the interface seam (helper signatures, types, nav link, env var) before the page and
client component are built against them.
Output: `live-actions.ts` (4 Server Actions), live types in `api.ts`, the nav entry, `.env.example`.

LB-A is DONE. This plan calls the existing routes; it does NOT touch `backend/`.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/LB-B-frontend-surface/CONTEXT.md
@docs/superpowers/specs/2026-06-05-live-bets-integration-design.md

# The exact patterns to mirror (read the real shape, copy it — do NOT invent):
# Canonical authed-mutation Server Action (cookie read + forward + status mapping):
@frontend/src/lib/bet-actions.ts
# Server Action cookie-forward + the getBackendUrl() server-only base:
@frontend/src/lib/auth.ts
# Typed fetch helpers + apiBase() (server vs NEXT_PUBLIC_ client) + the strings-on-the-wire convention:
@frontend/src/lib/api.ts
# The nav link list to extend:
@frontend/src/components/player-nav.tsx
# The backend contract these helpers call (response shapes: SessionResponse, TablesResponse, MirrorResult):
@backend/app/integrations/livebets/router.py
@backend/app/integrations/livebets/schemas.py
</context>

<constraints>
- PLANNING is done; this is the EXECUTE plan. The executor's ONLY writes are the four files in
  `files_modified`. Do NOT create or modify any other `frontend/` file or anything under `backend/`.
- pnpm: standalone `pnpm@9.15.0` ONLY (`pnpm --version` must be 9.15.x). NEVER `corepack pnpm`
  (resolves to a destructive 11.x that wipes node_modules and rewrites the lockfile — see CLAUDE.md).
  If pnpm is not 9.15.x, STOP and report. `frontend/node_modules` may be absent — run
  `pnpm install --frozen-lockfile` (standalone) before typecheck/lint.
- Additive only: extend the nav DESTINATIONS array and add new exports; change no existing helper.
- Money/odds stay STRINGS on the wire (SP-1) — never parse to a JS number.
- English copy; English identifiers/paths.
</constraints>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: Add the live API types + the read helpers (session, tables) to api.ts</name>
  <files>frontend/src/lib/api.ts</files>
  <behavior>
    Types and read helpers that mirror the existing `MarketDetail` / `fetchMarket` shape and the LB-A
    response models in `backend/app/integrations/livebets/schemas.py`:
    - `LiveSession { session_token: string; expires_at: string }` (matches `SessionResponse`).
    - `LiveTable { table_id: string; name: string | null }` (matches `TableItem`).
    - `LiveMirrorResult { bet_id: string; status: string; applied: boolean }` (matches `MirrorResult`).
    - `fetchLiveSession(session, tableId?)` → `POST {base}/api/live/session`, body `{ table_id }` (omit
      when undefined; LB-A defaults from `LIVEBETS_DEFAULT_TABLE_ID`). Returns `LiveSession`.
    - `fetchLiveTables(session)` → `GET {base}/api/live/tables`. Returns `LiveTable[]` (read `.tables`).
    - A typed `LiveTableUnconfigured` error (mirror `MarketNotFound`) thrown when `fetchLiveSession`
      gets the LB-A 400 ("No table_id supplied and LIVEBETS_DEFAULT_TABLE_ID is not configured.") so the
      page can branch to the friendly empty state instead of a generic error (CONTEXT Scope-IN bullet 1).
  </behavior>
  <action>
    In `api.ts`, add the three interfaces and the two read helpers above. These run SERVER-SIDE (called
    from the `/live` Server Component), so take the player's session-cookie value as the first argument
    and forward it as a `Cookie: xpredict_session=${session}` header — EXACTLY like
    `portfolio/page.tsx` and `bet-actions.ts` do; do NOT rely on `credentials:"include"` (the cookie is
    HttpOnly and the backend is a different origin). Use `apiBase()` for the base URL and
    `cache:"no-store"` (mirror `fetchMarket`). On a 400 from `fetchLiveSession`, throw
    `LiveTableUnconfigured`; on any other non-ok, throw `Error` with the status (mirror the existing
    helpers). Keep money/identifiers as strings. Add a JSDoc block on each, matching the file's house
    style and citing the LB-A route. Do NOT add the placed/settled mutations here — those are Server
    Actions in Task 2 (a `"use server"` file cannot live in `api.ts`).
  </action>
  <verify>
    <automated>cd frontend && pnpm exec tsc --noEmit</automated>
  </verify>
  <done>
    `api.ts` exports `LiveSession`, `LiveTable`, `LiveMirrorResult`, `LiveTableUnconfigured`,
    `fetchLiveSession`, `fetchLiveTables`; both helpers forward the cookie header and use `apiBase()` +
    `no-store`; typecheck is clean.
  </done>
</task>

<task type="auto" tdd="false">
  <name>Task 2: Add the placed/settled mirror Server Actions (live-actions.ts)</name>
  <files>frontend/src/lib/live-actions.ts</files>
  <behavior>
    A new `"use server"` module (mirror `bet-actions.ts`) exposing the two authed mutations the client
    widget fires, plus a session re-mint action:
    - `recordLivePlaced(betId: string): Promise<LiveActionResult>` → `POST {BACKEND_URL}/api/live/bets/{betId}/placed`.
    - `recordLiveSettled(betId: string): Promise<LiveActionResult>` → `POST {BACKEND_URL}/api/live/bets/{betId}/settled`.
    - `mintLiveSession(tableId?: string): Promise<LiveSessionResult>` → `POST {BACKEND_URL}/api/live/session`
      (for the `live-bets-session-expired` re-mint; the page does the FIRST mint via `fetchLiveSession`).
    Result shape is a discriminated union (mirror the project's `{status:"ok"|...}` style):
    `{ ok: true; applied: boolean }` / `{ ok: true; session_token; expires_at }` for the mint, and
    `{ ok: false; reason: "unauthenticated" | "not_found" | "conflict" | "error" }` otherwise — mapped
    from LB-A status codes: 200 ok; 401 unauthenticated; 404 not_found; 409 conflict; other → error.
  </behavior>
  <action>
    Create `frontend/src/lib/live-actions.ts` starting with `"use server"`. Read the HttpOnly cookie via
    `next/headers` `cookies()` and forward `Cookie: xpredict_session=${session}` to `${BACKEND_URL}`
    using a local `getBackendUrl()` (server-only, NO `NEXT_PUBLIC_` — mirror `bet-actions.ts:41-43`); the
    cookie value must never enter client JS (T-09-13). When the cookie is absent return
    `{ok:false, reason:"unauthenticated"}` without calling the backend (mirror `placeBetAction`). Wrap
    each `fetch` in try/catch → `{ok:false, reason:"error"}`. Map the LB-A status codes per the behavior
    block (the route maps ownership→404, verification→409, missing wallet→404; see `router.py`). Import
    the `LiveSession` type from `./api` for the mint result. Per design D-3 (Approach A) these are the
    mirror triggers; the backend is authoritative and idempotent — `applied:false` is the legitimate
    no-op for a duplicate event, NOT an error. Keep `betId` opaque (the backend parses it as a UUID).
    Add a top-of-file JSDoc block in the house style citing design §5 (DOM events) and §8 (money flow).
  </action>
  <verify>
    <automated>cd frontend && pnpm exec tsc --noEmit</automated>
  </verify>
  <done>
    `live-actions.ts` begins with `"use server"`, exports `recordLivePlaced`, `recordLiveSettled`,
    `mintLiveSession`; each forwards the session cookie server-side and maps 200/401/404/409/other to the
    discriminated result; typecheck clean.
  </done>
</task>

<task type="auto" tdd="false">
  <name>Task 3: Add the "Live" nav entry and document the widget-src env var</name>
  <files>frontend/src/components/player-nav.tsx, frontend/.env.example</files>
  <behavior>
    - `player-nav.tsx`: a new `{ href: "/live", label: "Live" }` entry in `DESTINATIONS`, placed after
      Markets (CONTEXT Scope-IN bullet 4 / SC2). The existing `isActive` logic already handles
      `/live` (prefix match), so no other change is needed.
    - `frontend/.env.example`: a NEW file (none exists in the repo today) documenting the one new PUBLIC
      var this phase introduces, `NEXT_PUBLIC_LIVEBETS_WIDGET_SRC`, with the LB-C dev value as a comment
      example (`http://localhost:8080/static/widget.js`) and a one-line note that it is the live-bets
      widget script URL loaded by `next/script` on `/live`.
  </behavior>
  <action>
    Add the `/live` entry to the `DESTINATIONS` array in `player-nav.tsx` (after `{ href: "/", label:
    "Markets" }`). Do NOT touch the auth block or `isActive`. Create `frontend/.env.example` (the
    `NEXT_PUBLIC_` prefix is mandatory so the value is readable in the browser bundle by the client
    widget loader). Because `.env.example` is the only doc surface for env here, also list the existing
    public var the live page reuses (`NEXT_PUBLIC_API_URL`) for completeness, with the server-only
    `BACKEND_URL` noted as server-side. Do NOT add real secrets — example/placeholder values only.
  </action>
  <verify>
    <automated>cd frontend && pnpm exec eslint src/components/player-nav.tsx && grep -v '^#' .env.example | grep -c NEXT_PUBLIC_LIVEBETS_WIDGET_SRC</automated>
  </verify>
  <done>
    `player-nav.tsx` renders a "Live" link to `/live` after Markets; `frontend/.env.example` exists and
    contains `NEXT_PUBLIC_LIVEBETS_WIDGET_SRC`; lint clean.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| browser → Next server (Server Action) | Client widget fires DOM events; the Server Action is the only authed path. The HttpOnly session cookie is read server-side and never reaches client JS. |
| Next server → XPredict backend `/api/live/*` | Cookie-forwarded server-side fetch; the backend (`current_active_player`) is the authority. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-LBB-01 | Information disclosure | session cookie | mitigate | Cookie read via `next/headers` and forwarded as a `Cookie:` header ONLY (server-side); never returned to the client, mirroring `bet-actions.ts` (T-09-13). No `NEXT_PUBLIC_` for `BACKEND_URL`. |
| T-LBB-02 | Elevation of privilege | placed/settled mutations | mitigate | No `user_id` parameter; the backend resolves the player from the forwarded session and is authoritative + idempotent (design §8). A foreign `bet_id` maps to 404 (IDOR-safe, LB-A BL-01). |
| T-LBB-03 | Spoofing | betId from a client DOM event | accept | `bet_id` originates client-side, but LB-A re-verifies it against live-bets (`GET /v2/bets/{id}`) before any ledger move; a demo does not need cross-DB two-phase guarantees (design §8 caveat). |
</threat_model>

<verification>
- `cd frontend && pnpm exec tsc --noEmit` — clean.
- `cd frontend && pnpm exec eslint src` — clean.
- `grep -v '^#' frontend/.env.example | grep -c NEXT_PUBLIC_LIVEBETS_WIDGET_SRC` ≥ 1.
- No diff under `backend/`; no `frontend/` file changed outside `files_modified`.
</verification>

<success_criteria>
- Helpers `fetchLiveSession` / `fetchLiveTables` (in `api.ts`) and Server Actions `recordLivePlaced` /
  `recordLiveSettled` / `mintLiveSession` (in `live-actions.ts`) exist, are typed, and forward the
  session cookie server-side (SC4, D-1).
- The "Live" nav entry renders and routes to `/live` (SC2).
- `NEXT_PUBLIC_LIVEBETS_WIDGET_SRC` is documented in `frontend/.env.example`.
- Typecheck + lint clean; `backend/` untouched.
</success_criteria>

<output>
Create `.planning/phases/LB-B-frontend-surface/LB-B-01-SUMMARY.md` when done.
</output>
