/**
 * Pillars — the three core platform capabilities (Phase 19 positioning).
 *
 * XPredict is a complete platform, not just a trading destination: you can RUN
 * native markets, INTEGRATE external ones, and LAUNCH your own. This section
 * gives those three capabilities equal weight. Server Component.
 */
import { Activity, Globe, Rocket } from "lucide-react";

const PILLARS = [
  {
    icon: Activity,
    kicker: "Run",
    title: "Native markets",
    body: "Operate XPredict's own markets — binary YES/NO and multi-outcome events — with live odds, a play-money wallet, and transparent settlement.",
  },
  {
    icon: Globe,
    kicker: "Integrate",
    title: "External markets",
    body: "Mirror live markets from sources like Polymarket and surface them next to your own, in one curated, searchable catalog.",
  },
  {
    icon: Rocket,
    kicker: "Launch",
    title: "Your own markets",
    body: "Create and deploy your own prediction markets through an API-first backend and a white-label UI — your colors, your logo, your rules.",
  },
] as const;

export function Pillars() {
  return (
    <section className="mx-auto w-full max-w-6xl px-4 py-16 sm:px-6 sm:py-20">
      <div className="mb-10 max-w-2xl">
        <h2 className="font-display text-3xl font-semibold tracking-tight sm:text-4xl">
          One platform, three ways to play.
        </h2>
        <p className="mt-3 text-base text-muted-foreground">
          Use XPredict as a destination, a distribution channel, or a foundation
          — or all three at once.
        </p>
      </div>

      <div className="grid gap-5 md:grid-cols-3">
        {PILLARS.map(({ icon: Icon, kicker, title, body }) => (
          <div
            key={kicker}
            className="group relative flex flex-col gap-4 rounded-2xl border border-border bg-card p-6 transition-all duration-300 hover:-translate-y-1 hover:border-brand-primary/40 hover:shadow-pop"
          >
            <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-brand-primary/25 bg-brand-primary/10 text-brand-primary">
              <Icon className="h-5 w-5" aria-hidden="true" />
            </div>
            <div>
              <span className="text-xs font-semibold uppercase tracking-[0.16em] text-brand-primary">
                {kicker}
              </span>
              <h3 className="mt-1 font-display text-xl font-semibold tracking-tight">
                {title}
              </h3>
            </div>
            <p className="text-sm leading-relaxed text-muted-foreground">
              {body}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}
