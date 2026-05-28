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
          <span className="text-sm font-normal text-emerald-700 dark:text-emerald-400">
            {yes}%
          </span>
        </div>
        <div>
          <span className="text-xs uppercase tracking-wide text-zinc-500">
            NO
          </span>{" "}
          <span className="text-sm font-normal text-rose-700 dark:text-rose-400">
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
          className="bg-emerald-500"
          style={{ width: `${yes}%` }}
        />
        <div
          className="bg-rose-500"
          style={{ width: `${no}%` }}
        />
      </div>
    </div>
  );
}
