/**
 * MarketCard -- displays a single market in the grid.
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
    <Card className="relative hover:shadow-md transition-shadow focus-within:ring-2 focus-within:ring-zinc-950 focus-within:ring-offset-2 group">
      <CardHeader className="p-6 pb-2">
        <h3 className="text-base font-semibold leading-snug line-clamp-3">
          <Link
            href={`/markets/${market.slug}`}
            className="after:absolute after:inset-0"
            aria-label={market.question}
          >
            {market.question}
          </Link>
        </h3>
      </CardHeader>
      <CardContent className="p-6 pt-0">
        <OddsDisplay yes={primaryPercent} no={secondaryPercent} />
      </CardContent>
      <CardFooter className="p-6 pt-0 flex justify-between items-end gap-2">
        <div className="min-w-0 truncate text-sm text-zinc-500">
          <span>Vol: {formatVolume(market.volume)}</span>
          <span className="mx-2">|</span>
          <span className={isEnded ? "text-zinc-400" : undefined}>
            {deadline}
          </span>
        </div>
        <div className="relative z-10 shrink-0">
          <SourceBadge
            source={market.source}
            sourceUrl={market.source_url}
          />
        </div>
      </CardFooter>
    </Card>
  );
}
