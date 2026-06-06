/**
 * CapabilityGrid — the six platform capabilities (Phase 19 positioning).
 *
 * XPrediction is more than a market or an API: it is a prediction-market
 * Platform + Infrastructure + White-label + API + Integrations + Markets (own &
 * external). These six map to real, shipping capabilities in the codebase — no
 * vaporware. Server Component.
 */
import {
  Boxes,
  Code2,
  Globe,
  Layers,
  Palette,
  ShieldCheck,
} from "lucide-react";

const CAPS = [
  {
    icon: Layers,
    title: "Prediction-market platform",
    body: "Binary markets and multi-outcome events with a curated, typed catalog — the full market engine, ready to run on day one.",
  },
  {
    icon: ShieldCheck,
    title: "Prediction infrastructure",
    body: "ACID settlement on a double-entry ledger plus real-time odds over WebSockets, on Postgres · Redis · Celery. Balances never drift.",
  },
  {
    icon: Palette,
    title: "White-label",
    body: "Your colors, logo and copy — injected at runtime from the admin. Re-skin the whole experience instantly, with no rebuild or redeploy.",
  },
  {
    icon: Code2,
    title: "API-first",
    body: "A typed FastAPI core — markets, wallets, bets, settlement, branding — built to integrate into your product, not to lock you in.",
  },
  {
    icon: Globe,
    title: "Integrations",
    body: "Mirror external markets from sources like Polymarket and bring partner liquidity and data into a single, coherent surface.",
  },
  {
    icon: Boxes,
    title: "Own & external markets",
    body: "Run your own house markets and external ones side by side, in one catalog your audience browses — you curate what they see.",
  },
] as const;

export function CapabilityGrid() {
  return (
    <section className="border-y border-border bg-surface/40">
      <div className="mx-auto w-full max-w-6xl px-4 py-16 sm:px-6 sm:py-20">
        <div className="mb-10 max-w-2xl">
          <h2 className="font-display text-3xl font-semibold tracking-tight sm:text-4xl">
            Six capabilities, one platform.
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
