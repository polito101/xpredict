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
    classes:
      "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
  },
  partially_resolved: {
    label: "Partially resolved",
    classes:
      "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  },
  resolved: {
    label: "Resolved",
    classes: "bg-zinc-900 text-zinc-50 dark:bg-zinc-50 dark:text-zinc-900",
  },
  void: {
    label: "Void",
    classes: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300",
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
    classes: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300",
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
