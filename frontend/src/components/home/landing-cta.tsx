/**
 * LandingCta — the closing conversion band (Phase 19 landing).
 * Server Component (composes the client Spark).
 */
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Spark } from "@/components/brand/spark";

export function LandingCta() {
  return (
    <section className="mx-auto w-full max-w-6xl px-4 pb-24 pt-4 sm:px-6">
      <div className="relative overflow-hidden rounded-3xl border border-border bg-card px-6 py-14 text-center sm:px-12">
        {/* Brand glow flourish. */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 opacity-60"
          style={{
            backgroundImage:
              "radial-gradient(40rem 20rem at 50% -20%, color-mix(in oklab, var(--brand-primary) 25%, transparent), transparent 70%)",
          }}
        />
        <div className="relative flex flex-col items-center gap-5">
          <Spark className="h-8 w-8" />
          <h2 className="max-w-2xl font-display text-3xl font-semibold tracking-tight sm:text-4xl">
            Build your prediction markets on XPredict.
          </h2>
          <p className="max-w-xl text-base text-muted-foreground">
            Trade, integrate, and launch — on infrastructure that carries your
            brand from day one.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-3 pt-1">
            <Button asChild size="lg" className="glow-brand">
              <Link href="/register">Create your account</Link>
            </Button>
            <Button asChild size="lg" variant="outline">
              <Link href="/login">Log in</Link>
            </Button>
          </div>
        </div>
      </div>
    </section>
  );
}
