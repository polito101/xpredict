/**
 * XGridHero — the single-viewport landing hero (sales-demo face).
 *
 * One exact screen (no scroll: the section is 100svh minus the h-16 header,
 * and the landing renders no footer): the XParticles canvas full-bleed
 * underneath and a minimal overlay — one headline and the CTAs. The overlay
 * is pointer-events-none (except the CTA container) so the canvas owns
 * cursor/click interaction everywhere; the interactivity IS the page.
 *
 * CTAs: with `demoMode` (NEXT_PUBLIC_DEMO_MODE, resolved by the server page —
 * mirrors the login page's gate so the button is absent from white-label
 * builds) the primary action is the one-click ephemeral demo session
 * (`DemoLoginButton` → POST /auth/demo-login → /markets); otherwise Log in is
 * primary with a plain link into the catalog.
 */
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { DemoLoginButton } from "@/app/(auth)/login/demo-login-button";
import { XParticles } from "@/components/home/x-particles";

export function XGridHero({ demoMode }: { demoMode: boolean }) {
  return (
    // svh (not dvh): the mobile URL bar collapsing must not resize the hero —
    // a dvh-driven resize would rebuild the canvas layout on every scroll.
    <section className="relative flex h-[calc(100svh-4rem)] items-center justify-center overflow-hidden">
      <XParticles />

      <div className="pointer-events-none relative z-10 flex max-w-4xl flex-col items-center gap-8 px-4 text-center text-balance">
        <h1 className="font-display text-4xl font-semibold leading-[1.05] tracking-tight sm:text-6xl lg:text-7xl">
          The core that <span className="text-gradient-brand">connects</span>{" "}
          every prediction market.
        </h1>

        <div className="pointer-events-auto flex flex-wrap items-center justify-center gap-3">
          {demoMode ? (
            <>
              <DemoLoginButton size="lg" variant="default" className="glow-brand" />
              <Button asChild size="lg" variant="outline">
                <Link href="/login">Log in</Link>
              </Button>
            </>
          ) : (
            <>
              <Button asChild size="lg" className="glow-brand">
                <Link href="/login">Log in</Link>
              </Button>
              <Button asChild size="lg" variant="outline">
                <Link href="/markets">Explore the demo</Link>
              </Button>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
