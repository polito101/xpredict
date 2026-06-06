"use client";

import "./globals.css";

/**
 * Global error boundary (v1.1 Fase C) — the last-resort fallback when the root
 * layout itself throws. It REPLACES the layout, so it must render its own
 * <html>/<body>; globals.css supplies the brand tokens + Tailwind utilities.
 * (Sentry's Next.js instrumentation still captures the error separately.)
 */
export default function GlobalError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="flex min-h-full items-center justify-center bg-background text-foreground">
        <main className="flex w-full max-w-md flex-col items-center gap-4 px-4 py-16 text-center">
          <h1 className="text-2xl font-semibold tracking-tight">
            Something went wrong
          </h1>
          <p className="text-sm text-muted-foreground">
            An unexpected error occurred on our end. Please try again.
          </p>
          <button
            type="button"
            onClick={() => reset()}
            className="inline-flex h-10 items-center justify-center rounded-xl bg-brand-primary px-4 text-sm font-medium text-brand-primary-foreground transition-all hover:brightness-110"
          >
            Try again
          </button>
        </main>
      </body>
    </html>
  );
}
