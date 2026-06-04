/**
 * Plan 09-04 — Shared zod schemas + Server-Action return contract for the
 * order-entry (bet) surface (MKT-03).
 *
 * Lives in a SEPARATE module from `bet-actions.ts` because Next.js forbids
 * non-async (synchronous) exports from a file with the `"use server"`
 * directive — Server Actions can only export async functions, so schemas,
 * constants, and pure helpers must live here (mirrors `auth-schemas.ts`).
 *
 * The client zod schema is PRE-FLIGHT UX ONLY: it stops obvious mistakes
 * (empty / non-positive stake, missing outcome) before the Server Action is
 * invoked. The backend `place_bet` (verified-email + not-banned + balance +
 * tenant stake-limits) is ALWAYS the authority — the form never bypasses a
 * server gate (T-09-12).
 */
import { z } from "zod";

/**
 * Tenant stake limits (mirror of `backend/app/core/config.py`
 * `BET_MIN_STAKE=1` / `BET_MAX_STAKE=100000`). Client-side these bound the
 * pre-flight schema; the backend re-checks and is authoritative. Kept as
 * numbers ONLY for the client min/max comparison — the stake itself stays a
 * string on the wire (SP-1).
 */
export const BET_MIN_STAKE = 1;
export const BET_MAX_STAKE = 100000;

/**
 * Build a pre-flight bet schema bounded on the given [min, max] range (BET-06).
 *
 * `stake` is validated as a positive decimal STRING within `min`/`max` (we keep
 * it a string — money/odds are never parsed to a float for storage, SP-1; the
 * bound check parses only to compare). Callers pass the per-market `min_stake`/
 * `max_stake` when present, else the global `BET_MIN_STAKE`/`BET_MAX_STAKE`
 * defaults. The backend `place_bet` re-checks these bounds and is authoritative —
 * this factory is a UX mirror only (T-12-08).
 */
export function makeBetSchema(min: number, max: number) {
  return z.object({
    outcome: z.enum(["YES", "NO"]),
    stake: z
      .string()
      .min(1, "Enter a stake")
      .refine((v) => /^\d+(\.\d+)?$/.test(v.trim()), {
        message: "Enter a valid amount",
      })
      .refine((v) => Number(v) >= min && Number(v) <= max, {
        message: `Stake must be between ${min} and ${max} PLAY_USD.`,
      }),
  });
}

/**
 * Pre-flight bet schema at the GLOBAL tenant min/max — the default used where no
 * per-market bounds apply. Kept exported so existing importers stay valid; the
 * per-market form builds its resolver via `makeBetSchema(...)` instead.
 */
export const BetSchema = makeBetSchema(BET_MIN_STAKE, BET_MAX_STAKE);

export type BetValues = z.infer<typeof BetSchema>;

/**
 * Shared return-shape contract for Server Actions consumed via
 * `useActionState` — identical to the auth surface (`auth-schemas.ts`) so the
 * form-error rendering idiom (`state.errors._form?.[0]`) is reused verbatim.
 */
export type ActionErrors = Record<string, string[] | undefined> & {
  _form?: string[];
};

export type ActionState =
  | { errors: ActionErrors }
  | { success: true; message: string }
  | undefined;
