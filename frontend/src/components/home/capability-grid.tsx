/**
 * CapabilityGrid — the platform's building blocks (Phase 19).
 *
 * Six real capabilities of the XPredict engine (every one ships in the codebase
 * — no vaporware): white-label theming, the market engine, settlement, real-time
 * odds, the API-first backend, and the operator backoffice. Server Component.
 */
import {
  Activity,
  BarChart3,
  Code2,
  Layers,
  Palette,
  ShieldCheck,
} from "lucide-react";

const CAPS = [
  {
    icon: Palette,
    title: "White-label by default",
    body: "Your colors, logo and copy — injected at runtime from the admin. Re-skin the whole experience instantly, with no rebuild or redeploy.",
  },
  {
    icon: Layers,
    title: "Prediction-market engine",
    body: "Binary markets and multi-outcome events, with a typed catalog operators curate. Independent per-outcome odds, never a faked distribution.",
  },
  {
    icon: ShieldCheck,
    title: "Transparent settlement",
    body: "ACID settlement on a double-entry ledger. Every payout is auditable, balances never drift, and resolutions carry public justification.",
  },
  {
    icon: Activity,
    title: "Real-time odds",
    body: "Live probability streaming over WebSockets, backed by Redis pub/sub — markets that move the moment opinion does.",
  },
  {
    icon: Code2,
    title: "API-first backend",
    body: "A typed FastAPI core — markets, wallets, bets, settlement, branding — designed to integrate into your product, not to lock you in.",
  },
  {
    icon: BarChart3,
    title: "Operator backoffice",
    body: "A full admin & CRM: manage members, create and resolve markets, set your branding, and watch volume, DAU and house P&L.",
  },
] as const;

export function CapabilityGrid() {
  return (
    <section className="border-y border-border bg-surface/40">
      <div className="mx-auto w-full max-w-6xl px-4 py-16 sm:px-6 sm:py-20">
        <div className="mb-10 max-w-2xl">
          <h2 className="font-display text-3xl font-semibold tracking-tight sm:text-4xl">
            Production-grade building blocks.
          </h2>
          <p className="mt-3 text-base text-muted-foreground">
            Everything you need to run prediction markets as your own product —
            already built, tested, and shipping.
          </p>
        </div>

        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {CAPS.map(({ icon: Icon, title, body }) => (
            <div
              key={title}
              className="flex flex-col gap-3 rounded-2xl border border-border bg-card p-6 transition-colors hover:border-border-strong"
            >
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-muted text-brand-primary">
                <Icon className="h-5 w-5" aria-hidden="true" />
              </div>
              <h3 className="text-base font-semibold tracking-tight">{title}</h3>
              <p className="text-sm leading-relaxed text-muted-foreground">
                {body}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
