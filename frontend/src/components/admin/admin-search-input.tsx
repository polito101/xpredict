/**
 * Plan 08-03 — Debounced admin search input.
 *
 * 300ms debounce per UI-SPEC §Interaction Contract. Fires `onChange` with the
 * debounced value (caller resets pagination to page 1). `Search` lucide icon
 * inside the input; `min-w-[280px]` per UI-SPEC.
 */
"use client";

import * as React from "react";
import { Search } from "lucide-react";

import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export function AdminSearchInput({
  value,
  onChange,
  placeholder,
  ariaLabel,
  debounceMs = 300,
  className,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  ariaLabel: string;
  debounceMs?: number;
  className?: string;
}) {
  // Local input state so typing is responsive; the debounced value is what
  // bubbles up to trigger a server refetch.
  const [local, setLocal] = React.useState(value);

  // Keep local in sync when the parent resets the value externally.
  React.useEffect(() => {
    setLocal(value);
  }, [value]);

  React.useEffect(() => {
    if (local === value) return;
    const t = setTimeout(() => onChange(local), debounceMs);
    return () => clearTimeout(t);
    // onChange is stable enough for this debounce; intentionally omit it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [local, debounceMs]);

  return (
    <div className={cn("relative min-w-[280px]", className)}>
      <Search
        className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400"
        aria-hidden="true"
      />
      <Input
        type="search"
        aria-label={ariaLabel}
        placeholder={placeholder}
        value={local}
        onChange={(e) => setLocal(e.target.value)}
        className="pl-9"
      />
    </div>
  );
}
