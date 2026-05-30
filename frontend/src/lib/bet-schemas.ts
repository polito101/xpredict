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
 * Pre-flight bet schema. `stake` is validated as a positive decimal STRING
 * within the tenant min/max (we keep it a string — money/odds are never
 * parsed to a float for storage, SP-1; the bound check parses only to compare).
 */
export const BetSchema = z.object({
  outcome: z.enum(["YES", "NO"]),
  stake: z
    .string()
    .min(1, "Enter a stake")
    .refine((v) => /^\d+(\.\d+)?$/.test(v.trim()), {
      message: "Enter a valid amount",
    })
    .refine((v) => Number(v) >= BET_MIN_STAKE && Number(v) <= BET_MAX_STAKE, {
      message: `Stake must be between ${BET_MIN_STAKE} and ${BET_MAX_STAKE} PLAY_USD.`,
    }),
});

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
