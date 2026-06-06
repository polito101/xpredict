/**
 * HeroVisual — the landing's signature node-graph (Phase 19).
 *
 * A glowing X "core" wired to three floating glass cards that illustrate the
 * platform's three capabilities at a glance: run your own market, integrate
 * external ones, and launch under your brand. The card contents are illustrative
 * marketing samples (not live data) — the real engine is shown in the demo
 * section below. Decorative; the meaningful copy lives in the hero text.
 * Server Component (composes the client XMark).
 */
import { XMark } from "@/components/brand/x-mark";

/** A tiny independent YES bar — the product's core gesture, in miniature. */
function MiniBar({ pct }: { pct: number }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
      <div
        className="h-full rounded-full bg-gradient-brand"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

function FloatCard({
  className,
  label,
  children,
}: {
  className?: string;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={`absolute w-48 rounded-2xl border border-border surface-glass p-3.5 shadow-pop ${className ?? ""}`}
    >
      <p className="mb-2 text-[0.65rem] font-semibold uppercase tracking-[0.14em] text-subtle-foreground">
        {label}
      </p>
      {children}
    </div>
  );
}

export function HeroVisual() {
  return (
    <div
      aria-hidden="true"
      className="relative mx-auto hidden aspect-square w-full max-w-md lg:block"
    >
      {/* Connector lines under everything. */}
      <svg
        viewBox="0 0 400 400"
        className="absolute inset-0 h-full w-full"
        fill="none"
      >
        <g
          stroke="color-mix(in oklab, var(--brand-primary) 45%, transparent)"
          strokeWidth="1.5"
          strokeDasharray="4 4"
        >
          <line x1="200" y1="200" x2="300" y2="86" />
          <line x1="200" y1="200" x2="96" y2="180" />
          <line x1="200" y1="200" x2="286" y2="316" />
        </g>
      </svg>

      {/* Core glow + X. */}
      <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2">
        <div className="absolute left-1/2 top-1/2 h-44 w-44 -translate-x-1/2 -translate-y-1/2 rounded-full bg-brand-primary/25 blur-3xl" />
        <div className="relative grid h-28 w-28 place-items-center rounded-3xl border border-brand-primary/30 surface-glass glow-brand">
          <XMark animated className="h-16 w-16" />
        </div>
      </div>

      {/* Your platform (top-right). */}
      <FloatCard label="Your platform" className="right-0 top-8">
        <p className="mb-2 truncate text-xs font-medium text-foreground">
          Will your team win?
        </p>
        <div className="flex items-center justify-between text-xs">
          <span className="font-semibold tabular-nums text-foreground">
            Yes 62%
          </span>
        </div>
        <div className="mt-1.5">
          <MiniBar pct={62} />
        </div>
      </FloatCard>

      {/* External markets (left). */}
      <FloatCard label="External markets" className="-left-2 top-1/3">
        <ul className="flex flex-col gap-2 text-xs">
          <li className="flex items-center justify-between gap-2">
            <span className="text-muted-foreground">Polymarket</span>
            <span className="font-semibold tabular-nums text-foreground">
              62%
            </span>
          </li>
          <li className="flex items-center justify-between gap-2">
            <span className="text-muted-foreground">Kalshi</span>
            <span className="font-semibold tabular-nums text-foreground">
              58%
            </span>
          </li>
        </ul>
      </FloatCard>

      {/* Your market (bottom-right). */}
      <FloatCard label="Your market" className="bottom-6 right-6">
        <p className="mb-2 truncate text-xs font-medium text-foreground">
          Ships in Q1?
        </p>
        <span className="text-xs font-semibold tabular-nums text-foreground">
          Yes 71%
        </span>
        <div className="mt-1.5">
          <MiniBar pct={71} />
        </div>
      </FloatCard>
    </div>
  );
}
