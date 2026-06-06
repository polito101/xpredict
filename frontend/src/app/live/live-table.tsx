/**
 * LB-B-02 — `<live-bets-table>` widget host (client island).
 *
 * Loads the live-bets widget script via `next/script` (design §4 — served from
 * the live-bets origin locally; no SRI in dev) and renders the custom element
 * `<live-bets-table>` (design §5 — the element contract). The page (server)
 * mints the session + resolves the table and passes them in; this island owns
 * the widget lifecycle + (Task 3) the DOM-event wiring + the in-island wallet
 * balance.
 *
 * React 19 renders custom elements and passes props through, but HYPHENATED
 * attributes (`session-token`, `table-id`) are set via `ref` + `setAttribute` —
 * the robust path for hyphenated names, and it lets the session-expired handler
 * re-set the token imperatively.
 *
 * DOM events (design §5/§6, SC3): the four widget events are wired in a single
 * effect that REMOVES every listener on cleanup. Each maps to an LB-B-01 Server
 * Action; placed/settled then refresh the IN-ISLAND wallet balance via
 * `getLiveBalance` (plan-check M-2 — `router.refresh()` would re-run the Server
 * Component but NOT update this island's `useState` balance, leaving it stale).
 * `applied:false` is a benign idempotent no-op (a duplicate event), NOT an error.
 *
 * TypeScript: `<live-bets-table>` is declared on `React.JSX.IntrinsicElements`
 * via a `declare module "react"` augmentation (verified against the installed
 * `@types/react@19`, where `JSX` lives under the `react` module export, NOT a
 * global `JSX` namespace — the `react-jsx` runtime resolves intrinsic elements
 * through `React.JSX.IntrinsicElements`). No `any`.
 */
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Script from "next/script";
import { toast } from "sonner";

import {
  getLiveBalance,
  mintLiveSession,
  recordLivePlaced,
  recordLiveSettled,
} from "@/lib/live-actions";

// React 19 custom-element typing: augment `React.JSX.IntrinsicElements` (this
// @types/react ships `JSX` under the module, not a global namespace) so
// `<live-bets-table>` typechecks WITHOUT `any`. The hyphenated attributes are
// set imperatively via setAttribute, so the element only needs the base HTML
// attribute surface here.
declare module "react" {
  // Module augmentation for a JSX intrinsic element REQUIRES a `namespace`
  // declaration (declaration merging into `React.JSX`); the `no-namespace` rule
  // has no ES-module equivalent for this, so it is disabled for this one line.
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace JSX {
    interface IntrinsicElements {
      "live-bets-table": React.DetailedHTMLProps<
        React.HTMLAttributes<HTMLElement>,
        HTMLElement
      >;
    }
  }
}

const CURRENCY = "PLAY_USD";

export interface LiveTableProps {
  sessionToken: string;
  tableId: string;
  initialBalance: string;
}

/**
 * Client host for the live-bets widget. Renders the wallet balance (a labelled
 * element matching `wallet/page.tsx`) so Task 3's refresh can update it in place,
 * loads `widget.js`, and renders `<live-bets-table>` with `session-token` +
 * `table-id` set via `setAttribute`.
 */
/** Defensive read of `bet_id` off an untrusted widget event detail. */
function readBetId(detail: unknown): string | null {
  if (detail && typeof detail === "object" && "bet_id" in detail) {
    const v = (detail as { bet_id?: unknown }).bet_id;
    if (typeof v === "string" && v.length > 0) return v;
  }
  return null;
}

/** Defensive read of an optional string field off an untrusted event detail. */
function readString(detail: unknown, key: string): string | null {
  if (detail && typeof detail === "object" && key in detail) {
    const v = (detail as Record<string, unknown>)[key];
    if (typeof v === "string" && v.length > 0) return v;
  }
  return null;
}

export function LiveTable({
  sessionToken,
  tableId,
  initialBalance,
}: LiveTableProps) {
  const elementRef = useRef<HTMLElement>(null);
  // Balance is held locally so the wallet refresh can move it IN PLACE (the
  // unified XPredict balance reacting to bets is the whole point — design §8).
  const [balance, setBalance] = useState(initialBalance);

  const widgetSrc = process.env.NEXT_PUBLIC_LIVEBETS_WIDGET_SRC;

  // M-2: re-read the XPredict balance and update the LOCAL state after a mirror,
  // so the displayed balance actually moves (router.refresh() would not touch
  // this island's useState copy). A failed refresh leaves the prior value.
  const refreshBalance = useCallback(async () => {
    const result = await getLiveBalance();
    if (result.ok) setBalance(result.balance);
  }, []);

  // Set the hyphenated attributes imperatively (the robust path for custom
  // elements). Keyed on the server-provided props; the session-expired handler
  // re-sets `session-token` on the element directly (no state → no re-render
  // churn, and no setState-in-effect). Re-running this effect on a fresh
  // `sessionToken` prop re-applies the server's value, which is correct.
  useEffect(() => {
    const el = elementRef.current;
    if (!el) return;
    el.setAttribute("session-token", sessionToken);
    el.setAttribute("table-id", tableId);
  }, [sessionToken, tableId]);

  // Wire the four widget DOM events; the cleanup removes EVERY listener (SC3).
  // The event detail is UNTRUSTED (third-party widget) — only `bet_id` is passed
  // to the Server Action; LB-A re-verifies status/stake/payout (T-LBB-04).
  useEffect(() => {
    const el = elementRef.current;
    if (!el) return;

    const onPlaced = (e: Event) => {
      const betId = readBetId((e as CustomEvent).detail);
      if (!betId) return; // missing bet_id → defensive no-op (no call).
      void (async () => {
        const result = await recordLivePlaced(betId);
        if (result.ok) {
          await refreshBalance();
        } else {
          toast.error("Couldn't record your bet. Please try again.");
        }
      })();
    };

    const onResult = (e: Event) => {
      // WR-01: only `bet_id` is taken from the UNTRUSTED event detail; the
      // win/loss toast is keyed off the BACKEND's authoritative settle status
      // (returned by recordLiveSettled), NOT `detail.status`. A tampered widget
      // emitting `{bet_id, status:"WON"}` for a bet the backend settles as LOST
      // must show the "lost" copy, not a celebratory "You won!".
      const betId = readBetId((e as CustomEvent).detail);
      if (!betId) return;
      void (async () => {
        const result = await recordLiveSettled(betId);
        if (!result.ok) {
          toast.error("Couldn't settle your bet. Please try again.");
          return;
        }
        await refreshBalance();
        // Idempotent no-op (already settled): nothing moved, so no win/loss
        // toast — a benign duplicate event must not re-announce an outcome.
        if (!result.applied) return;
        const status = result.status?.toUpperCase();
        if (status === "WON") {
          toast.success("You won! Your balance has been updated.");
        } else if (status === "LOST") {
          toast("Bet settled — better luck next round.");
        } else {
          // REFUNDED/VOIDED or a missing status → neutral, non-misleading copy.
          toast("Bet settled. Your balance has been updated.");
        }
      })();
    };

    const onSessionExpired = () => {
      void (async () => {
        const result = await mintLiveSession(tableId);
        if (result.ok) {
          // Re-set the token imperatively on the element (design §7 re-mint).
          elementRef.current?.setAttribute(
            "session-token",
            result.session_token,
          );
        } else {
          toast.error("Your live session expired. Please refresh the page.");
        }
      })();
    };

    const onError = (e: Event) => {
      const message = readString((e as CustomEvent).detail, "message");
      toast.error(message ?? "The live table hit an error. Please try again.");
    };

    el.addEventListener("live-bets-bet-placed", onPlaced);
    el.addEventListener("live-bets-result", onResult);
    el.addEventListener("live-bets-session-expired", onSessionExpired);
    el.addEventListener("live-bets-error", onError);

    return () => {
      el.removeEventListener("live-bets-bet-placed", onPlaced);
      el.removeEventListener("live-bets-result", onResult);
      el.removeEventListener("live-bets-session-expired", onSessionExpired);
      el.removeEventListener("live-bets-error", onError);
    };
  }, [tableId, refreshBalance]);

  return (
    <div className="flex flex-col gap-4">
      <div
        className="flex items-baseline gap-2"
        aria-label="wallet balance"
        data-testid="live-balance"
      >
        <span className="font-display text-2xl font-semibold tracking-tight tabular-nums">
          {balance}
        </span>
        <span className="text-sm font-normal text-muted-foreground">
          {CURRENCY}
        </span>
      </div>

      {/* If the widget src isn't configured, render a non-blocking notice rather
          than an empty `<script src="undefined">` (T-LBB-07). */}
      {widgetSrc ? (
        <Script src={widgetSrc} strategy="afterInteractive" />
      ) : (
        <p
          role="status"
          className="rounded-xl border border-border bg-surface p-4 text-sm text-muted-foreground"
        >
          Live widget not configured.
        </p>
      )}

      <live-bets-table ref={elementRef} />
    </div>
  );
}
