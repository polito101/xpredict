/**
 * OddsDisplay -- shows YES/NO percentages with a proportional odds bar.
 *
 * The recurring "odds" gesture of the product. YES carries the electric brand
 * gradient with a soft glow; NO is the muted complement. Binary split (YES + its
 * own NO) — the two segments sum to 100, which is correct for a binary market.
 *
 * Server Component (no "use client"). `role="img"` + the exact aria-label format
 * `"YES {yes}%, NO {no}%"` are part of the test/accessibility contract.
 */

interface OddsDisplayProps {
  yes: number;
  no: number;
}

export function OddsDisplay({ yes, no }: OddsDisplayProps) {
  return (
    <div className="space-y-2.5">
      <div className="flex items-baseline justify-between">
        <div className="flex items-baseline gap-1.5">
          <span className="text-[0.7rem] font-medium uppercase tracking-wide text-subtle-foreground">
            YES
          </span>
          <span className="font-display text-lg font-semibold tabular-nums text-foreground">
            {yes}%
          </span>
        </div>
        <div className="flex items-baseline gap-1.5">
          <span className="text-[0.7rem] font-medium uppercase tracking-wide text-subtle-foreground">
            NO
          </span>
          <span className="font-display text-lg font-semibold tabular-nums text-muted-foreground">
            {no}%
          </span>
        </div>
      </div>
      <div
        className="flex h-2 w-full overflow-hidden rounded-full bg-muted"
        role="img"
        aria-label={`YES ${yes}%, NO ${no}%`}
      >
        <div
          className="bg-gradient-brand glow-brand-sm transition-[width] duration-500"
          style={{ width: `${yes}%` }}
        />
      </div>
    </div>
  );
}
