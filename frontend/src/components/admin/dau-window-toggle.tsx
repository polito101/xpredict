/**
 * Plan 10-04 — DauWindowToggle: the inline 24h/7d/30d window toggle on the DAU
 * KPI card. Copied near-verbatim from price-history-chart.tsx `WindowToggle`
 * (UI-SPEC §Interaction Contract): `flex gap-1` `role="group"`, each button is
 * `variant="secondary"` (active) / `"ghost"` (inactive) with `aria-pressed` and
 * an `h-11` (44px) touch target. Default window is `24h` (D-05). Selecting a
 * window lifts it to the parent via `onChange`, which refetches the KPI
 * endpoint with `?window=` and updates the DAU value + the chart.
 */
"use client";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { KpiWindow } from "@/lib/kpi-types";

const WINDOWS: KpiWindow[] = ["24h", "7d", "30d"];

export function DauWindowToggle({
  window,
  onChange,
  disabled = false,
}: {
  window: KpiWindow;
  onChange: (window: KpiWindow) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex gap-1" role="group" aria-label="Active-users window">
      {WINDOWS.map((w) => {
        const active = w === window;
        return (
          <Button
            key={w}
            type="button"
            size="sm"
            variant={active ? "secondary" : "ghost"}
            aria-pressed={active}
            disabled={disabled}
            onClick={() => onChange(w)}
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
