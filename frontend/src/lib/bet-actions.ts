/**
 * Plan 09-04 — Bet placement Server Action (MKT-03).
 *
 * `placeBetAction` is the ONLY path the order-entry form uses to place a bet.
 * It mirrors `auth.ts` `loginAction` (the canonical Server-Action shape) and
 * the `portfolio/page.tsx` cookie-forward read:
 *
 *   - reads the player's HttpOnly `xpredict_session` cookie via `next/headers`
 *     `cookies()` (the cookie NEVER enters client JS — T-09-13);
 *   - POSTs `{market_id, outcome_id, stake}` to `${BACKEND_URL}/bets` with a
 *     forwarded `Cookie: xpredict_session=...` header. `BACKEND_URL` is
 *     server-only (no `NEXT_PUBLIC_` prefix) so the backend origin never leaks
 *     into the client bundle.
 *
 * The backend (`backend/app/bets/router.py::place_bet`, gated by
 * `current_betting_player`) is the AUTHORITY — verified-email, not-banned,
 * balance and tenant stake-limit checks all live server-side. This action
 * cannot place a bet for another user: there is no `user_id` parameter; the
 * backend resolves the player from the session (T-09-12). Each backend status
 * maps to a SPECIFIC inline message (no generic toast — CONTEXT Area 4):
 *
 *   201 → success            402 → insufficient balance
 *   409 → market closed       403 → verify-email (default) / banned
 *   422 → stake limits        401 → "Log in to place a bet" affordance
 *   other non-2xx → generic fallback
 *
 * Schemas + types live in `./bet-schemas` (Next forbids non-async exports from
 * a `"use server"` file).
 */
"use server";

import { cookies } from "next/headers";
import { revalidatePath } from "next/cache";

import type { ActionState, SellState } from "./bet-schemas";
import {
  BET_MAX_STAKE,
  BET_MIN_STAKE,
  BetSchema,
} from "./bet-schemas";

function getBackendUrl(): string {
  return process.env.BACKEND_URL || "http://localhost:8000";
}

// Exact UI-SPEC Copywriting Contract strings (inline, never a toast).
const COPY = {
  insufficientBalance:
    "Not enough play balance. Lower your stake or check your wallet.",
  marketClosed: "This market is closed and no longer accepting bets.",
  unverified: "Verify your email to place bets.",
  banned:
    "Your account can't place bets right now. Contact support if you think this is a mistake.",
  stakeLimits: `Stake must be between ${BET_MIN_STAKE} and ${BET_MAX_STAKE} PLAY_USD.`,
  loginRequired: "Log in to place a bet",
  generic: "Your bet couldn't be placed. Try again.",
} as const;

/** Best-effort read of the FastAPI `{ "detail": "..." }` error body. */
async function readDetail(res: Response): Promise<string> {
  try {
    const data = (await res.json()) as { detail?: unknown };
    return typeof data.detail === "string" ? data.detail : "";
  } catch {
    return "";
  }
}

/**
 * Place a bet for the authenticated player. `formData` carries the UUID
 * `market_id` + `outcome_id` (supplied by the SSR `MarketDetail.outcomes[].id`)
 * and the `stake` + `outcome` token (YES/NO) for the success message.
 */
export async function placeBetAction(
  _prev: ActionState,
  formData: FormData,
): Promise<ActionState> {
  // Pre-flight: stake + outcome token (UX only; backend re-validates).
  const parsed = BetSchema.safeParse({
    outcome: formData.get("outcome"),
    stake: formData.get("stake"),
  });
  if (!parsed.success) {
    return { errors: parsed.error.flatten().fieldErrors };
  }

  const marketId = formData.get("market_id");
  const outcomeId = formData.get("outcome_id");
  if (typeof marketId !== "string" || typeof outcomeId !== "string") {
    return { errors: { _form: [COPY.generic] } };
  }

  const store = await cookies();
  const session = store.get("xpredict_session")?.value;
  if (!session) {
    // No session at all — surface the login affordance (mirrors a 401).
    return { errors: { _form: [COPY.loginRequired] } };
  }

  let res: Response;
  try {
    res = await fetch(`${getBackendUrl()}/bets`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Cookie: `xpredict_session=${session}`,
      },
      // PlaceBetRequest is extra="forbid": exactly these three keys.
      body: JSON.stringify({
        market_id: marketId,
        outcome_id: outcomeId,
        stake: parsed.data.stake,
      }),
      cache: "no-store",
    });
  } catch {
    return { errors: { _form: [COPY.generic] } };
  }

  if (res.status === 201) {
    return {
      success: true,
      message: `Bet placed — ${parsed.data.stake} PLAY_USD on ${parsed.data.outcome}.`,
    };
  }

  switch (res.status) {
    case 402:
      return { errors: { _form: [COPY.insufficientBalance] } };
    case 409:
      return { errors: { _form: [COPY.marketClosed] } };
    case 403: {
      // Disambiguate banned vs unverified on the backend detail text. The
      // banned gate (current_betting_player) sends "Account is banned from
      // placing bets."; fastapi-users' unverified gate sends a different detail.
      // Match the full "is banned" sentinel — NOT a bare "ban" substring (WR-07),
      // which would mis-map any future 403 detail containing the letters "ban"
      // (e.g. "bandwidth", "abandoned request") to the banned copy. Default to
      // the unverified copy when the detail is not the banned sentinel.
      const detail = (await readDetail(res)).toLowerCase();
      if (detail.includes("is banned")) {
        return { errors: { _form: [COPY.banned] } };
      }
      return { errors: { _form: [COPY.unverified] } };
    }
    case 422:
      return { errors: { _form: [COPY.stakeLimits] } };
    case 401:
      return { errors: { _form: [COPY.loginRequired] } };
    default:
      return { errors: { _form: [COPY.generic] } };
  }
}

const SELL_COPY = {
  notClosable: "Esta posición ya no se puede cerrar (mercado cerrado o ya liquidada).",
  notFound: "No encontramos esa posición.",
  loginRequired: "Inicia sesión para cerrar la posición.",
  generic: "No se pudo cerrar la posición. Inténtalo de nuevo.",
} as const;

/**
 * Close (cash out) one of the player's open positions at the current price. The backend
 * (`POST /bets/{id}/sell`) is the authority; this forwards the HttpOnly session cookie and
 * maps each status to an inline message. On success it revalidates `/portfolio` so the RSC
 * re-fetches the updated positions + balance.
 */
export async function sellPositionAction(
  _prev: SellState,
  formData: FormData,
): Promise<SellState> {
  const betId = formData.get("bet_id");
  if (typeof betId !== "string" || betId.length === 0) {
    return { error: SELL_COPY.generic };
  }

  const store = await cookies();
  const session = store.get("xpredict_session")?.value;
  if (!session) return { error: SELL_COPY.loginRequired };

  let res: Response;
  try {
    res = await fetch(`${getBackendUrl()}/bets/${betId}/sell`, {
      method: "POST",
      headers: { Cookie: `xpredict_session=${session}` },
      cache: "no-store",
    });
  } catch {
    return { error: SELL_COPY.generic };
  }

  if (res.ok) {
    const body = (await res.json().catch(() => ({}))) as { payout?: string };
    revalidatePath("/portfolio");
    return {
      success: true,
      message: body.payout
        ? `Posición cerrada — cobras ${body.payout} PLAY_USD.`
        : "Posición cerrada.",
    };
  }

  switch (res.status) {
    case 409:
      return { error: SELL_COPY.notClosable };
    case 404:
      return { error: SELL_COPY.notFound };
    case 401:
      return { error: SELL_COPY.loginRequired };
    default:
      return { error: SELL_COPY.generic };
  }
}
