/**
 * HeroBand — the landing hero (Phase 19, platform-first positioning).
 *
 * XPredict is a COMPLETE prediction-market platform: run native markets,
 * integrate external ones, and launch your own under your brand. The hero leads
 * with that platform message (Stripe/Vercel/Shopify-Platform altitude), built
 * around the angular "X" + the central spark, over the global `Aurora` backdrop.
 * Primary CTA = Log in ("Acceder"); secondary = explore the live demo. Server
 * Component (composes the client XMark/Spark).
 */
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Spark } from "@/components/brand/spark";
import { XMark } from "@/components/brand/x-mark";
import { HeroVisual } from "@/components/home/hero-visual";

export function HeroBand({ brandName }: { brandName: string }) {
  const raw = brandName.trim();
  const name = !raw || raw === "XPredict" ? "XPrediction" : raw;
  return (
    <section className="relative overflow-hidden">
      <div className="mx-auto grid w-full max-w-6xl items-center gap-10 px-4 py-16 sm:px-6 sm:py-20 lg:grid-cols-[1.15fr_0.85fr] lg:py-28">
        {/* Copy */}
        <div className="flex flex-col items-start gap-6 text-balance">
          <span className="inline-flex items-center gap-2 rounded-full border border-border bg-surface/70 px-3 py-1 text-xs font-medium text-muted-foreground">
            <Spark className="h-3.5 w-3.5" />
            Prediction-market platform &amp; infrastructure
          </span>

          <h1 className="font-display text-4xl font-semibold leading-[1.05] tracking-tight sm:text-5xl lg:text-[3.6rem]">
            The core that{" "}
            <span className="text-gradient-brand">connects</span> every
            prediction market.
          </h1>

          <p className="max-w-xl text-base leading-relaxed text-muted-foreground sm:text-lg">
            {name} is the white-label, API-first layer for prediction markets —
            run native markets, integrate external ones, and let any brand launch
            and operate their own on your infrastructure.
          </p>

          <div className="flex flex-wrap items-center gap-3 pt-1">
            <Button asChild size="lg" className="glow-brand">
              <Link href="/login">Log in</Link>
            </Button>
            <Button asChild size="lg" variant="outline">
              <Link href="#demo">Explore the live demo</Link>
            </Button>
          </div>

          <p className="max-w-xl text-sm leading-relaxed text-subtle-foreground">
            Stripe for payments · Shopify for commerce · Vercel for deploy —{" "}
            <span className="text-muted-foreground">
              {name} for prediction markets.
            </span>{" "}
            New here?{" "}
            <Link
              href="/register"
              className="font-medium text-foreground underline underline-offset-4 transition-colors hover:text-brand-primary"
            >
              Create a free account
            </Link>
          </p>
        </div>

        {/* Compact brand mark for < lg (the full ecosystem network is desktop). */}
        <div className="relative flex items-center justify-center py-4 lg:hidden">
          <div
            aria-hidden="true"
            className="absolute h-44 w-44 rounded-full bg-brand-primary/20 blur-3xl"
          />
          <XMark
            animated
            className="relative h-32 w-32 drop-shadow-[0_8px_40px_rgba(37,99,235,0.35)]"
          />
        </div>

        {/* The living ecosystem network — the X core connecting everything. */}
        <HeroVisual />
      </div>

      {/* Audience strip — who it's for. */}
      <div className="mx-auto w-full max-w-6xl px-4 pb-10 sm:px-6">
        <p className="mb-3 text-center text-xs font-medium uppercase tracking-[0.18em] text-subtle-foreground sm:text-left">
          Built for the teams that shape what happens next
        </p>
        <div className="flex flex-wrap justify-center gap-2 sm:justify-start">
          {["Companies", "Platforms", "Media", "Communities", "Operators"].map(
            (a) => (
              <span
                key={a}
                className="rounded-full border border-border bg-surface/60 px-3.5 py-1.5 text-sm text-muted-foreground"
              >
                {a}
              </span>
            ),
          )}
        </div>
      </div>

      {/* Hairline divider into the body. */}
      <div
        aria-hidden="true"
        className="mx-auto h-px w-full max-w-6xl bg-gradient-to-r from-transparent via-border to-transparent"
      />
    </section>
  );
}
