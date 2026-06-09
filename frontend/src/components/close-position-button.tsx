"use client";

import { useActionState } from "react";

import { sellPositionAction } from "@/lib/bet-actions";
import type { SellState } from "@/lib/bet-schemas";

/**
 * Per-position "Cerrar / Cash out" control. Submits the bet id to `sellPositionAction`;
 * shows the live cash-out value on the button, a pending state while closing, and the
 * success/error message inline. On success the action revalidates `/portfolio`.
 */
export function ClosePositionButton({
  betId,
  cashout,
}: {
  betId: string;
  cashout: string;
}) {
  const [state, formAction, pending] = useActionState<SellState, FormData>(
    sellPositionAction,
    {},
  );

  return (
    <form action={formAction} className="flex flex-col gap-1">
      <input type="hidden" name="bet_id" value={betId} />
      <button
        type="submit"
        disabled={pending}
        className="inline-flex items-center justify-center rounded-lg border border-border px-3 py-1.5 text-sm font-medium transition-colors hover:border-border-strong disabled:opacity-50"
      >
        {pending ? "Cerrando…" : `Cerrar · cobra ${cashout} PLAY_USD`}
      </button>
      {state.error ? (
        <p role="alert" className="text-xs text-rose-400">
          {state.error}
        </p>
      ) : null}
      {state.success && state.message ? (
        <p className="text-xs text-emerald-400">{state.message}</p>
      ) : null}
    </form>
  );
}
