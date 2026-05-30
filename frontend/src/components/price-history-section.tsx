/**
 * Plan 09-04 — Price-history section wrapper (MKT-03).
 *
 * A small `"use client"` bridge that owns the chart's window state and
 * re-fetches the points when the player toggles 24h / 7d / 30d, composing the
 * Plan 03 `PriceHistoryChart` (which is a controlled component — the parent
 * owns `window` + `onWindowChange`).
 *
 * SSR seeds the initial 7d points (SP-5); subsequent window switches fetch
 * client-side via `fetchPriceHistory`. On a fetch failure we keep the last
 * good points (the chart degrades to its own empty state if <2 points), never
 * crashing the page. Money/odds stay strings on the wire (SP-1).
 */
"use client";

import { useState, useTransition } from "react";

import { PriceHistoryChart } from "@/components/price-history-chart";
import {
  fetchPriceHistory,
  type PricePoint,
  type PriceWindow,
} from "@/lib/api";

interface PriceHistorySectionProps {
  slug: string;
  initialPoints: PricePoint[];
  initialWindow?: PriceWindow;
}

export function PriceHistorySection({
  slug,
  initialPoints,
  initialWindow = "7d",
}: PriceHistorySectionProps) {
  const [window, setWindow] = useState<PriceWindow>(initialWindow);
  const [points, setPoints] = useState<PricePoint[]>(initialPoints);
  const [, startFetch] = useTransition();

  const onWindowChange = (next: PriceWindow) => {
    if (next === window) return;
    setWindow(next);
    startFetch(() => {
      void fetchPriceHistory(slug, next)
        .then((res) => setPoints(res.points))
        .catch(() => {
          // Keep the last good points; the chart shows its own empty state
          // if it drops below 2 points. Never crash the page on a transient
          // fetch error.
        });
    });
  };

  return (
    <PriceHistoryChart
      points={points}
      window={window}
      onWindowChange={onWindowChange}
    />
  );
}
