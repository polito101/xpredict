/**
 * LB-B-01 — Live-bets mirror Server Actions (design §5 DOM events, §8 money flow).
 *
 * The `"use client"` widget host (`app/live/live-table.tsx`) fires these from the
 * `<live-bets-table>` DOM events. They are the ONLY authed path that mirrors
 * live-bets money into the XPredict ledger. Mirrors `bet-actions.ts`:
 *
 *   - reads the player's HttpOnly `xpredict_session` cookie via `next/headers`
 *     `cookies()` (the cookie value NEVER enters client JS — T-LBB-01 / T-09-13);
 *   - forwards it as a `Cookie: xpredict_session=...` header to the server-only
 *     `${BACKEND_URL}` (no `NEXT_PUBLIC_` prefix, so the backend origin never
 *     leaks into the client bundle).
 *
 * The LB-A backend (`backend/app/integrations/livebets/router.py`, gated by
 * `current_active_player`) is the AUTHORITY: it re-verifies the bet against
 * live-bets (`GET /v2/bets/{id}`) and the transfers are idempotent. There is NO
 * `user_id` parameter — the player is resolved from the forwarded session, and a
 * foreign `bet_id` maps to 404 (IDOR-safe, design §8 / T-LBB-02). Per design D-3
 * (Approach A) these DOM events are the mirror triggers; `applied:false` is the
 * legitimate idempotent no-op for a duplicate event, NOT an error.
 *
 * `betId` is kept opaque (the backend parses it as a UUID). LB-A status codes map
 * to the discriminated result: 200 ok · 401 unauthenticated · 404 not_found ·
 * 409 conflict · other → error.
 *
 * The `LiveSession` shape is re-used from `./api` (Next forbids non-async value
 * exports from a `"use server"` file, so types are imported, not re-declared here).
 */
"use server";

import { cookies } from "next/headers";

import type { LiveSession } from "./api";

/**
 * Result of `recordLivePlaced` / `recordLiveSettled`. `applied` echoes LB-A
 * `MirrorResult.applied` — `false` is a benign idempotent no-op (design §8).
 *
 * `status` echoes LB-A `MirrorResult.status` — the backend's AUTHORITATIVE
 * settle outcome (WON/LOST/REFUNDED/VOIDED, `schemas.py` `MirrorResult.status`).
 * WR-01: the widget host keys the WON/LOST toast off THIS value, never the
 * untrusted `CustomEvent.detail.status` (a tampered event must not be able to
 * show a celebratory "You won!" for a bet the backend settled as LOST). It is
 * optional because `recordLivePlaced` does not carry a settle status and a
 * malformed 200 body may omit it (then the host falls back to neutral copy).
 */
export type LiveActionResult =
  | { ok: true; applied: boolean; status?: string }
  | { ok: false; reason: "unauthenticated" | "not_found" | "conflict" | "error" };

/**
 * Result of `mintLiveSession` — carries the renewed live-bets session token on
 * success so the widget host can re-set the `session-token` attribute.
 *
 * NIT-1: `expires_at` is intentionally NOT surfaced. The only caller
 * (`onSessionExpired`) re-sets the `session-token` attribute and the widget owns
 * its own expiry tracking, so threading the new expiry through here would be a
 * dead field. The backend's `expires_at` is still validated in the 200 branch
 * (it must be a well-formed session) — it just isn't returned. LB-C can re-add
 * it to the result if a consumer (e.g. session-renewal timing) needs it.
 */
export type LiveSessionResult =
  | { ok: true; session_token: string }
  | { ok: false; reason: "unauthenticated" | "not_found" | "conflict" | "error" };

/**
 * Result of `getLiveBalance` — the current XPredict wallet balance (a STRING on
 * the wire, SP-1) for the in-island refresh after a placed/settled mirror.
 */
export type LiveBalanceResult =
  | { ok: true; balance: string }
  | { ok: false };

/** Server-only backend base (NO `NEXT_PUBLIC_` — mirrors `bet-actions.ts`). */
function getBackendUrl(): string {
  return process.env.BACKEND_URL || "http://localhost:8000";
}

/**
 * Map a non-2xx LB-A status to the discriminated failure reason shared by all
 * three actions: 401 unauthenticated · 404 not_found · 409 conflict · else error.
 */
function reasonForStatus(
  status: number,
): "unauthenticated" | "not_found" | "conflict" | "error" {
  switch (status) {
    case 401:
      return "unauthenticated";
    case 404:
      return "not_found";
    case 409:
      return "conflict";
    default:
      return "error";
  }
}

/**
 * Read the HttpOnly session cookie server-side. Returns `undefined` when absent
 * (the caller short-circuits to `{ok:false, reason:"unauthenticated"}` without
 * calling the backend — mirrors `placeBetAction`).
 */
async function readSession(): Promise<string | undefined> {
  const store = await cookies();
  return store.get("xpredict_session")?.value;
}

/**
 * Mirror a PLACED live-bets bet — debits the player's XPredict wallet into
 * escrow (stake) via LB-A `POST /api/live/bets/{betId}/placed`. The backend
 * re-verifies status PENDING + reads the stake; a tampered event payload can
 * only pass `betId` (T-LBB-04). `applied:false` = already mirrored (no-op).
 */
export async function recordLivePlaced(
  betId: string,
): Promise<LiveActionResult> {
  const session = await readSession();
  if (!session) return { ok: false, reason: "unauthenticated" };

  let res: Response;
  try {
    res = await fetch(
      `${getBackendUrl()}/api/live/bets/${encodeURIComponent(betId)}/placed`,
      {
        method: "POST",
        headers: { Cookie: `xpredict_session=${session}` },
        cache: "no-store",
      },
    );
  } catch {
    return { ok: false, reason: "error" };
  }

  if (res.status === 200) {
    const data = (await res.json().catch(() => null)) as {
      applied?: unknown;
    } | null;
    return { ok: true, applied: data?.applied === true };
  }
  return { ok: false, reason: reasonForStatus(res.status) };
}

/**
 * Mirror a SETTLED live-bets bet (WON/LOST/REFUNDED/VOIDED) into the ledger via
 * LB-A `POST /api/live/bets/{betId}/settled`. The backend re-reads the payout
 * from live-bets (a tampered `payout` in the DOM event is ignored — T-LBB-04)
 * and is idempotent. `applied:false` = already settled (no-op).
 */
export async function recordLiveSettled(
  betId: string,
): Promise<LiveActionResult> {
  const session = await readSession();
  if (!session) return { ok: false, reason: "unauthenticated" };

  let res: Response;
  try {
    res = await fetch(
      `${getBackendUrl()}/api/live/bets/${encodeURIComponent(betId)}/settled`,
      {
        method: "POST",
        headers: { Cookie: `xpredict_session=${session}` },
        cache: "no-store",
      },
    );
  } catch {
    return { ok: false, reason: "error" };
  }

  if (res.status === 200) {
    // WR-01: surface the backend's AUTHORITATIVE settle status so the host keys
    // the WON/LOST toast off it (not the untrusted event detail). `status` is a
    // string on the wire (LB-A `MirrorResult.status`); a malformed body leaves
    // it `undefined` and the host falls back to neutral "settled" copy.
    const data = (await res.json().catch(() => null)) as {
      applied?: unknown;
      status?: unknown;
    } | null;
    return {
      ok: true,
      applied: data?.applied === true,
      status: typeof data?.status === "string" ? data.status : undefined,
    };
  }
  return { ok: false, reason: reasonForStatus(res.status) };
}

/**
 * Re-mint the player's live-bets session via LB-A `POST /api/live/session` (for
 * the `live-bets-session-expired` handler; the `/live` page does the FIRST mint
 * via `fetchLiveSession`). Sends `{ table_id }` only when supplied; otherwise
 * LB-A defaults from `LIVEBETS_DEFAULT_TABLE_ID`. On success returns the new
 * token + expiry so the host can `setAttribute("session-token", ...)`.
 */
export async function mintLiveSession(
  tableId?: string,
): Promise<LiveSessionResult> {
  const session = await readSession();
  if (!session) return { ok: false, reason: "unauthenticated" };

  let res: Response;
  try {
    res = await fetch(`${getBackendUrl()}/api/live/session`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Cookie: `xpredict_session=${session}`,
      },
      body: JSON.stringify(tableId === undefined ? {} : { table_id: tableId }),
      cache: "no-store",
    });
  } catch {
    return { ok: false, reason: "error" };
  }

  if (res.status === 200) {
    const data = (await res.json().catch(() => null)) as Partial<LiveSession> | null;
    // NIT-1: still validate `expires_at` (a well-formed session must carry it),
    // but do not surface it — the caller only needs the renewed token.
    if (
      data &&
      typeof data.session_token === "string" &&
      typeof data.expires_at === "string"
    ) {
      return {
        ok: true,
        session_token: data.session_token,
      };
    }
    return { ok: false, reason: "error" };
  }
  return { ok: false, reason: reasonForStatus(res.status) };
}

/**
 * Read the player's CURRENT XPredict wallet balance via `GET /wallet/me/balance`
 * (the same mechanism `wallet/page.tsx` uses), forwarding the session cookie.
 *
 * Plan-check M-2: the `/live` widget host calls this AFTER a placed/settled
 * mirror and writes the result into its LOCAL `useState` balance, so the unified
 * XPredict balance visibly moves in the client island. `router.refresh()` alone
 * would re-run the Server Component but NOT update the client island's `useState`
 * copy (stale balance), so the in-island refresh reads the balance explicitly.
 * Money is a STRING on the wire (SP-1) — returned verbatim, never parsed.
 */
export async function getLiveBalance(): Promise<LiveBalanceResult> {
  const session = await readSession();
  if (!session) return { ok: false };

  try {
    const res = await fetch(`${getBackendUrl()}/wallet/me/balance`, {
      headers: { Cookie: `xpredict_session=${session}` },
      cache: "no-store",
    });
    if (!res.ok) return { ok: false };
    const data = (await res.json().catch(() => null)) as {
      balance?: unknown;
    } | null;
    if (data && typeof data.balance === "string") {
      return { ok: true, balance: data.balance };
    }
    return { ok: false };
  } catch {
    return { ok: false };
  }
}
