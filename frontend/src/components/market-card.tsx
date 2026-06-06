/**
 * MarketCard -- displays a single binary market in the catalog grid.
 *
 * Shows question, YES/NO odds bar, volume, deadline, and source badge.
 * Uses a stretched-link pattern: the question title contains a Link with
 * after:absolute after:inset-0 that covers the entire card, while the
 * SourceBadge anchor sits above via relative z-10 to avoid nested <a> tags.
 *
 * Server Component (no "use client").
 */
import Link from "next/link";
import {
  Card,
  CardHeader,
  CardContent,
  CardFooter,
} from "@/components/ui/card";
import { OddsDisplay } from "@/components/odds-display";
import { SourceBadge } from "@/components/source-badge";
import {
  formatVolume,
  formatDeadline,
  type MarketItem,
} from "@/lib/api";

interface MarketCardProps {
  market: MarketItem;
}

export function MarketCard({ market }: MarketCardProps) {
  // Compute YES/NO percentages from outcomes.
  // Gamma API returns title-case labels ("Yes"/"No"), so compare
  // case-insensitively. For non-binary markets, fall back to first outcome.
  const yesOutcome = market.outcomes.find(
    (o) => o.label.toUpperCase() === "YES"
  );
  const primaryOutcome = yesOutcome ?? market.outcomes[0];
  const primaryPercent = primaryOutcome
    ? Math.round(parseFloat(primaryOutcome.current_odds) * 100)
    : 50;
  const secondaryPercent = 100 - primaryPercent;

  const deadline = formatDeadline(market.deadline);
  const isEnded = deadline === "Ended";

  return (
    <Card className="group relative flex flex-col overflow-hidden transition-all duration-300 hover:-translate-y-1 hover:border-brand-primary/40 hover:shadow-pop focus-within:ring-2 focus-within:ring-brand-primary/60">
      {/* Hover glow wash from the top edge. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 -top-px h-px bg-gradient-brand opacity-0 transition-opacity duration-300 group-hover:opacity-100"
      />
      <CardHeader className="flex-row items-start justify-between gap-2 p-5 pb-3">
        {market.category ? (
          <span className="truncate rounded-full bg-muted px-2.5 py-0.5 text-[0.7rem] font-medium uppercase tracking-wide text-muted-foreground">
            {market.category}
          </span>
        ) : (
          <span />
        )}
        <div className="relative z-10 shrink-0">
          <SourceBadge source={market.source} sourceUrl={market.source_url} />
        </div>
      </CardHeader>
      <CardContent className="flex-1 p-5 py-0">
        <h3 className="text-[0.95rem] font-semibold leading-snug line-clamp-3 text-foreground">
          <Link
            href={`/markets/${market.slug}`}
            className="outline-none after:absolute after:inset-0"
            aria-label={market.question}
          >
            {market.question}
          </Link>
        </h3>
      </CardContent>
      <CardFooter className="mt-4 flex-col items-stretch gap-3 p-5 pt-0">
        <OddsDisplay yes={primaryPercent} no={secondaryPercent} />
        <div className="flex items-center justify-between border-t border-border/60 pt-3 text-xs text-muted-foreground">
          <span className="font-medium text-foreground/80">
            {formatVolume(market.volume)}{" "}
            <span className="font-normal text-subtle-foreground">vol</span>
          </span>
          <span className={isEnded ? "text-subtle-foreground" : undefined}>
            {deadline}
          </span>
        </div>
      </CardFooter>
    </Card>
  );
}
