/**
 * OddsDisplay -- shows YES/NO percentages with a proportional odds bar.
 *
 * Server Component (no "use client").
 */

interface OddsDisplayProps {
  yes: number;
  no: number;
}

export function OddsDisplay({ yes, no }: OddsDisplayProps) {
  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between">
        <div>
          <span className="text-xs uppercase tracking-wide text-zinc-500">
            YES
          </span>{" "}
          <span className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
            {yes}%
          </span>
        </div>
        <div>
          <span className="text-xs uppercase tracking-wide text-zinc-500">
            NO
          </span>{" "}
          <span className="text-sm font-normal text-zinc-500">
            {no}%
          </span>
        </div>
      </div>
      <div
        className="flex h-1.5 w-full overflow-hidden rounded-full"
        role="img"
        aria-label={`YES ${yes}%, NO ${no}%`}
      >
        <div
          className="bg-brand-primary"
          style={{ width: `${yes}%` }}
        />
        <div
          className="bg-zinc-200 dark:bg-zinc-700"
          style={{ width: `${no}%` }}
        />
      </div>
    </div>
  );
}
