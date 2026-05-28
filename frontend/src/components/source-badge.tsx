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
  if (source === "POLYMARKET") {
    return (
      <a
        href={sourceUrl ?? "#"}
        target="_blank"
        rel="noopener noreferrer"
        aria-label="View on Polymarket (opens in new tab)"
        onClick={(e) => e.stopPropagation()}
      >
        <Badge
          variant="secondary"
          className={cn(
            "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
            "text-xs",
          )}
        >
          Polymarket
        </Badge>
      </a>
    );
  }

  if (source === "HOUSE") {
    return (
      <Badge
        className={cn(
          "bg-zinc-900 text-zinc-50 dark:bg-zinc-100 dark:text-zinc-900",
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
