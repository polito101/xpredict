/**
 * DemoShowcase — "the engine, running" (Phase 19 landing).
 *
 * Frames the live app as a DEMO/capability of the platform: this very deployment
 * is XPredict running as its own tenant. Shows real platform stats derived from
 * the PUBLIC catalog (no new API) + a few featured markets/events (the premium
 * cards, reused verbatim), then a CTA into the demo (`/markets`, gated → login).
 * Server Component.
 */
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { MarketCard } from "@/components/market-card";
import { EventCard } from "@/components/catalog/event-card";
import { catalogMarketToMarketItem, type CatalogItem } from "@/lib/catalog";

export interface DemoStat {
  label: string;
  value: string;
}

export function DemoShowcase({
  featured,
  stats,
}: {
  featured: CatalogItem[];
  stats: DemoStat[];
}) {
  return (
    <section
      id="demo"
      className="scroll-mt-20 border-t border-border bg-surface/40"
    >
      <div className="mx-auto w-full max-w-6xl px-4 py-16 sm:px-6 sm:py-20">
        <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div className="max-w-2xl">
            <span className="text-xs font-semibold uppercase tracking-[0.16em] text-brand-primary">
              The platform, live
            </span>
            <h2 className="mt-1 font-display text-3xl font-semibold tracking-tight sm:text-4xl">
              See the engine running.
            </h2>
            <p className="mt-3 text-base text-muted-foreground">
              This site is XPrediction running as its own tenant. Your deployment
              works the same — it just looks like you.
            </p>
          </div>
          <Button asChild size="lg" className="shrink-0 self-start sm:self-auto">
            <Link href="/markets">Explore the demo</Link>
          </Button>
        </div>

        {stats.length > 0 && (
          <dl className="mb-10 grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-border bg-border sm:grid-cols-4">
            {stats.map((s) => (
              <div
                key={s.label}
                className="flex flex-col gap-1 bg-card px-5 py-5"
              >
                <dd className="font-display text-2xl font-semibold tabular-nums">
                  {s.value}
                </dd>
                <dt className="text-xs font-medium uppercase tracking-wide text-subtle-foreground">
                  {s.label}
                </dt>
              </div>
            ))}
          </dl>
        )}

        {featured.length > 0 && (
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {featured.map((item) =>
              item.type === "event" ? (
                <EventCard key={item.id} event={item} />
              ) : (
                <MarketCard
                  key={item.id}
                  market={catalogMarketToMarketItem(item)}
                />
              ),
            )}
          </div>
        )}
      </div>
    </section>
  );
}
