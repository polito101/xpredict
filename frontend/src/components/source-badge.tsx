/**
 * SourceBadge -- displays market source as a small chip.
 *
 * "Polymarket" badge links to the source URL (opens in new tab).
 * "House" badge has no link.
 *
 * Client Component: onClick stopPropagation on the Polymarket anchor
 * prevents the parent card Link from navigating when clicking the badge.
 */
"use client";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface SourceBadgeProps {
  source: string;
  sourceUrl?: string | null;
}

export function SourceBadge({ source, sourceUrl }: SourceBadgeProps) {
  if (source === "POLYMARKET" && sourceUrl) {
    return (
      <a
        href={sourceUrl}
        target="_blank"
        rel="noopener noreferrer"
        aria-label="View on Polymarket (opens in new tab)"
        onClick={(e) => e.stopPropagation()}
      >
        <Badge
          variant="secondary"
          className={cn(
            "gap-1 transition-colors hover:text-foreground",
            "text-xs",
          )}
        >
          Polymarket
        </Badge>
      </a>
    );
  }

  if (source === "POLYMARKET") {
    return (
      <Badge variant="secondary" className="text-xs">
        Polymarket
      </Badge>
    );
  }

  if (source === "HOUSE") {
    return (
      <Badge
        className={cn(
          "border-brand-primary/30 bg-brand-primary/15 text-brand-primary",
          "text-xs",
        )}
      >
        House
      </Badge>
    );
  }

  // Fallback for unknown sources
  return (
    <Badge variant="outline" className="text-xs">
      {source}
    </Badge>
  );
}
