/**
 * VolumeChart — Recharts AreaChart of 30-day daily bet volume for the admin
 * KPI dashboard (Plan 10-04, ADD-03 / D-06). Mirrors price-history-chart.tsx
 * (LineChart → AreaChart, probability → volume, X axis ts → day).
 *
 * Contract (10-UI-SPEC §Component Inventory / §Copywriting):
 *   - Title "Bet volume — last 30 days".
 *   - Daily buckets over 30 days. Stroke/fill `var(--brand-primary)` (so the
 *     chart re-skins live with operator branding) with an emerald-600 fallback.
 *   - `<1 bucket` → VolumeChartEmptyState at the SAME `h-64` height (heading
 *     "No activity yet", body "Volume appears here as players place bets.") —
 *     never a blank Recharts axis.
 *
 * GOTCHAS baked in (RESEARCH / T-10-16):
 *   - `react-is` is pinned to the installed React via pnpm.overrides, or
 *     Recharts renders blank on React 19. The not-blank smoke test
 *     (volume-chart.test.tsx) is the sentinel. Do NOT touch the pin.
 *   - <ResponsiveContainer> collapses to 0 height without a sized parent, so
 *     the wrapper is a fixed `h-64`. The empty state occupies the same height.
 *   - Money/volume are STRINGS on the wire; we only `parseFloat` for DISPLAY
 *     (the chart Y value), never store as a float (money-as-string contract).
 */
"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { VolumeBucket } from "@/lib/kpi-types";

/** Brand-primary stroke/fill so the chart re-skins live; emerald fallback. */
const VOLUME_STROKE = "var(--brand-primary, #059669)";

function VolumeChartEmptyState() {
  return (
    <div className="flex h-64 w-full flex-col items-center justify-center text-center">
      <p className="text-lg font-semibold text-zinc-950 dark:text-zinc-50">
        No activity yet
      </p>
      <p className="mt-1 max-w-xs text-sm text-zinc-500">
        Volume appears here as players place bets.
      </p>
    </div>
  );
}

export function VolumeChart({ buckets }: { buckets: VolumeBucket[] }) {
  return (
    <div className="space-y-2">
      <h2 className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
        Bet volume — last 30 days
      </h2>
      {buckets.length < 1 ? (
        <VolumeChartEmptyState />
      ) : (
        <div className="h-64 w-full">
          {/* sized parent — ResponsiveContainer collapses to 0 otherwise */}
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={buckets.map((b) => ({
                day: b.day,
                // string -> display number only (money-as-string); never stored.
                // Rounds to 2 decimal places for Y-axis display (÷100 = 2 dp).
                // The wire value has 4 dp; the axis uses 2 dp intentionally for
                // readability — kpi-card.tsx still shows full 4 dp in the cards.
                volume: Math.round(parseFloat(b.volume) * 100) / 100,
              }))}
            >
              <CartesianGrid stroke="#e4e4e7" strokeDasharray="3 3" />
              <XAxis
                dataKey="day"
                tick={{ fontSize: 12, fill: "#71717a" }}
              />
              <YAxis tick={{ fontSize: 12, fill: "#71717a" }} />
              <Tooltip />
              <Area
                type="monotone"
                dataKey="volume"
                stroke={VOLUME_STROKE}
                fill={VOLUME_STROKE}
                fillOpacity={0.15}
                strokeWidth={2}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
