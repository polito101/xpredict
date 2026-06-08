/**
 * LandingCta — the closing narrative band (infra-company refinement).
 *
 * The page's final beat: it restates the whole promise (run native · integrate
 * external · launch under your brand) and closes on self-serve ACTION CTAs
 * (create an account, explore the platform) — distinct from the "Get a demo"
 * section's sales conversation so the ending doesn't read as a repeated CTA.
 * Server Component (composes the client Spark).
 */
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Spark } from "@/components/brand/spark";

const PROMISE = [
  "Run native markets",
  "Integrate external liquidity",
  "Launch under your own brand",
] as const;

export function LandingCta() {
  return (
    <section className="mx-auto w-full max-w-6xl px-4 pb-24 pt-4 sm:px-6">
      <div className="relative overflow-hidden rounded-3xl border border-border bg-card px-6 py-16 text-center sm:px-12">
        {/* Brand glow flourish. */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 opacity-60"
          style={{
            backgroundImage:
              "radial-gradient(40rem 20rem at 50% -20%, color-mix(in oklab, var(--brand-primary) 25%, transparent), transparent 70%)",
          }}
        />
        <div className="relative flex flex-col items-center gap-6">
          <Spark className="h-8 w-8" />
          <h2 className="max-w-2xl font-display text-3xl font-semibold tracking-tight sm:text-4xl lg:text-[2.75rem]">
            Ready to run prediction markets as your own?
          </h2>

          {/* The three-part promise, restated as the closing line. */}
          <div className="flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-sm text-muted-foreground sm:text-base">
            {PROMISE.map((p, i) => (
              <span key={p} className="flex items-center gap-x-5">
                {i > 0 && (
                  <span aria-hidden="true" className="text-border-strong">
                    ·
                  </span>
                )}
                {p}
              </span>
            ))}
          </div>

          <div className="flex flex-wrap items-center justify-center gap-3 pt-2">
            <Button asChild size="lg" className="glow-brand">
              <Link href="/register">Create your account</Link>
            </Button>
            <Button asChild size="lg" variant="outline">
              <Link href="#demo">Explore the platform</Link>
            </Button>
          </div>
        </div>
      </div>
    </section>
  );
}
