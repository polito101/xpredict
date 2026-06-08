/**
 * CapabilityGrid — the six platform capabilities (Phase 19 → Quality Pass).
 *
 * XPrediction is more than a market or an API: it is a prediction-market
 * Platform + White-label + Infrastructure + API + Integrations + Markets (own &
 * external). These six map to real, shipping capabilities in the codebase — no
 * vaporware. Server Component.
 *
 * Quality Pass — visual hierarchy: the six cards used to carry identical weight,
 * so the eye had no entry point. The grid stays a clean 3×2 (no col-spans, no
 * holes), but the lead capability — "Prediction-market platform", what the buyer
 * actually purchases — is given a restrained "core" treatment (brand border +
 * soft glow + gradient icon + kicker + larger title). The rest are supporting
 * enablers. All six share one consistent hover (lift + brand border) so the
 * section reads as one coherent system.
 */
import {
  Boxes,
  Code2,
  Globe,
  Layers,
  Palette,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";

type Cap = {
  icon: LucideIcon;
  title: string;
  body: string;
  /** The lead capability — rendered with the elevated "core" treatment. */
  featured?: boolean;
};

// Ordered by buyer value: the platform itself first (what they buy), then the
// enablers that make it sellable, then the reach.
const CAPS: Cap[] = [
  {
    icon: Layers,
    title: "Prediction-market platform",
    body: "Binary markets and multi-outcome events with a curated, typed catalog — the full market engine, ready to run on day one.",
    featured: true,
  },
  {
    icon: Palette,
    title: "White-label",
    body: "Your colors, logo and copy — injected at runtime from the admin. Re-skin the whole experience instantly, with no rebuild or redeploy.",
  },
  {
    icon: ShieldCheck,
    title: "Prediction infrastructure",
    body: "ACID settlement on a double-entry ledger plus real-time odds over WebSockets, on Postgres · Redis · Celery. Balances never drift.",
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
];

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
          {CAPS.map(({ icon: Icon, title, body, featured }) =>
            featured ? (
              <div
                key={title}
                className="group relative overflow-hidden rounded-2xl border border-brand-primary/30 bg-card p-6 shadow-[0_0_0_1px_color-mix(in_oklab,var(--brand-primary)_14%,transparent),0_22px_56px_-26px_color-mix(in_oklab,var(--brand-primary)_60%,transparent)] transition-all duration-300 hover:-translate-y-0.5 hover:border-brand-primary/50"
              >
                {/* Restrained brand wash — depth, not decoration. */}
                <div
                  aria-hidden="true"
                  className="pointer-events-none absolute inset-0 opacity-70"
                  style={{
                    backgroundImage:
                      "radial-gradient(30rem 14rem at 0% 0%, color-mix(in oklab, var(--brand-primary) 13%, transparent), transparent 72%)",
                  }}
                />
                <div className="relative flex flex-col gap-3">
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-brand text-brand-primary-foreground glow-brand-sm">
                    <Icon className="h-5 w-5" aria-hidden="true" />
                  </div>
                  <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-brand-primary">
                    Platform core
                  </span>
                  <h3 className="font-display text-lg font-semibold tracking-tight">
                    {title}
                  </h3>
                  <p className="text-sm leading-relaxed text-muted-foreground">
                    {body}
                  </p>
                </div>
              </div>
            ) : (
              <div
                key={title}
                className="group flex flex-col gap-3 rounded-2xl border border-border bg-card p-6 transition-all duration-300 hover:-translate-y-0.5 hover:border-brand-primary/40 hover:shadow-pop"
              >
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-muted text-brand-primary">
                  <Icon className="h-5 w-5" aria-hidden="true" />
                </div>
                <h3 className="text-base font-semibold tracking-tight">{title}</h3>
                <p className="text-sm leading-relaxed text-muted-foreground">
                  {body}
                </p>
              </div>
            ),
          )}
        </div>
      </div>
    </section>
  );
}
