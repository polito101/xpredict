/**
 * PriceHistoryChart -- Recharts YES-probability line chart for a market's
 * price history (Plan 09-03, MKT-03).
 *
 * Contract (UI-SPEC §"Price-history chart" + RESEARCH Code Examples):
 *   - YES probability line ONLY (binary market; NO is the complement and is
 *     explicitly NOT plotted in v1). Stroke = emerald-600 (#059669).
 *   - 24h / 7d / 30d window toggle, default 7d. Selecting a window calls
 *     `onWindowChange` — the parent owns the window state + re-fetch.
 *   - <2 points renders a friendly empty state at the same h-64 height (no
 *     layout collapse / jump).
 *
 * GOTCHAS baked in:
 *   - `react-is` must be pinned to the installed React version + a pnpm
 *     override, or Recharts renders blank on React 19 (RESEARCH Pitfall 1).
 *     The chart-not-blank smoke test is the sentinel for that.
 *   - <ResponsiveContainer> collapses to 0 height without a sized parent, so
 *     the wrapper is a fixed `h-64` (RESEARCH Pitfall 2).
 *   - Money/odds are strings on the wire; we only round for display
 *     (`Math.round(parseFloat(...) * 100)`), never store as floats (SP-1).
 */
"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { PricePoint, PriceWindow } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const WINDOWS: PriceWindow[] = ["24h", "7d", "30d"];

interface PriceHistoryChartProps {
  points: PricePoint[];
  window: PriceWindow;
  onWindowChange: (window: PriceWindow) => void;
}

function WindowToggle({
  window,
  onWindowChange,
}: {
  window: PriceWindow;
  onWindowChange: (window: PriceWindow) => void;
}) {
  return (
    <div className="flex gap-1" role="group" aria-label="Price history window">
      {WINDOWS.map((w) => {
        const active = w === window;
        return (
          <Button
            key={w}
            type="button"
            size="sm"
            variant={active ? "secondary" : "ghost"}
            aria-pressed={active}
            onClick={() => onWindowChange(w)}
            // ≥44px mobile touch target (UI-SPEC §Spacing) — `h-11` overrides
            // the `size="sm"` h-9 (36px) while keeping the compact px-3 width.
            className={cn("h-11", active && "font-semibold")}
          >
            {w}
          </Button>
        );
      })}
    </div>
  );
}

function ChartEmptyState() {
  return (
    <div className="flex h-64 w-full flex-col items-center justify-center text-center">
      <p className="text-lg font-semibold text-zinc-950 dark:text-zinc-50">
        Not enough price history yet
      </p>
      <p className="mt-1 max-w-xs text-sm text-zinc-500">
        Check back soon — the chart appears once this market has a couple of
        price snapshots.
      </p>
    </div>
  );
}

export function PriceHistoryChart({
  points,
  window,
  onWindowChange,
}: PriceHistoryChartProps) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-end">
        <WindowToggle window={window} onWindowChange={onWindowChange} />
      </div>
      {points.length < 2 ? (
        <ChartEmptyState />
      ) : (
        <div className="h-64 w-full">
          {/* sized parent — ResponsiveContainer collapses to 0 otherwise */}
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={points.map((p) => ({
                ts: p.ts,
                // string -> display percent only (SP-1); never stored as float
                yes: Math.round(parseFloat(p.probability) * 100),
              }))}
            >
              <CartesianGrid stroke="#e4e4e7" strokeDasharray="3 3" />
              <XAxis
                dataKey="ts"
                tick={{ fontSize: 12, fill: "#71717a" }}
              />
              <YAxis
                domain={[0, 100]}
                unit="%"
                tick={{ fontSize: 12, fill: "#71717a" }}
              />
              <Tooltip />
              <Line
                type="monotone"
                dataKey="yes"
                stroke="#059669"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
