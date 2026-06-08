/**
 * InfraMetrics — production-readiness signal for the landing (Quality Pass).
 *
 * A second metrics band beneath the live catalog stats. These are INFRASTRUCTURE
 * metrics (uptime, API throughput, settlements, active deployments) shown as
 * HONEST PLACEHOLDERS ("—") — styled to read like the real metric band, but never
 * fabricated. The goal: signal "built to operate at scale, in production" without
 * inventing numbers. Server Component.
 *
 * Wiring real values later is a one-liner per metric: give the matching entry a
 * `value` (e.g. from a future GET /metrics endpoint, or passed down as props
 * mirroring `DemoStat`). Until then the band renders the em dash, and the
 * "ready to stream" kicker makes that state read as intentional, not broken.
 */

interface InfraMetric {
  label: string;
  /** Real value once wired; `null` renders the honest "—" placeholder. */
  value: string | null;
}

const INFRA: InfraMetric[] = [
  { label: "Platform uptime", value: null },
  { label: "API requests", value: null },
  { label: "Markets settled", value: null },
  { label: "Active deployments", value: null },
];

export function InfraMetrics() {
  return (
    <div className="mb-10">
      <div className="mb-3 flex items-center gap-2">
        <span
          aria-hidden="true"
          className="h-1.5 w-1.5 rounded-full bg-brand-secondary shadow-[0_0_8px_var(--brand-secondary)]"
        />
        <span className="text-xs font-semibold uppercase tracking-[0.16em] text-subtle-foreground">
          Production infrastructure · ready to stream
        </span>
      </div>
      <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-border bg-border sm:grid-cols-4">
        {INFRA.map((m) => (
          <div key={m.label} className="flex flex-col gap-1 bg-card px-5 py-5">
            <dd className="font-display text-2xl font-semibold tabular-nums text-muted-foreground">
              {m.value ?? "—"}
            </dd>
            <dt className="text-xs font-medium uppercase tracking-wide text-subtle-foreground">
              {m.label}
            </dt>
          </div>
        ))}
      </dl>
    </div>
  );
}
