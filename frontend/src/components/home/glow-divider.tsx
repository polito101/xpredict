/**
 * GlowDivider — a hairline section separator with a soft brand glow at its
 * centre, used between landing sections that meet on the open canvas (i.e. where
 * there is no surface-band border doing the job already). Decorative only
 * (`aria-hidden`); the brand color comes from the runtime token, so it re-skins
 * with the operator palette. Server Component.
 */
export function GlowDivider() {
  return (
    <div aria-hidden="true" className="mx-auto w-full max-w-6xl px-4 sm:px-6">
      <div className="relative h-px w-full bg-gradient-to-r from-transparent via-border to-transparent">
        {/* A crisp brand-lit centre segment… */}
        <div className="absolute left-1/2 top-0 h-px w-1/2 -translate-x-1/2 bg-gradient-to-r from-transparent via-brand-secondary to-transparent" />
        {/* …wrapped in a soft glow halo. */}
        <div className="absolute left-1/2 top-1/2 h-2 w-44 -translate-x-1/2 -translate-y-1/2 rounded-full bg-gradient-to-r from-transparent via-brand-secondary/60 to-transparent blur-md" />
      </div>
    </div>
  );
}
