/**
 * CatalogControls — the browse filter island (BRW-01..04).
 *
 * A `"use client"` controls bar that drives the URL searchParams: a debounced
 * search input, a category chip row (only the provided non-empty categories +
 * "All"), and status + sort `Select`s. The Server Component homepage re-fetches
 * the catalog on every URL change (`cache:"no-store"`) — so filters are
 * shareable and SSR-fresh with no client data store. White-label: the active
 * category chip uses the brand token.
 */
"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { Search } from "lucide-react";

import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

interface CatalogControlsProps {
  categories: string[];
  q?: string;
  category?: string;
  status?: string;
  sort?: string;
}

const STATUS_OPTIONS = [
  { value: "all", label: "All statuses" },
  { value: "open", label: "Open" },
  { value: "closing_soon", label: "Closing soon" },
  { value: "resolved", label: "Resolved" },
];

const SORT_OPTIONS = [
  { value: "volume", label: "Volume" },
  { value: "closing_soonest", label: "Closing soonest" },
  { value: "newest", label: "Newest" },
];

const SEARCH_DEBOUNCE_MS = 300;

export function CatalogControls({
  categories,
  q,
  category,
  status,
  sort,
}: CatalogControlsProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [searchValue, setSearchValue] = useState(q ?? "");
  const [syncedQ, setSyncedQ] = useState(q ?? "");
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Sync the input when the URL `q` changes externally (browser back/forward) —
  // the React "adjust state during render" pattern (no effect, so no cascading-
  // render lint). During typing the URL lags (debounced), so this no-ops.
  if ((q ?? "") !== syncedQ) {
    setSyncedQ(q ?? "");
    setSearchValue(q ?? "");
  }

  // Clear a pending debounce on unmount.
  useEffect(
    () => () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    },
    [],
  );

  function setParam(key: string, value: string | null) {
    const params = new URLSearchParams(searchParams?.toString() ?? "");
    if (value && value !== "all") {
      params.set(key, value);
    } else {
      params.delete(key);
    }
    const qs = params.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname);
  }

  function onSearchChange(value: string) {
    setSearchValue(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setParam("q", value.trim() || null);
    }, SEARCH_DEBOUNCE_MS);
  }

  return (
    <div className="mb-8 flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-4">
        <div className="relative w-full sm:w-72">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-subtle-foreground"
            aria-hidden="true"
          />
          <Input
            type="search"
            value={searchValue}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search markets…"
            aria-label="Search markets"
            className="pl-9"
          />
        </div>

        <Select
          value={status ?? "all"}
          onValueChange={(v) => setParam("status", v)}
        >
          <SelectTrigger className="w-44" aria-label="Filter by status">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {STATUS_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={sort ?? "volume"} onValueChange={(v) => setParam("sort", v)}>
          <SelectTrigger className="w-44" aria-label="Sort">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SORT_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {categories.length > 0 && (
        <div
          className="flex gap-2 overflow-x-auto pb-1"
          role="group"
          aria-label="Filter by category"
        >
          <CategoryChip
            label="All"
            active={!category}
            onClick={() => setParam("category", null)}
          />
          {categories.map((c) => (
            <CategoryChip
              key={c}
              label={c}
              active={category === c}
              onClick={() => setParam("category", c)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function CategoryChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "shrink-0 rounded-full border px-3.5 py-1.5 text-sm font-medium transition-all",
        active
          ? "border-transparent bg-brand-primary text-brand-primary-foreground glow-brand-sm"
          : "border-border bg-muted/60 text-muted-foreground hover:border-border-strong hover:text-foreground",
      )}
    >
      {label}
    </button>
  );
}
