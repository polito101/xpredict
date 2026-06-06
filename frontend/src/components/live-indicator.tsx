/**
 * LiveIndicator -- a small inline dot + label driven by the market socket's
 * connection state (Plan 09-03 Task 4, MKT-04 / UI-SPEC connection-state table).
 *
 * Mirrors the `odds-display.tsx` semantic-color idiom (emerald / amber). The
 * state machine is owned by `useMarketSocket`; this component only renders it.
 *
 *   live         -> emerald-500 pulsing dot + "Live"
 *   stale        -> amber-500 solid dot     + "Stale"   (odds kept visible)
 *   reconnecting -> amber-500 pulsing dot   + "Reconnecting…"
 *
 * Wrapped in `aria-live="polite"` so the state change is announced to assistive
 * tech without stealing focus.
 */
"use client";

import type { ConnState } from "@/hooks/use-market-socket";
import { cn } from "@/lib/utils";

interface LiveIndicatorProps {
  state: ConnState;
  className?: string;
}

const STATE_CONFIG: Record<
  ConnState,
  { dot: string; label: string; text: string }
> = {
  live: {
    dot: "bg-emerald-400 animate-pulse shadow-[0_0_8px] shadow-emerald-400/70",
    label: "Live",
    text: "text-emerald-400",
  },
  stale: {
    dot: "bg-amber-400",
    label: "Stale",
    text: "text-amber-400",
  },
  reconnecting: {
    dot: "bg-amber-400 animate-pulse",
    label: "Reconnecting…",
    text: "text-amber-400",
  },
};

export function LiveIndicator({ state, className }: LiveIndicatorProps) {
  const { dot, label, text } = STATE_CONFIG[state];
  return (
    <span
      className={cn("inline-flex items-center gap-1", className)}
      aria-live="polite"
    >
      <span
        className={cn("h-2 w-2 rounded-full", dot)}
        aria-hidden="true"
      />
      <span className={cn("text-xs font-semibold", text)}>{label}</span>
    </span>
  );
}
