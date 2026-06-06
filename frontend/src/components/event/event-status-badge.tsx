/**
 * EventStatusBadge — the derived event status chip (open / partially_resolved /
 * resolved / void). The event has no stored status; this is the read-projection
 * surfaced on the event detail + admin manage pages. Follows the locked chip
 * convention (`px-2.5 py-0.5 text-xs font-semibold`, `aria-label="Status: …"`).
 */
import { cn } from "@/lib/utils";

const EVENT_STATUS: Record<string, { label: string; classes: string }> = {
  open: {
    label: "Open",
    classes: "bg-emerald-500/15 text-emerald-400",
  },
  partially_resolved: {
    label: "Partially resolved",
    classes: "bg-amber-500/15 text-amber-400",
  },
  resolved: {
    label: "Resolved",
    classes: "bg-foreground/10 text-foreground",
  },
  void: {
    label: "Void",
    classes: "bg-muted text-subtle-foreground",
  },
};

export function EventStatusBadge({
  status,
  className,
}: {
  status: string;
  className?: string;
}) {
  const s = EVENT_STATUS[status] ?? {
    label: status,
    classes: "bg-muted text-muted-foreground",
  };
  return (
    <span
      aria-label={`Status: ${s.label}`}
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold",
        s.classes,
        className,
      )}
    >
      {s.label}
    </span>
  );
}
