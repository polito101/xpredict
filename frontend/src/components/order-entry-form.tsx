/**
 * Plan 09-04 — Order-entry form (MKT-03).
 *
 * Mirrors `login-form.tsx`: react-hook-form `useForm` + `zodResolver(BetSchema)`
 * for pre-flight UX validation, paired with React 19 `useActionState` driving
 * the `placeBetAction` Server Action (the authoritative, cookie-forwarded
 * `POST /bets`).
 *
 * Flow (UI-SPEC §Order-entry form):
 *   1. Player picks an outcome (YES/NO Select) + enters a stake.
 *   2. Submit runs client zod; on success it OPENS the BetConfirmDialog — it
 *      does NOT POST directly.
 *   3. Only the dialog's "Confirm bet" fires `placeBetAction`.
 *   4. Each backend status maps to a SPECIFIC inline message in a
 *      `role="alert"` region (NO toast — CONTEXT Area 4). Success renders an
 *      inline confirmation.
 *
 * Disabled/auth states:
 *   - market CLOSED  → the form is disabled with the closed-market copy.
 *   - unauthenticated → a "Log in to place a bet" link to /login (not a dead
 *     form). `isAuthenticated` is derived by the page from the session cookie.
 *
 * Money/odds are strings on the wire; the expected-payout preview rounds for
 * display only (SP-1) and never feeds storage math.
 */
"use client";

import { useActionState, startTransition, useMemo, useState } from "react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { placeBetAction } from "@/lib/bet-actions";
import {
  makeBetSchema,
  BET_MAX_STAKE,
  BET_MIN_STAKE,
  type BetValues,
  type ActionState,
} from "@/lib/bet-schemas";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { BetConfirmDialog } from "@/components/bet-confirm-dialog";
import { BetPlacedSuccess } from "@/components/bet-placed-success";

const CURRENCY = "PLAY_USD";

export interface OrderEntryOutcome {
  id: string;
  label: string; // "YES" | "NO"
  current_odds: string; // probability in (0,1] as a string (SP-1)
}

interface OrderEntryFormProps {
  marketId: string;
  outcomes: OrderEntryOutcome[];
  marketStatus: string;
  isAuthenticated: boolean;
  /**
   * Per-market stake bounds (BET-06). Money STRINGS on the wire (SP-1) — parsed
   * only to compare. When absent (or null), the global BET_MIN/MAX_STAKE defaults
   * apply. The server (`place_bet`) is authoritative; these are a UX mirror.
   */
  minStake?: string | null;
  maxStake?: string | null;
}

/** Round a probability string (0..1) to a whole percent for display (SP-1). */
function toPct(odds: string | undefined): number {
  if (!odds) return 0;
  const n = parseFloat(odds);
  return Number.isNaN(n) ? 0 : Math.round(n * 100);
}

/**
 * Expected payout = stake / current_odds_of_chosen (RESEARCH Pattern 7).
 * Display-only string math: returns a 2-dp string, or "—" when not computable.
 *
 * Gated on the SAME effective min/max the zod schema enforces (WR-08) so the
 * preview and the submit gate agree — a sub-min (or over-max) stake shows "—"
 * rather than a plausible payout for a bet the form will then reject. The bounds
 * prefer the per-market values, falling back to the globals. Display-only: this
 * never feeds storage math (SP-1).
 */
function expectedPayout(
  stake: string,
  odds: string | undefined,
  minNum: number,
  maxNum: number,
): string {
  const s = parseFloat(stake);
  const p = odds ? parseFloat(odds) : NaN;
  if (Number.isNaN(s) || Number.isNaN(p) || p <= 0 || s < minNum || s > maxNum)
    return "—";
  return (s / p).toFixed(2);
}

export function OrderEntryForm({
  marketId,
  outcomes,
  marketStatus,
  isAuthenticated,
  minStake,
  maxStake,
}: OrderEntryFormProps) {
  const [state, formAction, pending] = useActionState<ActionState, FormData>(
    placeBetAction,
    undefined,
  );
  const [confirmOpen, setConfirmOpen] = useState(false);

  // Effective numeric bounds (BET-06): prefer the per-market value, fall back to
  // the global default. Parsed ONLY for the bound comparison — the stake stays a
  // string on the wire (SP-1). The server re-checks and is authoritative.
  const minNum = minStake != null ? Number(minStake) : BET_MIN_STAKE;
  const maxNum = maxStake != null ? Number(maxStake) : BET_MAX_STAKE;

  const betSchema = useMemo(() => makeBetSchema(minNum, maxNum), [minNum, maxNum]);

  const form = useForm<BetValues>({
    resolver: zodResolver(betSchema),
    defaultValues: { outcome: "YES", stake: "" },
    mode: "onSubmit",
  });

  const yesOutcome = useMemo(
    () => outcomes.find((o) => o.label === "YES"),
    [outcomes],
  );
  const noOutcome = useMemo(
    () => outcomes.find((o) => o.label === "NO"),
    [outcomes],
  );

  const selectedOutcome = form.watch("outcome");
  const stake = form.watch("stake");
  const chosen = selectedOutcome === "YES" ? yesOutcome : noOutcome;

  const yesPct = toPct(yesOutcome?.current_odds);
  const noPct = toPct(noOutcome?.current_odds);
  const payout = expectedPayout(stake ?? "", chosen?.current_odds, minNum, maxNum);

  // Form-level error from the Server Action (the mapped inline bet error).
  const formError =
    state && "errors" in state ? state.errors._form?.[0] : undefined;
  const success = state && "success" in state ? state.message : undefined;

  const isClosed = marketStatus === "CLOSED";

  // Submit only OPENS the confirm dialog (after client zod). The POST happens
  // on the dialog's "Confirm bet".
  const onSubmit = form.handleSubmit(() => {
    setConfirmOpen(true);
  });

  // Fire the Server Action from the dialog's confirm button.
  const onConfirm = () => {
    const values = form.getValues();
    const fd = new FormData();
    fd.append("market_id", marketId);
    fd.append("outcome_id", chosen?.id ?? "");
    fd.append("outcome", values.outcome);
    fd.append("stake", values.stake);
    setConfirmOpen(false);
    startTransition(() => formAction(fd));
  };

  // Unauthenticated: a real affordance, never a dead form.
  if (!isAuthenticated) {
    return (
      <div className="flex flex-col gap-3" data-testid="order-entry-login">
        <p className="text-sm text-zinc-500">
          You need an account to place a bet on this market.
        </p>
        <Button asChild size="lg">
          <Link href="/login">Log in to place a bet</Link>
        </Button>
      </div>
    );
  }

  return (
    <>
      <Form {...form}>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void onSubmit(e);
          }}
          className="space-y-4"
          noValidate
        >
          <FormField
            control={form.control}
            name="outcome"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Your prediction</FormLabel>
                <Select
                  value={field.value}
                  onValueChange={field.onChange}
                  disabled={isClosed}
                >
                  <FormControl>
                    <SelectTrigger className="h-11" aria-label="Your prediction">
                      <SelectValue />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    <SelectItem value="YES">YES</SelectItem>
                    <SelectItem value="NO">NO</SelectItem>
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="stake"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Stake ({CURRENCY})</FormLabel>
                <FormControl>
                  <Input
                    type="text"
                    inputMode="decimal"
                    placeholder="0.00"
                    autoComplete="off"
                    disabled={isClosed}
                    className="h-11"
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <p className="flex items-center justify-between text-sm text-zinc-500">
            <span>Expected payout</span>
            <span className="font-normal text-zinc-950 dark:text-zinc-50">
              {payout} {CURRENCY}
            </span>
          </p>

          {isClosed && (
            <p
              role="alert"
              className="text-sm font-semibold text-rose-700 dark:text-rose-400"
              data-testid="market-closed"
            >
              This market is closed and no longer accepting bets.
            </p>
          )}

          {formError && (
            <div
              role="alert"
              className="text-sm font-semibold text-red-500"
              data-testid="bet-error"
            >
              {formError}
              {/* The unverified-email error carries a resend affordance. */}
              {formError === "Verify your email to place bets." && (
                <>
                  {" "}
                  <Link href="/verify-email" className="underline">
                    Resend verification
                  </Link>
                </>
              )}
            </div>
          )}

          {success && <BetPlacedSuccess message={success} />}

          <Button
            type="submit"
            size="lg"
            className="w-full"
            disabled={isClosed || pending}
          >
            {pending ? "Placing bet…" : "Place bet"}
          </Button>
        </form>
      </Form>

      <BetConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        stake={stake ?? ""}
        yesPct={yesPct}
        noPct={noPct}
        payout={payout}
        onConfirm={onConfirm}
        pending={pending}
      />
    </>
  );
}
