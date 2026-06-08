/**
 * HowItWorks — the operator's three-step path from brand to live markets.
 * Server Component (Phase 19 landing).
 */
const STEPS = [
  {
    n: "01",
    title: "Brand it",
    body: "Set your palette, logo and voice in the admin. Players re-skin to your identity on their next page load — no deploy.",
  },
  {
    n: "02",
    title: "Launch markets",
    body: "Spin up your own house markets and mirror live external ones. Curate a credible, searchable catalog for your audience.",
  },
  {
    n: "03",
    title: "Operate & scale",
    body: "Settle transparently, manage members and resolutions, and watch the numbers — on infrastructure built to grow with you.",
  },
] as const;

export function HowItWorks() {
  return (
    <section className="mx-auto w-full max-w-6xl px-4 py-16 sm:px-6 sm:py-20">
      <div className="mb-10 max-w-2xl">
        <h2 className="font-display text-3xl font-semibold tracking-tight sm:text-4xl">
          Live in three steps.
        </h2>
        <p className="mt-3 text-base text-muted-foreground">
          From your brand to your first resolved market — without building the
          hard parts yourself.
        </p>
      </div>

      <ol className="grid gap-5 md:grid-cols-3">
        {STEPS.map(({ n, title, body }) => (
          <li
            key={n}
            className="group relative flex flex-col gap-3 rounded-2xl border border-border bg-card p-6 transition-all duration-300 hover:-translate-y-0.5 hover:border-brand-primary/40 hover:shadow-pop"
          >
            <span className="font-display text-3xl font-semibold text-gradient-brand">
              {n}
            </span>
            <h3 className="text-lg font-semibold tracking-tight">{title}</h3>
            <p className="text-sm leading-relaxed text-muted-foreground">
              {body}
            </p>
          </li>
        ))}
      </ol>
    </section>
  );
}
