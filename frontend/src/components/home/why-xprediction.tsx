/**
 * WhyXPrediction — the "why choose us" section (infra-company refinement).
 *
 * Pillars says what you can do; CapabilityGrid says what's built; this says WHY a
 * serious team builds on XPrediction — six concrete advantages, not vague
 * marketing. Intentionally lighter than the bordered card sections (clean icon +
 * title + line, generously spaced) to vary the page rhythm, at Stripe/Vercel
 * altitude. Server Component.
 */
import {
  Rocket,
  Palette,
  Boxes,
  Activity,
  Terminal,
  Gauge,
  type LucideIcon,
} from "lucide-react";

type Reason = { icon: LucideIcon; title: string; body: string };

const REASONS: Reason[] = [
  {
    icon: Rocket,
    title: "Launch faster",
    body: "Skip months of engineering — the market engine, wallet and settlement run on day one.",
  },
  {
    icon: Palette,
    title: "White-label from day one",
    body: "Your brand, colors and domain across the whole experience, changed at runtime — no rebuild.",
  },
  {
    icon: Boxes,
    title: "Native + external markets",
    body: "Run your own house markets and mirror external ones in a single, curated catalog.",
  },
  {
    icon: Activity,
    title: "Real-time infrastructure",
    body: "Live odds and money-safe settlement that stay consistent under real load.",
  },
  {
    icon: Terminal,
    title: "API-first architecture",
    body: "A typed core designed to drop into your product and your stack — built not to lock you in.",
  },
  {
    icon: Gauge,
    title: "Built to scale",
    body: "Production-grade infrastructure that grows from your first market to your busiest day.",
  },
];

export function WhyXPrediction() {
  return (
    <section
      id="why"
      className="mx-auto w-full max-w-6xl scroll-mt-20 px-4 py-16 sm:px-6 sm:py-20"
    >
      <div className="mb-10 max-w-2xl">
        <span className="text-xs font-semibold uppercase tracking-[0.16em] text-brand-primary">
          Why XPrediction
        </span>
        <h2 className="mt-1 font-display text-3xl font-semibold tracking-tight sm:text-4xl">
          The infrastructure teams choose to build on.
        </h2>
        <p className="mt-3 text-base text-muted-foreground">
          Not a template, not a black box — the concrete reasons serious teams run
          their markets on XPrediction.
        </p>
      </div>

      <div className="grid gap-x-8 gap-y-10 sm:grid-cols-2 lg:grid-cols-3">
        {REASONS.map(({ icon: Icon, title, body }) => (
          <div key={title} className="flex flex-col gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-lg border border-brand-primary/20 bg-brand-primary/10 text-brand-primary">
              <Icon className="h-5 w-5" aria-hidden="true" strokeWidth={1.75} />
            </span>
            <h3 className="font-display text-lg font-semibold tracking-tight">
              {title}
            </h3>
            <p className="text-sm leading-relaxed text-muted-foreground">{body}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
