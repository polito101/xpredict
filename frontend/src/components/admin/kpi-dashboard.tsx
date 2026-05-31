/**
 * Plan 10-04 — KpiDashboard: the client wrapper that owns the DAU window state
 * and refetch. It takes the initial server-fetched KpiResponse (from the
 * /admin Server Component), renders the DAU window toggle inline on the DAU
 * card, and on toggle re-calls the `fetchKpis` "use server" action with the
 * new window — updating BOTH the DAU value and the chart (UI-SPEC §Interaction
 * Contract). The refetch runs inside a transition so the UI stays responsive
 * and the toggle disables while pending.
 *
 * The admin Bearer never reaches this client component — `fetchKpis` reads the
 * HttpOnly `admin_jwt` cookie server-side (T-10-15).
 */
"use client";

import * as React from "react";

import { KpiGrid } from "@/components/admin/kpi-card";
import { DauWindowToggle } from "@/components/admin/dau-window-toggle";
import { VolumeChart } from "@/components/admin/volume-chart";
import { fetchKpis } from "@/lib/kpi-api";
import type { KpiResponse, KpiWindow } from "@/lib/kpi-types";

export function KpiDashboard({ initial }: { initial: KpiResponse }) {
  const [kpis, setKpis] = React.useState<KpiResponse>(initial);
  const [window, setWindow] = React.useState<KpiWindow>("24h");
  const [pending, startTransition] = React.useTransition();

  function onWindowChange(next: KpiWindow) {
    if (next === window) return;
    setWindow(next);
    startTransition(async () => {
      try {
        const fresh = await fetchKpis(next);
        setKpis(fresh);
      } catch {
        // Keep the last good payload on a transient refetch failure; the
        // initial server load already surfaced any hard error on the page.
      }
    });
  }

  return (
    <div className="mt-8 space-y-8">
      <KpiGrid
        kpis={kpis}
        dauToggle={
          <DauWindowToggle
            window={window}
            onChange={onWindowChange}
            disabled={pending}
          />
        }
      />
      <VolumeChart buckets={kpis.volume_buckets} />
    </div>
  );
}
