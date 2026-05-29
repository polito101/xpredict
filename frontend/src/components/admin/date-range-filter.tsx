/**
 * Plan 08-03 — Date range filter (From / To).
 *
 * Two `type="date"` inputs labeled "From" / "To" per UI-SPEC. Fires `onChange`
 * with the `{ from, to }` pair (caller maps these to signup_after /
 * signup_before, or date_from / date_to for the audit log).
 */
"use client";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export type DateRange = { from: string; to: string };

export function DateRangeFilter({
  value,
  onChange,
}: {
  value: DateRange;
  onChange: (value: DateRange) => void;
}) {
  return (
    <div className="flex items-end gap-3">
      <div className="flex flex-col gap-1">
        <Label
          htmlFor="date-range-from"
          className="text-xs font-medium text-zinc-500"
        >
          From
        </Label>
        <Input
          id="date-range-from"
          type="date"
          value={value.from}
          onChange={(e) => onChange({ ...value, from: e.target.value })}
          className="w-[160px]"
        />
      </div>
      <div className="flex flex-col gap-1">
        <Label
          htmlFor="date-range-to"
          className="text-xs font-medium text-zinc-500"
        >
          To
        </Label>
        <Input
          id="date-range-to"
          type="date"
          value={value.to}
          onChange={(e) => onChange({ ...value, to: e.target.value })}
          className="w-[160px]"
        />
      </div>
    </div>
  );
}
