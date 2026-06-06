/**
 * OutcomeRow — one INDEPENDENT outcome of a multi-outcome event (EVT-02).
 *
 * Each row shows ONLY this outcome's own YES probability (0–100%) on its own
 * bar — its YES vs its OWN NO complement, a truthful per-binary split. It is
 * NEVER a segment of a single bar that sums to 100% across outcomes (the
 * framing LOCK). A keyboard-accessible button; the selected row carries the
 * brand ring. Non-OPEN children show a status chip.
 */
"use client";

import { MarketStatusBadge } from "@/components/admin/market-status-badge";
import { cn } from "@/lib/utils";

interface OutcomeRowProps {
  label: string;
  yesPct: number;
  status: string;
  selected: boolean;
  onSelect: () => void;
}

export function OutcomeRow({
  label,
  yesPct,
  status,
  selected,
  onSelect,
}: OutcomeRowProps) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      aria-label={`${label}, ${yesPct}% YES`}
      className={cn(
        "flex w-full flex-col gap-2 rounded-xl border p-3.5 text-left transition-all",
        selected
          ? "border-brand-primary/60 bg-brand-primary/5 ring-1 ring-brand-primary/40"
          : "border-border bg-card hover:border-border-strong hover:bg-surface",
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <span className="flex min-w-0 items-center gap-2">
          <span className="min-w-0 truncate font-medium">{label}</span>
          {status !== "OPEN" && <MarketStatusBadge status={status} />}
        </span>
        <span className="shrink-0 font-semibold tabular-nums">{yesPct}%</span>
      </div>
      {/* This outcome's OWN YES bar — independent, never a cross-outcome sum. */}
      <div
        className="h-2 w-full overflow-hidden rounded-full bg-muted"
        role="img"
        aria-label={`${label}: ${yesPct}% YES`}
      >
        <div
          className="h-full rounded-full bg-gradient-brand transition-[width] duration-500"
          style={{ width: `${yesPct}%` }}
        />
      </div>
    </button>
  );
}
