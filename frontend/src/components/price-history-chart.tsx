/**
 * PriceHistoryChart -- Recharts YES-probability chart for a market's price
 * history (Plan 09-03, MKT-03), restyled dark-first (Phase 19).
 *
 * Contract (UI-SPEC §"Price-history chart" + RESEARCH Code Examples):
 *   - YES probability ONLY (binary market; NO is the complement, not plotted).
 *     A glowing brand gradient line over a soft gradient area fill.
 *   - 24h / 7d / 30d window toggle, default 7d. Selecting a window calls
 *     `onWindowChange` — the parent owns the window state + re-fetch.
 *   - <2 points renders a friendly empty state at the same h-64 height (no
 *     layout collapse / jump).
 *
 * GOTCHAS baked in:
 *   - `react-is` must be pinned to the installed React version + a pnpm override,
 *     or Recharts renders blank on React 19 (RESEARCH Pitfall 1). The
 *     chart-not-blank smoke test asserts `path.recharts-line-curve` — a `<Line>`
 *     inside `<ComposedChart>` keeps emitting that class (the Area adds the fill).
 *   - <ResponsiveContainer> collapses to 0 height without a sized parent, so the
 *     wrapper is a fixed `h-64` (RESEARCH Pitfall 2).
 *   - Money/odds are strings on the wire; only round for display (SP-1).
 */
"use client";

import { useId } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { PricePoint, PriceWindow } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const WINDOWS: PriceWindow[] = ["24h", "7d", "30d"];

// X-axis / tooltip date formatting: raw ISO timestamps are unreadable on the
// axis. 24h window → time of day; 7d/30d → short date. en-US keeps the format
// aligned with the app's English chrome regardless of device locale.
function axisTickFormatter(ts: string, w: PriceWindow): string {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "";
  return w === "24h"
    ? d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })
    : d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function tooltipLabelFormatter(ts: string): string {
  const d = new Date(ts);
  return Number.isNaN(d.getTime())
    ? ""
    : d.toLocaleString("en-US", {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      });
}

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
    <div className="flex h-64 w-full flex-col items-center justify-center rounded-xl border border-dashed border-border text-center">
      <p className="text-base font-semibold text-foreground">
        Not enough price history yet
      </p>
      <p className="mt-1 max-w-xs text-sm text-muted-foreground">
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
  const uid = useId().replace(/:/g, "");
  const areaId = `pharea-${uid}`;
  const lineId = `phline-${uid}`;

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
            <ComposedChart
              data={points.map((p) => ({
                ts: p.ts,
                // string -> display percent only (SP-1); never stored as float
                yes: Math.round(parseFloat(p.probability) * 100),
              }))}
              margin={{ top: 8, right: 8, bottom: 0, left: -16 }}
            >
              <defs>
                <linearGradient id={areaId} x1="0" y1="0" x2="0" y2="1">
                  <stop
                    offset="0%"
                    stopColor="var(--brand-primary)"
                    stopOpacity={0.35}
                  />
                  <stop
                    offset="100%"
                    stopColor="var(--brand-primary)"
                    stopOpacity={0}
                  />
                </linearGradient>
                <linearGradient id={lineId} x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stopColor="var(--brand-primary)" />
                  <stop offset="100%" stopColor="var(--brand-secondary)" />
                </linearGradient>
              </defs>
              <CartesianGrid
                stroke="var(--border)"
                strokeDasharray="3 3"
                vertical={false}
              />
              <XAxis
                dataKey="ts"
                tickFormatter={(value) => axisTickFormatter(String(value), window)}
                tick={{ fontSize: 12, fill: "var(--muted-foreground)" }}
                axisLine={{ stroke: "var(--border)" }}
                tickLine={false}
                minTickGap={40}
              />
              <YAxis
                domain={[0, 100]}
                unit="%"
                tick={{ fontSize: 12, fill: "var(--muted-foreground)" }}
                axisLine={false}
                tickLine={false}
                width={44}
              />
              <Tooltip
                cursor={{ stroke: "var(--border-strong)", strokeWidth: 1 }}
                contentStyle={{
                  background: "var(--popover)",
                  border: "1px solid var(--border)",
                  borderRadius: "0.75rem",
                  color: "var(--popover-foreground)",
                  fontSize: "0.8rem",
                  boxShadow: "var(--shadow-pop)",
                }}
                labelStyle={{ color: "var(--muted-foreground)" }}
                itemStyle={{ color: "var(--foreground)" }}
                labelFormatter={(label) => tooltipLabelFormatter(String(label))}
                formatter={(value) => [`${value}%`, "YES"]}
              />
              <Area
                type="monotone"
                dataKey="yes"
                stroke="none"
                fill={`url(#${areaId})`}
                isAnimationActive={false}
              />
              <Line
                type="monotone"
                dataKey="yes"
                stroke={`url(#${lineId})`}
                strokeWidth={2.5}
                dot={false}
                activeDot={{
                  r: 4,
                  fill: "var(--brand-primary)",
                  stroke: "var(--background)",
                  strokeWidth: 2,
                }}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
