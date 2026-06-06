/**
 * Plan 10-04 — KPI cards (KpiCard + KpiGrid) for the admin dashboard.
 *
 * Composes the existing shadcn `Card` primitive (UI-SPEC §Component Inventory):
 *   - label: `text-sm text-zinc-500`
 *   - value: `text-2xl font-semibold tabular-nums`
 *
 * MONEY DISCIPLINE (CLAUDE.md hard constraint): money arrives as a STRING and
 * is rendered via DISPLAY-ONLY formatting (`formatMoney` — string ops, a fixed
 * 4-dp padded display). The value is NEVER coerced with `parseFloat`/`Number()`
 * into a number for storage — the money field stays `string` end to end
 * (kpi-types.ts). The House P&L sign is read from the string (a leading "-"
 * with non-zero magnitude), not from a float, to pick the value color:
 * `emerald-600` for >= 0, `red-500` for < 0 (UI-SPEC §Color, guarded by
 * kpi-card.test.tsx).
 *
 * Fresh-deploy zeros render as a real "0" / "$0.0000" — NEVER "N/A"/em-dash
 * (UI-SPEC A-ZERO: a real zero is meaningful for "is this platform healthy?").
 */
import * as React from "react";
import Link from "next/link";

import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { KpiResponse } from "@/lib/kpi-types";

/**
 * Format a money STRING for display only — pads to 4 decimal places and
 * prefixes "$". Pure string manipulation; no `parseFloat`/`Number()` (the
 * stored value stays a string). A leading "+" is dropped; a leading "-" is
 * preserved as "-$x".
 *
 * Guard (IN-05): empty or non-numeric input (e.g. the backend sends null/""
 * on a schema change) returns "$—" instead of the misleading "$0.0000" or
 * "$abc.0000". A real "0" from the backend still renders as "$0.0000" per
 * UI-SPEC A-ZERO — a zero is meaningful and must never be an em-dash.
 */
export function formatMoney(raw: string): string {
  const trimmed = raw.trim();
  // Reject empty strings and values that are not a valid signed decimal number.
  // A valid money string is an optional sign followed by digits, optionally
  // with a decimal point and more digits — nothing else (no letters, no spaces).
  if (trimmed === "" || !/^[+-]?\d+(\.\d+)?$/.test(trimmed)) {
    return "$—"; // em-dash placeholder: "$—"
  }
  const negative = trimmed.startsWith("-");
  const unsigned = trimmed.replace(/^[+-]/, "");
  const [intPart, fracPartRaw = ""] = unsigned.split(".");
  const fracPart = (fracPartRaw + "0000").slice(0, 4);
  const body = `$${intPart || "0"}.${fracPart}`;
  return negative ? `-${body}` : body;
}

/**
 * True when a money STRING is strictly negative — a leading "-" AND a non-zero
 * magnitude (so "-0.0000" is treated as zero, not negative). String-only; no
 * float coercion.
 */
export function isNegativeMoney(raw: string): boolean {
  const trimmed = raw.trim();
  if (!trimmed.startsWith("-")) return false;
  // Non-zero magnitude if any digit 1-9 remains after stripping sign + dot.
  return /[1-9]/.test(trimmed.replace(/[-.]/g, ""));
}

export interface KpiCardProps {
  label: string;
  /** Display value (already formatted for money, or a plain integer string). */
  value: string;
  /** When true, color the value by sign (P&L): negative red-500, else emerald-600. */
  colorBySign?: boolean;
  /** Raw money string used for the sign check when `colorBySign` is set. */
  rawValue?: string;
  /** Optional sub-caption (e.g. the DAU toggle) in the header. */
  caption?: React.ReactNode;
}

export function KpiCard({
  label,
  value,
  colorBySign = false,
  rawValue,
  caption,
}: KpiCardProps) {
  const negative = colorBySign && isNegativeMoney(rawValue ?? value);
  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm text-muted-foreground">{label}</span>
          {caption}
        </div>
      </CardHeader>
      <CardContent>
        <span
          data-testid="kpi-value"
          className={cn(
            "text-2xl font-semibold tabular-nums",
            colorBySign && (negative ? "text-red-500" : "text-emerald-600"),
          )}
        >
          {value}
        </span>
      </CardContent>
    </Card>
  );
}

/**
 * The House P&L card — ONE card showing both Today and All-time money values,
 * each colored by sign (negative red-500, else emerald-600). This keeps the
 * grid at five cards (UI-SPEC: P&L is a single card with two sub-captions).
 */
export function HousePnlCard({
  today,
  cumulative,
}: {
  today: string;
  cumulative: string;
}) {
  const rows: { caption: string; raw: string }[] = [
    { caption: "Today", raw: today },
    { caption: "All-time", raw: cumulative },
  ];
  return (
    <Card>
      <CardHeader className="pb-2">
        <span className="text-sm text-muted-foreground">House P&amp;L</span>
      </CardHeader>
      <CardContent className="flex flex-col gap-1">
        {rows.map(({ caption, raw }) => (
          <div key={caption} className="flex items-baseline justify-between gap-2">
            <span className="text-sm text-muted-foreground">{caption}</span>
            <span
              data-testid={`kpi-pnl-${caption.toLowerCase()}`}
              className={cn(
                "text-2xl font-semibold tabular-nums",
                isNegativeMoney(raw) ? "text-red-500" : "text-emerald-600",
              )}
            >
              {formatMoney(raw)}
            </span>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

/**
 * The five KPI cards in a responsive grid (UI-SPEC §Responsive Contract):
 * grid-cols-1 (mobile) → sm:grid-cols-2 → lg:grid-cols-3 (5 cards reflow 3+2).
 *
 * The DAU card carries the inline 24h/7d/30d toggle (passed in as `dauToggle`
 * so the parent owns the window state + refetch — mirrors price-history).
 */
export function KpiGrid({
  kpis,
  dauToggle,
}: {
  kpis: KpiResponse;
  dauToggle?: React.ReactNode;
}) {
  return (
    <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
      <KpiCard label="24h bet volume" value={formatMoney(kpis.volume_24h)} />
      <KpiCard
        label="Daily active users"
        value={String(kpis.daily_active_users)}
        caption={dauToggle}
      />
      <KpiCard label="Active markets" value={String(kpis.active_markets)} />
      {/* A-KPI-LINK: the "Pending resolutions" card deep-links to the markets
          that need action — status=CLOSED is the closest queryable proxy for
          "past-deadline awaiting resolution". The card visual is unchanged; the
          Link only adds the navigation affordance (block so the whole card is
          the hit target; rounded-xl matches the Card radius for focus ring). */}
      <Link
        href="/admin/markets?status=CLOSED"
        className="block rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-label="Pending resolutions — view markets awaiting action"
      >
        <KpiCard
          label="Pending resolutions"
          value={String(kpis.pending_resolutions)}
        />
      </Link>
      <HousePnlCard
        today={kpis.house_pnl_today}
        cumulative={kpis.house_pnl_cumulative}
      />
    </div>
  );
}
