/**
 * XGridHero — the single-viewport landing hero (sales-demo face).
 *
 * Replaces the 7-section Phase 19 landing with one screen: the XParticles
 * canvas full-bleed underneath, and a centered, minimal overlay on top —
 * badge, headline, one brand line, two CTAs. The overlay is pointer-events-
 * none (except the CTAs) so the canvas receives cursor/click interaction
 * everywhere. Server Component (composes the client XParticles/Spark).
 */
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Spark } from "@/components/brand/spark";
import { XParticles } from "@/components/home/x-particles";

export function XGridHero({ brandName }: { brandName: string }) {
  const raw = brandName.trim();
  const name = !raw || raw === "XPredict" ? "XPrediction" : raw;
  return (
    <section className="relative flex min-h-[calc(100dvh-4rem)] items-center justify-center overflow-hidden">
      <XParticles />

      <div className="pointer-events-none relative z-10 flex max-w-3xl flex-col items-center gap-6 px-4 py-16 text-center text-balance">
        <span className="inline-flex items-center gap-2 rounded-full border border-border bg-surface/70 px-3 py-1 text-xs font-medium text-muted-foreground">
          <Spark className="h-3.5 w-3.5" />
          Prediction-market platform
        </span>

        <h1 className="font-display text-4xl font-semibold leading-[1.05] tracking-tight sm:text-6xl lg:text-7xl">
          The core that <span className="text-gradient-brand">connects</span>{" "}
          every prediction market.
        </h1>

        <p className="max-w-xl text-base text-muted-foreground sm:text-lg">
          {name} — white-label, API-first. Run native markets, integrate
          external ones, launch your own.
        </p>

        <div className="pointer-events-auto flex flex-wrap items-center justify-center gap-3 pt-2">
          <Button asChild size="lg" className="glow-brand">
            <Link href="/login">Log in</Link>
          </Button>
          <Button asChild size="lg" variant="outline">
            <Link href="/markets">Explore the demo</Link>
          </Button>
        </div>
      </div>
    </section>
  );
}
